// Output building off the simulation thread. The kernel only appends compact records to two
// single-producer/single-consumer rings of fixed chunks -- ledger deliveries in one, lifecycle
// orders and quotes in the other -- and one consumer thread per ring replays them, in the same
// order, into the same ledger columns / TraceStream the kernel used to fill itself (full
// ledger blocks still go to the sink). The two outputs share no state, and each ring keeps
// its own call order, so the replayed output is identical. Building it was ~47% of the
// kernel thread's time on the largest units.
//
// Errors raised while replaying (TraceStream's ordering guards) are captured and rethrown by
// finish() on the kernel thread, so the caller sees the same std::runtime_error as before,
// only after the loop instead of during it.
#pragma once

#include <atomic>
#include <cstdint>
#include <exception>
#include <memory>
#include <thread>
#include <utility>

#include "engine.hpp"
#include "spsc.hpp"
#include "trace_stream.hpp"

namespace t3 {

// One ring + its consumer thread. `Apply` is called on the consumer for every record, in
// append order; `Done` once after the last one (not after an error or an abort).
template <class Rec>
class Lane {
 public:
  template <class Apply, class Done>
  void start(Apply apply, Done done) {
    ring_.reset(new Chunk[kChunks]);
    worker_ = std::thread([this, apply, done]() mutable { consume(apply, done); });
  }
  Lane() = default;
  Lane(const Lane&) = delete;
  Lane& operator=(const Lane&) = delete;
  ~Lane() {
    if (worker_.joinable()) {
      abort_.store(true);
      join();
    }
  }

  Rec& next() {
    if (fill_ == kChunkRecs) publish();
    if (fill_ == 0 && head_ - consumed_.load() >= kChunks)  // the slot's chunk is still in use
      space_.wait_until([this] { return head_ - consumed_.load() < kChunks; });
    return ring_[head_ % kChunks].recs[fill_++];
  }
  // Publishes the tail, waits for the consumer; rethrows its error.
  void join() {
    publish();
    done_.store(true);
    data_.notify();
    worker_.join();
    if (error_ && !abort_.load()) std::rethrow_exception(error_);
  }

 private:
  static constexpr size_t kChunkRecs = 4096;
  static constexpr size_t kChunks = 16;
  struct Chunk {
    Rec recs[kChunkRecs];
    size_t n = 0;
  };
  std::unique_ptr<Chunk[]> ring_;
  size_t head_ = 0;  // producer: chunks published
  size_t fill_ = 0;  // producer: records in the current chunk
  alignas(64) std::atomic<size_t> published_{0};
  alignas(64) std::atomic<size_t> consumed_{0};
  std::atomic<bool> done_{false}, abort_{false};
  Event data_, space_;  // "chunk published" / "chunk released"
  std::exception_ptr error_;
  std::thread worker_;

  void publish() {
    if (fill_ == 0) return;
    ring_[head_ % kChunks].n = fill_;
    fill_ = 0;
    published_.store(++head_);
    data_.notify();
  }

  template <class Apply, class Done>
  void consume(Apply& apply, Done& done) noexcept {
    size_t tail = 0;
    bool failed = false;
    for (;;) {
      data_.wait_until([&] { return published_.load() != tail || done_.load(); });
      const size_t avail = published_.load();
      if (avail == tail) break;  // done and drained
      for (; tail < avail; tail++) {
        const Chunk& c = ring_[tail % kChunks];
        if (!failed && !abort_.load(std::memory_order_relaxed)) {
          try {
            for (size_t i = 0; i < c.n; i++) apply(c.recs[i]);
          } catch (...) {
            error_ = std::current_exception();
            failed = true;  // keep releasing chunks so the producer never blocks
          }
        }
        consumed_.store(tail + 1);
        space_.notify();
      }
    }
    if (failed || abort_.load()) return;
    try {
      done();
    } catch (...) {
      error_ = std::current_exception();
    }
  }
};

class OutputLog {
 public:
  OutputLog(bool chronological, MessageSink* sink, TraceSink* trace_sink = nullptr,
            bool ledger = true)
      : sink_(sink), trace_sink_(trace_sink), ledger_on_(ledger), trace_(chronological) {
    if (ledger_on_) ledger_.start([this](const LedgerRec& r) { apply(r); },
                  [this] {
                    if (sink_ && !mcols_.t_recv.empty()) sink_->submit(mcols_);
                  });
    lifecycle_.start([this](const TraceRec& r) { apply(r); },
                     [this] { trace_columns_ = trace_.finish(); });
  }

