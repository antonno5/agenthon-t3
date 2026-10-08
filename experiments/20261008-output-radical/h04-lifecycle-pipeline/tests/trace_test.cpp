// Executive summary: trace order, late fills, bounded handoff and negative-latency fallback.
#include "trace_stream.hpp"
#include "trace_pipeline.hpp"
#include <cassert>
#include <atomic>
#include <iostream>
using namespace t3;
struct Sink : TraceSink {
  size_t rows = 0, calls = 0;
  void submit(TraceColumns& b) override {
    assert(b.msg_type.empty() && b.t_ns.size() <= kTraceBlockRows);
    rows += b.t_ns.size(); ++calls; clear_trace(b);
  }
};
int main() {
  Sink sink;
  TraceStream s(true, &sink);
  // Agent-log stable ties: quotes first; oid, owner, append order afterwards.
  s.order(10, 2, 20, TM_PARTIAL_FILL, SIDE_BID, 3, 2, 1);
  s.order(10, 1, 10, TM_ORDER_ACCEPTED, SIDE_BID, 3, 4, 1);
  s.order(10, 1, 10, TM_ORDER_SUBMITTED, SIDE_BID, 3, 4, 1);
  s.quote(10, SIDE_ASK, 5, 8); s.quote(10, SIDE_ASK, 6, 9);
  for (size_t i = 0; i < kTracePipelineRows + 17; ++i)
    s.order(20 + i, 1, 10, TM_ORDER_ACCEPTED, SIDE_BID, 3, 4, 2);
  assert(sink.rows == kTracePipelineRows); // handoff happens before finish
  s.order(2 * kTracePipelineRows, 2, 20, TM_PARTIAL_FILL, SIDE_BID, 3, 1, 1);
  auto t = s.finish();
  assert(sink.rows == kTracePipelineRows && sink.calls == 16);
  assert(t.order_id[0] == -1 && t.price[0] == 6 && t.size[0] == 9);
  assert(t.msg_type[1] == TM_ORDER_ACCEPTED && t.msg_type[2] == TM_ORDER_SUBMITTED);
  assert(t.msg_type[3] == TM_PARTIAL_FILL); // demoted after first encoded row group
  assert(t.msg_type.back() == TM_ORDER_FILLED); // final retained execution, residual irrelevant
  Sink negative;
  TraceStream fallback(false, &negative);
  fallback.order(30, 1, 1, TM_PARTIAL_FILL, SIDE_ASK, 9, 2, 4);
  fallback.order(20, 1, 1, TM_PARTIAL_FILL, SIDE_ASK, 9, 3, 4);
  auto f = fallback.finish();
  assert(negative.calls == 0 && f.t_ns[0] == 20 && f.msg_type[0] == TM_PARTIAL_FILL);
  assert(f.msg_type[1] == TM_ORDER_FILLED);
  // One timestamp crosses an input block. Quote overwrites happen before sorting
  // and submission, and ordering exactly matches the unchanged buffered stream.
  Sink ties_sink;
  TraceStream ties(true, &ties_sink), buffered;
  for (size_t i = 0; i < kTraceBlockRows + 7; ++i) {
    const int64_t oid = kTraceBlockRows + 7 - i;
    ties.order(100, i % 3, i % 3, TM_ORDER_ACCEPTED, SIDE_ASK, 8, 2, oid);
    buffered.order(100, i % 3, i % 3, TM_ORDER_ACCEPTED, SIDE_ASK, 8, 2, oid);
  }
  ties.quote(100, SIDE_BID, 7, 1); buffered.quote(100, SIDE_BID, 7, 1);
  ties.quote(100, SIDE_BID, 6, 9); buffered.quote(100, SIDE_BID, 6, 9);
  auto tied = ties.finish(), expected = buffered.finish();
  assert(ties_sink.rows == tied.t_ns.size() && ties_sink.calls == 2);
  assert(tied.t_ns == expected.t_ns && tied.agent_id == expected.agent_id &&
         tied.msg_type == expected.msg_type && tied.side == expected.side &&
         tied.price == expected.price && tied.size == expected.size && tied.order_id == expected.order_id);
  // Positive path rejects time reversal and leaves no worker running on unwind.
  bool threw = false;
  try { TraceStream wrong; wrong.order(2,1,1,0,0,1,1,0); wrong.order(1,1,1,0,0,1,1,0); }
  catch (const std::runtime_error&) { threw = true; }
  assert(threw);
  std::atomic<size_t> encoded{0};
  TracePipeline pipeline([&](const TraceColumns& b, size_t) { encoded += b.t_ns.size(); }, [] {});
  TraceStream streaming(true, &pipeline);
  for (size_t i = 0; i < 4 * kTraceBlockRows; ++i)
    streaming.order(i,1,1,TM_ORDER_ACCEPTED,0,1,1,i);
  // Two queued buffers enforce actual worker completion before producer can continue.
  assert(encoded >= kTraceBlockRows);
  streaming.finish(); pipeline.finish();
  assert(encoded == 4 * kTraceBlockRows);
  std::cout << "trace ordering/demotion/cap/fallback/active producer overlap: passed\n";
}
