// Executive summary: encode identical real engine columns to memory without simulation or disk I/O.
#include PQSOURCE
#include <arrow/io/memory.h>
#include <arrow/ipc/api.h>
#include <chrono>
#include <ctime>
#include <fstream>
#include <iostream>
#include <thread>
using namespace t3;
using Clock = std::chrono::steady_clock;
double seconds(Clock::time_point begin) { return std::chrono::duration<double>(Clock::now()-begin).count(); }
struct Output {
  std::shared_ptr<arrow::Buffer> bytes;
  double setup = 0, write = 0, close = 0;
  int64_t rows = 0, batches = 0, rowgroups = 0;
};
Output encode(std::shared_ptr<arrow::Table> table, bool message) {
  Output out; out.rows = table->num_rows();
  auto begin = Clock::now();
  auto sink = value(arrow::io::BufferOutputStream::Create());
  auto writer = open_writer(table->schema(), sink);
  std::vector<std::shared_ptr<arrow::Array>> columns;
  for (const auto& c : table->columns()) { if (c->num_chunks() != 1) throw std::runtime_error("combine input chunks first"); columns.push_back(c->chunk(0)); }
  auto batch = arrow::RecordBatch::Make(table->schema(), table->num_rows(), columns);
  out.setup = seconds(begin); begin = Clock::now();
  if (message) {
    // Exactly the production ledger's 64Ki record callbacks and 1Mi groups.
    for (int64_t offset = 0; offset < table->num_rows(); offset += kMessageBlockRows) {
      if (offset % kMessageRowGroupRows == 0) { check(writer->NewBufferedRowGroup()); ++out.rowgroups; }
      check(writer->WriteRecordBatch(*batch->Slice(offset, std::min<int64_t>(kMessageBlockRows, table->num_rows()-offset))));
      ++out.batches;
    }
  } else {
#ifdef CANDIDATE
    write_buffered_table(table, writer.get());
#else
    check(writer->WriteTable(*table, std::min<int64_t>(table->num_rows(), kMessageRowGroupRows)));
#endif
    out.rowgroups = (table->num_rows()+kMessageRowGroupRows-1)/kMessageRowGroupRows;
    out.batches = out.rowgroups;
  }
  out.write = seconds(begin); begin = Clock::now();
  check(writer->Close()); out.close = seconds(begin);
  out.bytes = value(sink->Finish());
  return out;
}
std::shared_ptr<arrow::Table> load(const std::string& path) {
  auto file = value(arrow::io::ReadableFile::Open(path));
  auto reader = value(arrow::ipc::RecordBatchFileReader::Open(file));
  std::vector<std::shared_ptr<arrow::RecordBatch>> batches;
  for (int i = 0; i < reader->num_record_batches(); ++i) batches.push_back(value(reader->ReadRecordBatch(i)));
  auto table = value(arrow::Table::FromRecordBatches(batches));
  return value(table->CombineChunks());
}
void save(const Output& out, const std::string& path) {
  if (!out.bytes) return;
  std::ofstream f(path, std::ios::binary); f.write(reinterpret_cast<const char*>(out.bytes->data()), out.bytes->size());
  if (!f) throw std::runtime_error("diagnostic output write failed");
}
void show(const char* name, const Output& out) {
  std::cout << '"' << name << "\":{\"rows\":" << out.rows << ",\"columns\":" << (std::string(name)=="trace"?7:10)
            << ",\"record_batches\":" << out.batches << ",\"rowgroups\":" << out.rowgroups
            << ",\"output_bytes\":" << (out.bytes?out.bytes->size():0)
            << ",\"setup_seconds\":" << out.setup << ",\"write_seconds\":" << out.write << ",\"close_seconds\":" << out.close << '}';
}
int main(int argc, char** argv) {
  if (argc != 4) return 2;
  std::string input = argv[1], mode = argv[2], output = argv[3];
  auto trace = load(input+"/trace.arrow"), messages = load(input+"/messages.arrow");
  Output t, m; std::exception_ptr failure;
  auto begin = Clock::now(); auto cpu_begin = std::clock();
  if (mode == "overlap") {
    std::thread ledger([&] { try { m = encode(messages, true); } catch (...) { failure = std::current_exception(); } });
    try { t = encode(trace, false); } catch (...) { ledger.join(); throw; }
    ledger.join(); if (failure) std::rethrow_exception(failure);
  } else if (mode == "trace") t = encode(trace, false);
  else if (mode == "messages") m = encode(messages, true);
  else throw std::runtime_error("unknown mode");
  double wall = seconds(begin), cpu = double(std::clock()-cpu_begin)/CLOCKS_PER_SEC;
  // Disk output and digest comparisons happen after every timed region.
  save(t, output+"/trace.parquet"); save(m, output+"/message_trace.parquet");
  std::cout.precision(12);
  std::cout << "{\"wall_seconds\":" << wall << ",\"process_cpu_seconds\":" << cpu << ',';
  show("trace", t); std::cout << ','; show("messages", m); std::cout << "}\n";
}
