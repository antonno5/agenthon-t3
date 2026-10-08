// Executive summary: validate exact lifecycle bytes across page, block and rowgroup boundaries.
#include "pqwrite.cpp"
#include "trace_stream.hpp"
#include "trace_pipeline.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cassert>
using namespace t3;
namespace t3 { const char* const kMsgTypeNames[MT_COUNT] = {
  "AGENT_WAKEUP", "MKT_CLOSE_PRICE_REQ", "MKT_HOURS_REQ", "MKT_HOURS", "QUERY_SPREAD",
  "QUERY_SPREAD_RESP", "LIMIT_ORDER", "CANCEL_ORDER", "ORDER_ACCEPTED", "ORDER_EXECUTED",
  "ORDER_CANCELLED", "MKT_CLOSED", "MKT_CLOSE_PRICE"}; }
TraceColumns rows(size_t begin, size_t n, bool types = true) {
  TraceColumns t;
  for (size_t j = 0; j < n; ++j) {
    int64_t i = begin + j;
    t.t_ns.push_back(1000000000 + i * 37); t.agent_id.push_back(i % 31);
    if (types) t.msg_type.push_back(i % 6);
    t.side.push_back(i % 2); t.price.push_back(10000 + i * 3);
    t.size.push_back(i % 113); t.order_id.push_back(i - 1);
  }
  return t;
}
int main(int argc, char** argv) {
  assert(argc == 2); std::filesystem::create_directories(argv[1]);
  for (size_t n : {size_t(1),size_t(1023),size_t(1024),size_t(1025),size_t(65535),
                   size_t(65536),size_t(65537), kTracePipelineRows - 1, kTracePipelineRows,
                   kTracePipelineRows + 1, 2 * kTracePipelineRows + 1537}) {
    auto stem = std::string(argv[1]) + "/" + std::to_string(n);
    auto t = rows(0,n); write_trace(t,stem + "-baseline.parquet");
    TraceParquetWriter writer(stem + "-candidate.parquet");
    for (size_t offset = 0; offset < std::min(n,kTracePipelineRows); offset += kTraceBlockRows)
      writer.append_immutable(rows(offset,std::min(kTraceBlockRows,n-offset),false),offset);
    assert(writer.encoded_rows() == std::min(n,kTracePipelineRows));
    writer.finish(t);
    std::cout << n << " rows\n";
  }
  const std::string stem = std::string(argv[1]) + "/late-fill";
  TraceParquetWriter writer(stem + "-candidate.parquet");
  TracePipeline p([&](const TraceColumns& b,size_t off) { writer.append_immutable(b,off); },[] {});
  TraceStream stream(true,&p);
  stream.order(1,1,1,TM_PARTIAL_FILL,SIDE_BID,100,3,0);
  for (size_t i = 0; i < kTracePipelineRows + 31; ++i)
    stream.order(2+i,1,1,TM_ORDER_ACCEPTED,SIDE_BID,100,1,1);
  stream.order(2*kTracePipelineRows,1,1,TM_PARTIAL_FILL,SIDE_BID,100,2,0);
  auto t = stream.finish(); p.finish();
  assert(t.msg_type[0] == TM_PARTIAL_FILL && t.msg_type.back() == TM_ORDER_FILLED);
  writer.finish(t); write_trace(t,stem + "-baseline.parquet");
  bool rejected = false;
  try { TraceParquetWriter w(std::string(argv[1])+"/invalid.parquet"); w.append_immutable(rows(0,1),0); }
  catch (const std::runtime_error&) { rejected = true; }
  assert(rejected);
}