  // Kernel.deliver ledger row (see the replay in apply()).
  void deliver(int64_t msg_id, int32_t src, int32_t dst, bool has_send, int64_t t_send,
               int64_t t_recv, uint8_t type, bool has_oid, int64_t oid, int64_t causal_v) {
    LedgerRec& r = ledger_.next();
    r.msg_id = msg_id; r.t_send = t_send; r.t_recv = t_recv; r.oid = oid; r.causal = causal_v;
    r.src = src; r.dst = dst;
    r.type = type;
    r.flags = static_cast<uint8_t>((has_send ? 1 : 0) | (has_oid ? 2 : 0));
  }
  void order(int64_t t, int32_t owner, int32_t agent, uint8_t type, uint8_t side,
             int64_t price, int64_t size, int64_t oid) {
    TraceRec& r = lifecycle_.next();
    r.t = t; r.price = price; r.size = size; r.oid = oid;
    r.owner = owner; r.agent = agent;
    r.quote = false; r.type = type; r.side = side;
  }
  void quote(int64_t t, uint8_t side, int64_t price, int64_t size) {
    TraceRec& r = lifecycle_.next();
    r.t = t; r.price = price; r.size = size;
    r.quote = true; r.side = side;
  }

  // Drains both rings, joins the consumers and returns the trace and the ledger rows not yet
  // handed to the sink (all of them when there is no sink).
  std::pair<TraceColumns, MessageColumns> finish() {
    if (ledger_on_) ledger_.join();
    lifecycle_.join();
    return {std::move(trace_columns_), std::move(mcols_)};
  }

 private:
  struct LedgerRec {
    int64_t msg_id, t_send, t_recv, oid, causal;
    int32_t src, dst;
    uint8_t type, flags;
  };
  struct TraceRec {
    int64_t t, price, size, oid;
    int32_t owner, agent;
    bool quote;
    uint8_t type, side;
  };

  MessageSink* sink_;
  TraceSink* trace_sink_;
  bool ledger_on_;
  size_t reported_ = 0;  // final trace rows already reported to trace_sink_
  TraceStream trace_;  // touched only by the lifecycle consumer
  MessageColumns mcols_;  // touched only by the ledger consumer
  TraceColumns trace_columns_;
  // Declared last: destroyed (joined) first, before the state their consumers touch.
  Lane<LedgerRec> ledger_;
  Lane<TraceRec> lifecycle_;

  void apply(const LedgerRec& r) {
    const bool has_send = r.flags & 1, has_oid = r.flags & 2;
    MessageColumns& c = mcols_;
    c.t_recv.push_back(r.t_recv);
    c.t_send.push_back(has_send ? r.t_send : 0);
    c.t_send_null.push_back(!has_send);
    c.latency.push_back(has_send ? r.t_recv - r.t_send : 0);
    c.src.push_back(r.src);
    c.dst.push_back(r.dst);
    c.message_id.push_back(r.msg_id);
    c.msg_type.push_back(r.type);
    c.order_id.push_back(has_oid ? r.oid : 0);
    c.order_id_null.push_back(!has_oid);
    c.causal_parent.push_back(r.causal >= 0 ? r.causal : 0);
    c.causal_null.push_back(r.causal < 0);
    if (sink_ && c.t_recv.size() == kMessageBlockRows) sink_->submit(c);
  }
  void apply(const TraceRec& r) {
    if (r.quote)
      trace_.quote(r.t, r.side, r.price, r.size);
    else
      trace_.order(r.t, r.owner, r.agent, r.type, r.side, r.price, r.size, r.oid);
    if (trace_sink_ && trace_.final_rows() >= reported_ + kTraceReportRows) {
      reported_ = trace_.final_rows();
      trace_sink_->rows_final(trace_.columns(), reported_);
    }
  }
  static constexpr size_t kTraceReportRows = 16 * 1024;
};

}  // namespace t3
