// Parquet output through the pinned Arrow15 writer. H01 changes only physical
// encoding: Snappy, dictionary for finite type/side vocabularies, no statistics.
// Decoded schemas (including pandas metadata), values and ordering are unchanged.
#include "pqwrite.hpp"

#include <arrow/api.h>
#include <arrow/io/file.h>
#include <arrow/util/thread_pool.h>
#include <parquet/arrow/writer.h>
#include <parquet/properties.h>

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <string>

namespace t3 {
namespace {

// pandas' to_parquet(index=False) schema metadata for trace.py's two frames (constant: with
// no index it depends only on column names and dtypes). Identical to native.py's strings.
const char* const kTraceMeta =
    "{\"index_columns\": [], \"column_indexes\": [], \"columns\": ["
    "{\"name\": \"t_ns\", \"field_name\": \"t_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"agent_id\", \"field_name\": \"agent_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"msg_type\", \"field_name\": \"msg_type\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"side\", \"field_name\": \"side\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"price\", \"field_name\": \"price\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"size\", \"field_name\": \"size\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"order_id\", \"field_name\": \"order_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}], "
    "\"creator\": {\"library\": \"pyarrow\", \"version\": \"15.0.2\"}, \"pandas_version\": \"1.5.3\"}";

const char* const kMsgMeta =
    "{\"index_columns\": [], \"column_indexes\": [], \"columns\": ["
    "{\"name\": \"seq\", \"field_name\": \"seq\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"t_recv_ns\", \"field_name\": \"t_recv_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"t_send_ns\", \"field_name\": \"t_send_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}, "
    "{\"name\": \"latency_ns\", \"field_name\": \"latency_ns\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"src_id\", \"field_name\": \"src_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"dst_id\", \"field_name\": \"dst_id\", \"pandas_type\": \"int32\", \"numpy_type\": \"int32\", \"metadata\": null}, "
    "{\"name\": \"message_id\", \"field_name\": \"message_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"int64\", \"metadata\": null}, "
    "{\"name\": \"msg_type\", \"field_name\": \"msg_type\", \"pandas_type\": \"unicode\", \"numpy_type\": \"string\", \"metadata\": null}, "
    "{\"name\": \"order_id\", \"field_name\": \"order_id\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}, "
    "{\"name\": \"causal_parent\", \"field_name\": \"causal_parent\", \"pandas_type\": \"int64\", \"numpy_type\": \"Int64\", \"metadata\": null}], "
    "\"creator\": {\"library\": \"pyarrow\", \"version\": \"15.0.2\"}, \"pandas_version\": \"1.5.3\"}";

const char* const kTraceMsgTypes[] = {"ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED",
                                      "PARTIAL_FILL",    "ORDER_FILLED",   "QUOTE_UPDATE"};
const char* const kSides[] = {"BID", "ASK"};

void check(const arrow::Status& st) {
  if (!st.ok()) throw std::runtime_error("parquet write: " + st.ToString());
}
template <class T>
T value(arrow::Result<T> r) {
  if (!r.ok()) throw std::runtime_error("parquet write: " + r.status().ToString());
  return std::move(r).ValueUnsafe();
}

// Non-owning views over the engine's column vectors (they outlive the write).
template <class T>
std::shared_ptr<arrow::Buffer> view(const std::vector<T>& v) {
  return std::make_shared<arrow::Buffer>(reinterpret_cast<const uint8_t*>(v.data()),
                                         static_cast<int64_t>(v.size() * sizeof(T)));
}

std::shared_ptr<arrow::Array> int_array(const std::shared_ptr<arrow::DataType>& type,
                                        int64_t n, std::shared_ptr<arrow::Buffer> data) {
  return arrow::MakeArray(arrow::ArrayData::Make(type, n, {nullptr, std::move(data)}, 0));
}

struct OwnedBuffers {  // storage for buffers built here (strings, bitmaps)
  std::vector<std::vector<uint8_t>> bytes;
  std::vector<std::vector<int32_t>> offsets;
};

std::shared_ptr<arrow::Array> string_array(int64_t n, const std::vector<uint8_t>& codes,
                                           const char* const* names, OwnedBuffers& own) {
  own.offsets.emplace_back(codes.size() + 1);
  own.bytes.emplace_back();
  std::vector<int32_t>& off = own.offsets.back();
  std::vector<uint8_t>& data = own.bytes.back();
  // Code columns hold a handful of distinct values: size each name once, then fill the
  // offsets and the exactly-sized data buffer with no per-row reallocation.
  size_t len[256];
  for (size_t c = 0; c < 256; c++) len[c] = 0;
  size_t total = 0;
  for (uint8_t c : codes) {
    if (len[c] == 0) len[c] = std::char_traits<char>::length(names[c]);
    total += len[c];
  }
  data.resize(total);
  off[0] = 0;
  size_t pos = 0;
  for (size_t i = 0; i < codes.size(); i++) {
    const size_t l = len[codes[i]];
    std::memcpy(data.data() + pos, names[codes[i]], l);
    pos += l;
    off[i + 1] = static_cast<int32_t>(pos);
  }
  return arrow::MakeArray(
      arrow::ArrayData::Make(arrow::utf8(), n, {nullptr, view(off), view(data)}, 0));
}

std::shared_ptr<arrow::Array> nullable_int64(int64_t n, const std::vector<int64_t>& values,
                                             const std::vector<uint8_t>& nulls,
                                             OwnedBuffers& own) {
  int64_t null_count = 0;
  own.bytes.emplace_back((nulls.size() + 7) / 8, 0);
  std::vector<uint8_t>& bm = own.bytes.back();
  for (size_t i = 0; i < nulls.size(); i++) {
    if (nulls[i])
      null_count++;
    else
      bm[i >> 3] |= static_cast<uint8_t>(1u << (i & 7));
  }
  // pyarrow.Array.from_buffers(..., [None if no nulls else bitmap, data], null_count=...)
  std::shared_ptr<arrow::Buffer> validity = null_count ? view(bm) : nullptr;
  return arrow::MakeArray(
      arrow::ArrayData::Make(arrow::int64(), n, {validity, view(values)}, null_count));
}

std::unique_ptr<parquet::arrow::FileWriter> open_writer(
    const std::shared_ptr<arrow::Schema>& schema,
    const std::shared_ptr<arrow::io::OutputStream>& sink) {
  // Frozen H01 physical encoding policy; shared by both journal writers.
  parquet::WriterProperties::Builder props;
  props.data_page_version(parquet::ParquetDataPageVersion::V1);  // data_page_version="1.0"
  props.version(parquet::ParquetVersion::PARQUET_2_6);           // version="2.6"
  props.compression(parquet::Compression::SNAPPY);               // compression="snappy"
  // Numeric columns skip dictionary construction/fallback. The only dictionaries
  // are finite vocabularies: lifecycle/ledger types and lifecycle side.
  props.disable_dictionary();
  props.enable_dictionary("msg_type");
  props.enable_dictionary("side");
  // Consumers read complete journals; statistics do not participate in semantics.
  props.disable_statistics();
  props.max_row_group_length(64 * 1024 * 1024);                  // _MAX_ROW_GROUP_SIZE
  props.disable_page_checksum();                                 // write_page_checksum=False
  props.disable_write_page_index();                              // write_page_index=False
  // _create_arrow_writer_properties(...) with ParquetWriter's defaults (engine "V2")
  parquet::ArrowWriterProperties::Builder aprops;
  aprops.store_schema();
  aprops.disable_deprecated_int96_timestamps();
  aprops.disallow_truncated_timestamps();
  aprops.enable_compliant_nested_types();
  // One process-wide pool, shared by lifecycle and message files. Only column
  // encoding runs here: caller + MessagePipeline dispatcher remain outside the
  // pool, so concurrent WriteRecordBatch calls cannot nest blocking work in it.
  // Simulation + ledger dispatcher + two encoders fit the four-CPU contract.
  static auto encoders = value(arrow::internal::ThreadPool::Make(2));
  aprops.set_use_threads(true);
  aprops.set_executor(encoders.get());

  return value(parquet::arrow::FileWriter::Open(*schema, arrow::default_memory_pool(),
                                               sink, props.build(), aprops.build()));
}
void write_buffered_table(const std::shared_ptr<arrow::Table>& table,
                          parquet::arrow::FileWriter* writer) {
  // Arrow15 WriteTable does not use the executor. Buffered row groups preserve
  // the same per-column encoder and its progressive dictionary/page thresholds.
  // Keep the default 1024 write batch size and the original 1Mi row groups.
  check(table->Validate());  // retain WriteTable's pre-encoding error behavior
  if (table->num_rows() == 0) {
    check(writer->WriteTable(*table, 0));
    return;
  }
  std::vector<std::shared_ptr<arrow::Array>> columns;
  for (const auto& column : table->columns()) columns.push_back(column->chunk(0));
  auto batch = arrow::RecordBatch::Make(table->schema(), table->num_rows(), columns);
  for (int64_t offset = 0; offset < table->num_rows(); offset += kMessageRowGroupRows) {
    check(writer->NewBufferedRowGroup());
    check(writer->WriteRecordBatch(*batch->Slice(
        offset, std::min<int64_t>(kMessageRowGroupRows, table->num_rows() - offset))));
  }
}
void write_table(const std::shared_ptr<arrow::Table>& table, const std::string& path) {
  auto sink = value(arrow::io::FileOutputStream::Open(path));
  auto writer = open_writer(table->schema(), sink);
  write_buffered_table(table, writer.get());
  check(writer->Close());
  check(sink->Close());
}

}  // namespace

namespace {
std::shared_ptr<arrow::Table> trace_table(const TraceColumns& t, OwnedBuffers& own) {
  const int64_t n = static_cast<int64_t>(t.t_ns.size());
  auto schema = arrow::schema(
      {arrow::field("t_ns", arrow::int64()), arrow::field("agent_id", arrow::int32()),
       arrow::field("msg_type", arrow::utf8()), arrow::field("side", arrow::utf8()),
       arrow::field("price", arrow::int64()), arrow::field("size", arrow::int64()),
       arrow::field("order_id", arrow::int64())},
      arrow::key_value_metadata({"pandas"}, {kTraceMeta}));
  auto table = arrow::Table::Make(
      schema, {int_array(arrow::int64(), n, view(t.t_ns)),
               int_array(arrow::int32(), n, view(t.agent_id)),
               string_array(n, t.msg_type, kTraceMsgTypes, own),
               string_array(n, t.side, kSides, own), int_array(arrow::int64(), n, view(t.price)),
               int_array(arrow::int64(), n, view(t.size)),
               int_array(arrow::int64(), n, view(t.order_id))});
  return table;
}
}  // namespace
void write_trace(const TraceColumns& t, const std::string& path) {
  OwnedBuffers own;
  write_table(trace_table(t, own), path);
}

namespace {
std::shared_ptr<arrow::Schema> message_schema() {
  return arrow::schema(
      {arrow::field("seq", arrow::int64()), arrow::field("t_recv_ns", arrow::int64()),
       arrow::field("t_send_ns", arrow::int64()), arrow::field("latency_ns", arrow::int64()),
       arrow::field("src_id", arrow::int32()), arrow::field("dst_id", arrow::int32()),
       arrow::field("message_id", arrow::int64()), arrow::field("msg_type", arrow::utf8()),
       arrow::field("order_id", arrow::int64()), arrow::field("causal_parent", arrow::int64())},
      arrow::key_value_metadata({"pandas"}, {kMsgMeta}));
}
std::shared_ptr<arrow::Table> message_table(const MessageColumns& m, size_t offset,
                                          OwnedBuffers& own, std::vector<int64_t>& seq) {
  const int64_t k = static_cast<int64_t>(m.t_recv.size());
  seq.resize(m.t_recv.size());
  for (size_t i = 0; i < seq.size(); i++) seq[i] = static_cast<int64_t>(offset + i);
  return arrow::Table::Make(
      message_schema(), {int_array(arrow::int64(), k, view(seq)),
               int_array(arrow::int64(), k, view(m.t_recv)),
               nullable_int64(k, m.t_send, m.t_send_null, own),
               int_array(arrow::int64(), k, view(m.latency)),
               int_array(arrow::int32(), k, view(m.src)),
               int_array(arrow::int32(), k, view(m.dst)),
               int_array(arrow::int64(), k, view(m.message_id)),
               string_array(k, m.msg_type, kMsgTypeNames, own),
               nullable_int64(k, m.order_id, m.order_id_null, own),
               nullable_int64(k, m.causal_parent, m.causal_null, own)});
}
}  // namespace
void write_messages(const MessageColumns& m, const std::string& path) {
  OwnedBuffers own;
  std::vector<int64_t> seq;
  auto table = message_table(m, 0, own, seq);
  write_table(table, path);
}
struct MessageParquetWriter::Impl {
  std::shared_ptr<arrow::io::FileOutputStream> sink;
  std::unique_ptr<parquet::arrow::FileWriter> writer;
  bool wrote = false, closed = false, partial = false;
  size_t next_offset = 0;
  explicit Impl(const std::string& path) {
    sink = value(arrow::io::FileOutputStream::Open(path));
    writer = open_writer(message_schema(), sink);
  }
};
MessageParquetWriter::MessageParquetWriter(const std::string& path)
    : impl_(std::make_unique<Impl>(path)) {}
MessageParquetWriter::~MessageParquetWriter() = default;
void MessageParquetWriter::append(const MessageColumns& m, size_t offset) {
  if (impl_->closed || impl_->partial || offset != impl_->next_offset ||
      m.t_recv.empty() || m.t_recv.size() > kMessageBlockRows)
    throw std::runtime_error("invalid message parquet block boundary");
  OwnedBuffers own;
  std::vector<int64_t> seq;
  auto table = message_table(m, offset, own, seq);
  // Manual boundaries keep the original max_row_group_length property (64Mi),
  // while reproducing WriteTable's actual 1Mi row groups. Aligned blocks preserve
  // Arrow15's 1024-row page/dictionary threshold checks across callback boundaries.
  if (offset % kMessageRowGroupRows == 0) check(impl_->writer->NewBufferedRowGroup());
  std::vector<std::shared_ptr<arrow::Array>> columns;
  for (const auto& column : table->columns()) columns.push_back(column->chunk(0));
  auto batch = arrow::RecordBatch::Make(table->schema(), table->num_rows(), columns);
  check(impl_->writer->WriteRecordBatch(*batch));
  impl_->next_offset += m.t_recv.size();
  impl_->wrote = true;
  impl_->partial = m.t_recv.size() < kMessageBlockRows;
}
void MessageParquetWriter::close() {
  if (impl_->closed) return;
  if (!impl_->wrote) {
    // No lifecycle trace can exist without delivered messages; normally cancelled
    // before close. Preserve direct empty-file handling for writer-level callers.
    OwnedBuffers own;
    std::vector<int64_t> seq;
    auto table = message_table(MessageColumns{}, 0, own, seq);
    check(impl_->writer->WriteTable(*table, 0));
  }
  check(impl_->writer->Close());
  check(impl_->sink->Close());
  impl_->closed = true;
}

}  // namespace t3
