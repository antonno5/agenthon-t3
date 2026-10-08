// Executive summary: compare full-table, full-rowgroup and partial buffered writers.
// Including the implementation lets this probe reuse the exact schema/properties.
#include "pqwrite.cpp"
#include <iostream>
#include <filesystem>
using namespace t3;
MessageColumns rows(size_t begin, size_t n) {
  MessageColumns m;
  for (size_t j = 0; j < n; ++j) {
    int64_t i = begin + j;
    m.t_recv.push_back(1000000000 + i * 37); m.t_send.push_back(i * 31);
    m.latency.push_back(i * 6); m.message_id.push_back(i * 2);
    m.order_id.push_back(i / 2); m.causal_parent.push_back(i - 1);
    m.t_send_null.push_back(i % 19 == 0); m.order_id_null.push_back(i % 7 == 0);
    m.causal_null.push_back(i % 13 == 0); m.src.push_back(i % 31);
    m.dst.push_back(i % 11); m.msg_type.push_back(i % MT_COUNT);
  }
  return m;
}
int main(int argc, char** argv) {
  std::filesystem::create_directories(argv[1]);
  for (size_t n : {size_t(1), size_t(1023), size_t(1024), size_t(65535), size_t(65536), size_t(65537),
                   kMessageRowGroupRows - 1, kMessageRowGroupRows, kMessageRowGroupRows + 1,
                   2 * kMessageRowGroupRows + 1537}) {
    auto stem = std::string(argv[1]) + "/" + std::to_string(n);
    auto m = rows(0, n); write_messages(m, stem + "-table.parquet");
    { MessageParquetWriter writer(stem + "-candidate.parquet");
      for (size_t i = 0; i < n; i += kMessageBlockRows)
        writer.append(rows(i, std::min(kMessageBlockRows, n - i)), i);
      writer.close(); }
    { auto sink = value(arrow::io::FileOutputStream::Open(stem + "-partial.parquet"));
      auto writer = open_writer(message_schema(), sink);
      if (!n) {
        OwnedBuffers own; std::vector<int64_t> seq;
        check(writer->WriteTable(*message_table(m, 0, own, seq), 0));
      }
      for (size_t i = 0; i < n; i += 65536) {
        if (i % kMessageRowGroupRows == 0) check(writer->NewBufferedRowGroup());
        auto block = rows(i, std::min<size_t>(65536, n - i));
        OwnedBuffers own; std::vector<int64_t> seq;
        auto table = message_table(block, i, own, seq);
        std::vector<std::shared_ptr<arrow::Array>> cols;
        for (const auto& col : table->columns()) cols.push_back(col->chunk(0));
        auto batch = arrow::RecordBatch::Make(table->schema(), table->num_rows(), cols);
        check(writer->WriteRecordBatch(*batch));
      }
      check(writer->Close()); check(sink->Close()); }
    std::cout << n << " rows written\n";
  }
}
