// Executive summary: check exact writers at page, block, vocabulary and row-group boundaries.
#include PQSOURCE
#include "message_pipeline.hpp"
#include <filesystem>
#include <cassert>
#include <iostream>
#include <fstream>
#include <limits>
using namespace t3;
namespace t3 {
const char* const kMsgTypeNames[MT_COUNT] = {
  "AGENT_WAKEUP", "MarketClosePriceRequestMsg", "MarketHoursRequestMsg", "MarketHoursMsg",
  "QuerySpreadMsg", "QuerySpreadResponseMsg", "LimitOrderMsg", "CancelOrderMsg",
  "OrderAcceptedMsg", "OrderExecutedMsg", "OrderCancelledMsg", "MarketClosedMsg", "MarketClosePriceMsg"
};
}
MessageColumns messages(size_t begin, size_t n, int null_mode = 0) {
  MessageColumns m;
  for (size_t j = 0; j < n; ++j) {
    int64_t i = begin + j;
    m.t_recv.push_back(1000000000 + i * 37); m.t_send.push_back(i * 31);
    m.latency.push_back(i * 6); m.message_id.push_back(i * 2);
    m.order_id.push_back(i / 2); m.causal_parent.push_back(i - 1);
    m.t_send_null.push_back(null_mode == 1 || (null_mode == 0 && i % 19 == 0));
    m.order_id_null.push_back(null_mode == 1 || (null_mode == 0 && i % 7 == 0));
    m.causal_null.push_back(null_mode == 1 || (null_mode == 0 && i % 13 == 0));
    m.src.push_back(i % 31); m.dst.push_back(i % 11);
    // New vocabulary first appears exactly around write-batch/block boundaries.
    m.msg_type.push_back(i < 1023 ? 0 : i < 65535 ? 1 : i % MT_COUNT);
  }
  return m;
}
TraceColumns trace(size_t n) {
  TraceColumns t;
  for (size_t i = 0; i < n; ++i) {
    t.t_ns.push_back(i * 17); t.agent_id.push_back(i % 31);
    t.msg_type.push_back(i < 1023 ? 0 : i < 65535 ? 1 : i % 6);
    t.side.push_back(i < 1024 ? 0 : i % 2);
    t.price.push_back(10000 + i % 79); t.size.push_back(i % 512); t.order_id.push_back(i);
  }
  return t;
}
int main(int argc, char** argv) {
  assert(argc == 2 || argc == 3); std::filesystem::create_directories(argv[1]);
  for (size_t n : {size_t(0), size_t(1), size_t(1023), size_t(1024), size_t(1025),
                   size_t(65535), size_t(65536), size_t(65537),
                   kMessageRowGroupRows - 1, kMessageRowGroupRows,
                   kMessageRowGroupRows + 1, 2 * kMessageRowGroupRows + 1537}) {
    if (argc == 3 && n != std::stoull(argv[2])) continue;
    auto stem = std::string(argv[1]) + "/" + std::to_string(n);
    auto m = messages(0, n); auto t = trace(n);
    if (n == 0) {
      // Compare the original library-specific empty success/error behavior.
      // Arrow25 rejects native empty string views; the binding bypasses writers
      // on empty lifecycle traces on every version.
      auto empty = [&](const std::string& suffix, auto write) {
        auto path = stem + suffix + ".parquet";
        try { write(path); }
        catch (const std::runtime_error& e) {
          std::filesystem::remove(path);
          std::ofstream(stem + suffix + ".status") << e.what();
        }
      };
      empty("-messages-table", [&](const std::string& p) { write_messages(m, p); });
      empty("-messages-stream", [&](const std::string& p) { MessageParquetWriter w(p); w.close(); });
      empty("-trace", [&](const std::string& p) { write_trace(t, p); });
      continue;
    }
    write_messages(m, stem + "-messages-table.parquet");
    // The two caller threads are outside the encoder executor. Exercise real
    // pipeline backpressure while trace and message encoding share its capacity.
    MessageParquetWriter writer(stem + "-messages-stream.parquet");
    MessagePipeline pipeline([&](const MessageColumns& b, size_t o) { writer.append(b, o); },
                             [&] { writer.close(); });
    for (size_t i = 0; i < n; i += kMessageBlockRows) {
      auto b = messages(i, std::min(kMessageBlockRows, n - i)); pipeline.submit(b);
    }
    write_trace(t, stem + "-trace.parquet"); pipeline.finish(); writer.close();
    std::cout << n << " boundary rows passed\n";
  }
  if (argc == 3 && std::stoull(argv[2]) != 2098689) return 0;
  for (int mode : {1, 2}) {
    auto m = messages(0, 65537, mode);
    auto stem = std::string(argv[1]) + "/null-" + std::to_string(mode);
    write_messages(m, stem + "-table.parquet");
    MessageParquetWriter writer(stem + "-stream.parquet");
    writer.append(messages(0, 65536, mode), 0); writer.append(messages(65536, 1, mode), 65536);
    writer.close();
  }
  {
    auto t = trace(2); auto m = messages(0, 2, 2);
    t.t_ns[0] = m.t_recv[0] = std::numeric_limits<int64_t>::min();
    t.t_ns[1] = m.t_recv[1] = std::numeric_limits<int64_t>::max();
    t.agent_id[0] = m.src[0] = std::numeric_limits<int32_t>::min();
    t.agent_id[1] = m.src[1] = std::numeric_limits<int32_t>::max();
    t.price[0] = m.order_id[0] = -1; t.size[1] = m.causal_parent[1] = std::numeric_limits<int64_t>::max();
    write_trace(t, std::string(argv[1]) + "/extremes-trace.parquet");
    write_messages(m, std::string(argv[1]) + "/extremes-messages.parquet");
  }
  { MessageParquetWriter writer(std::string(argv[1]) + "/errors.parquet");
    auto expect_error = [&](const MessageColumns& m, size_t o) {
      bool threw = false; try { writer.append(m, o); } catch (const std::runtime_error&) { threw = true; }
      assert(threw);
    };
    expect_error(messages(0, 0), 0); expect_error(messages(0, 65537), 0);
    expect_error(messages(0, 1), 1); writer.append(messages(0, 1), 0);
    expect_error(messages(1, 1), 1); writer.close(); writer.close(); expect_error(messages(1, 1), 1);
  }
  // WriteTable used to validate input before encoding; preserve that error too.
  auto malformed = trace(2); malformed.price.pop_back();
  const auto bad_path = std::string(argv[1]) + "/malformed.parquet";
  bool failed = false;
  try { write_trace(malformed, bad_path); }
  catch (const std::runtime_error& e) {
    failed = true; std::filesystem::remove(bad_path);
    std::ofstream(std::string(argv[1]) + "/malformed.status") << e.what();
  }
  assert(failed);
#ifdef SPECIALIZED
  auto reject = [&](auto write) { bool rejected = false; try { write(); } catch (const std::runtime_error&) { rejected = true; } assert(rejected); };
  for (uint8_t bad : {uint8_t(6), uint8_t(255)}) {
    auto t = trace(1); t.msg_type[0] = bad; reject([&] { write_trace(t, bad_path); });
  }
  auto t = trace(1); t.side[0] = 2; reject([&] { write_trace(t, bad_path); });
  auto m = messages(0, 1); m.msg_type[0] = MT_COUNT; reject([&] { write_messages(m, bad_path); });
  m = messages(0, 1); m.causal_null.clear(); reject([&] { write_messages(m, bad_path); });
#endif
}
