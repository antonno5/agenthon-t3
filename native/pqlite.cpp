// See pqlite.hpp. Parquet format references: parquet-format/src/main/thrift/parquet.thrift
// (field ids used below) and Encodings.md (RLE/bit-packing hybrid, PLAIN).
#include "pqlite.hpp"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>

#include "pqmeta.hpp"
#include "sha256_lite.hpp"
#include "snappy_lite.hpp"

namespace t3 {
namespace pqlite {
namespace {

using Bytes = std::vector<uint8_t>;

// ---------------------------------------------------------------------------------------
// Thrift compact protocol (just what the Parquet footer and page headers need)
// ---------------------------------------------------------------------------------------
enum : uint8_t { T_I16 = 4, T_I32 = 5, T_I64 = 6, T_BINARY = 8, T_LIST = 9, T_STRUCT = 12 };

class Thrift {
 public:
  explicit Thrift(Bytes& o) : o_(o) {}
  void i16(int16_t id, int16_t v) { field(id, T_I16); varint(zz(v)); }
  void i32(int16_t id, int32_t v) { field(id, T_I32); varint(zz(v)); }
  void i64(int16_t id, int64_t v) { field(id, T_I64); varint(zz(v)); }
  void str(int16_t id, const std::string& s) { field(id, T_BINARY); raw_str(s); }
  void begin(int16_t id) { field(id, T_STRUCT); push(); }
  void end() { o_.push_back(0); pop(); }
  // List header; for struct elements call elem_begin()/end() per element.
  void list(int16_t id, uint8_t elem_type, size_t n) {
    field(id, T_LIST);
    if (n < 15) {
      o_.push_back(static_cast<uint8_t>((n << 4) | elem_type));
    } else {
      o_.push_back(static_cast<uint8_t>(0xF0 | elem_type));
      varint(n);
    }
  }
  void elem_begin() { push(); }
  void elem_i32(int32_t v) { varint(zz(v)); }
  void raw_str(const std::string& s) {
    varint(s.size());
    o_.insert(o_.end(), s.begin(), s.end());
  }
  void stop() { o_.push_back(0); }  // end of a top-level struct

 private:
  Bytes& o_;
  int16_t last_ = 0;
  std::vector<int16_t> stack_;
  static uint64_t zz(int64_t v) { return (static_cast<uint64_t>(v) << 1) ^ static_cast<uint64_t>(v >> 63); }
  void varint(uint64_t v) {
    while (v >= 0x80) { o_.push_back(static_cast<uint8_t>(v | 0x80)); v >>= 7; }
    o_.push_back(static_cast<uint8_t>(v));
  }
  void field(int16_t id, uint8_t type) {
    const int delta = id - last_;
    if (delta > 0 && delta <= 15) {
      o_.push_back(static_cast<uint8_t>((delta << 4) | type));
    } else {
      o_.push_back(type);
      varint(zz(id));
    }
    last_ = id;
  }
  void push() { stack_.push_back(last_); last_ = 0; }
  void pop() { last_ = stack_.back(); stack_.pop_back(); }
};

// ---------------------------------------------------------------------------------------
// Encodings
// ---------------------------------------------------------------------------------------
void put_uvarint(Bytes& o, uint64_t v) {
  while (v >= 0x80) { o.push_back(static_cast<uint8_t>(v | 0x80)); v >>= 7; }
  o.push_back(static_cast<uint8_t>(v));
}
void put_u32le(Bytes& o, uint32_t v) {
  for (int i = 0; i < 4; i++) o.push_back(static_cast<uint8_t>(v >> (8 * i)));
}

// Definition levels (max level 1) as a length-prefixed RLE/bit-packing hybrid run.
void def_levels(Bytes& o, const uint8_t* nulls, size_t n) {
  Bytes run;
  bool any_null = false;
  if (nulls)
    for (size_t i = 0; i < n && !any_null; i++) any_null = nulls[i] != 0;
  if (!any_null) {
    put_uvarint(run, static_cast<uint64_t>(n) << 1);  // RLE run of n ones
    run.push_back(1);
  } else {
    const size_t groups = (n + 7) / 8;
    put_uvarint(run, (static_cast<uint64_t>(groups) << 1) | 1);  // bit-packed, width 1
    const size_t start = run.size();
    run.resize(start + groups, 0);
    for (size_t i = 0; i < n; i++)
      if (!nulls[i]) run[start + (i >> 3)] |= static_cast<uint8_t>(1u << (i & 7));
  }
  put_u32le(o, static_cast<uint32_t>(run.size()));
  o.insert(o.end(), run.begin(), run.end());
}

// Dictionary indices: bit width byte + one bit-packed run (values LSB-first, padded to 8).
void dict_indices(Bytes& o, const uint8_t* codes, size_t n, int width) {
  o.push_back(static_cast<uint8_t>(width));
  const size_t groups = (n + 7) / 8;
  put_uvarint(o, (static_cast<uint64_t>(groups) << 1) | 1);
  const size_t start = o.size();
  o.resize(start + groups * width, 0);
  size_t bit = 0;
  for (size_t i = 0; i < n; i++, bit += width) {
    const uint32_t v = codes[i];
    for (int b = 0; b < width; b++)
      if (v & (1u << b)) o[start + ((bit + b) >> 3)] |= static_cast<uint8_t>(1u << ((bit + b) & 7));
  }
}

int bit_width(size_t max_value) {
  int w = 0;
  while ((size_t{1} << w) <= max_value) w++;
  return std::max(w, 1);
}

// ---------------------------------------------------------------------------------------
// Columns and pages
// ---------------------------------------------------------------------------------------
enum PhysType : int32_t { PT_INT32 = 1, PT_INT64 = 2, PT_BYTE_ARRAY = 6 };

struct Column {
  std::string name;
  int32_t type;
  const char* const* vocab = nullptr;  // dictionary-encoded string column when set
  size_t vocab_n = 0;
  // Encoded chunk: [dictionary page][data pages...]
  Bytes dict_page, pages;
  int64_t num_values = 0, uncompressed = 0;
};

void page_header(Bytes& o, bool dictionary, int32_t unc, int32_t comp, int32_t num_values,
                 int32_t encoding) {
  Thrift t(o);
  t.i32(1, dictionary ? 2 : 0);  // PageType DICTIONARY_PAGE / DATA_PAGE
  t.i32(2, unc);
  t.i32(3, comp);
  if (dictionary) {
    t.begin(7);  // DictionaryPageHeader
    t.i32(1, num_values);
    t.i32(2, 0);  // PLAIN
    t.end();
  } else {
    t.begin(5);  // DataPageHeader
    t.i32(1, num_values);
    t.i32(2, encoding);
    t.i32(3, 3);  // definition levels: RLE
    t.i32(4, 3);  // repetition levels: RLE (none present)
    t.end();
  }
  t.stop();
}

// Compresses `body` into a page appended to `out`; returns header+uncompressed size.
int64_t add_page(Bytes& out, const Bytes& body, bool dictionary, int32_t num_values,
                 int32_t encoding) {
  Bytes comp;
  snappy_lite::compress(body.data(), body.size(), comp);
  Bytes header;
  page_header(header, dictionary, static_cast<int32_t>(body.size()),
              static_cast<int32_t>(comp.size()), num_values, encoding);
  out.insert(out.end(), header.begin(), header.end());
  out.insert(out.end(), comp.begin(), comp.end());
  return static_cast<int64_t>(header.size() + body.size());
}

void ensure_dict_page(Column& c) {
  if (!c.vocab || !c.dict_page.empty()) return;
  Bytes body;
  for (size_t i = 0; i < c.vocab_n; i++) {
    const uint32_t len = static_cast<uint32_t>(std::strlen(c.vocab[i]));
    put_u32le(body, len);
    body.insert(body.end(), c.vocab[i], c.vocab[i] + len);
  }
  c.uncompressed += add_page(c.dict_page, body, true, static_cast<int32_t>(c.vocab_n), 0);
}

template <class T>
void numeric_page(Column& c, const T* v, const uint8_t* nulls, size_t n) {
  Bytes body;
  def_levels(body, nulls, n);
  const size_t start = body.size();
  size_t valid = 0;
  for (size_t i = 0; i < n; i++) valid += !(nulls && nulls[i]);
  body.resize(start + valid * sizeof(T));
  uint8_t* dst = body.data() + start;
  if (!nulls) {
    std::memcpy(dst, v, n * sizeof(T));  // x86-64 is little-endian, as PLAIN requires
  } else {
    for (size_t i = 0; i < n; i++)
      if (!nulls[i]) { std::memcpy(dst, &v[i], sizeof(T)); dst += sizeof(T); }
  }
  c.uncompressed += add_page(c.pages, body, false, static_cast<int32_t>(n), 0);
  c.num_values += static_cast<int64_t>(n);
}

void string_page(Column& c, const uint8_t* codes, size_t n) {
  ensure_dict_page(c);
  Bytes body;
  def_levels(body, nullptr, n);
  dict_indices(body, codes, n, bit_width(c.vocab_n - 1));
  c.uncompressed += add_page(c.pages, body, false, static_cast<int32_t>(n), 8);  // RLE_DICTIONARY
  c.num_values += static_cast<int64_t>(n);
}

// Runs fn(i) for i in [0, n) on up to `threads` threads (the platform grants 4 CPUs).
template <class F>
void parallel_for(size_t n, size_t threads, F fn) {
  threads = std::min(threads, n);
  if (threads <= 1) {
    for (size_t i = 0; i < n; i++) fn(i);
    return;
  }
  std::vector<std::thread> pool;
  std::vector<std::exception_ptr> errors(threads);
  for (size_t t = 0; t < threads; t++)
    pool.emplace_back([&, t] {
      try {
        for (size_t i = t; i < n; i += threads) fn(i);
      } catch (...) {
        errors[t] = std::current_exception();
      }
    });
  for (auto& th : pool) th.join();
  for (auto& e : errors)
    if (e) std::rethrow_exception(e);
}

// Builds the file in memory, writes it and returns its SHA-256 (computed concurrently).
std::string write_file(const std::string& path, std::vector<Column>& cols, int64_t num_rows,
                       const char* arrow_schema, const char* pandas) {
  Bytes file;
  size_t total = 8;
  for (auto& c : cols) total += c.dict_page.size() + c.pages.size();
  file.reserve(total + 4096);
  const uint8_t magic[4] = {'P', 'A', 'R', '1'};
  file.insert(file.end(), magic, magic + 4);
  struct Placed { int64_t start, data_offset, size; };
  std::vector<Placed> placed;
  for (auto& c : cols) {
    Placed p;
    p.start = static_cast<int64_t>(file.size());
    file.insert(file.end(), c.dict_page.begin(), c.dict_page.end());
    p.data_offset = static_cast<int64_t>(file.size());
    file.insert(file.end(), c.pages.begin(), c.pages.end());
    p.size = static_cast<int64_t>(file.size()) - p.start;
    placed.push_back(p);
  }
  const size_t footer_start = file.size();
  {
    Thrift t(file);
    t.i32(1, 2);  // version
    t.list(2, T_STRUCT, cols.size() + 1);
    t.elem_begin();  // root
    t.str(4, "schema");
    t.i32(5, static_cast<int32_t>(cols.size()));
    t.end();
    for (auto& c : cols) {
      t.elem_begin();
      t.i32(1, c.type);
      t.i32(3, 1);  // OPTIONAL
      t.str(4, c.name);
      if (c.type == PT_BYTE_ARRAY) {
        t.i32(6, 0);  // ConvertedType UTF8
        t.begin(10);  // LogicalType
        t.begin(1);   // STRING
        t.end();
        t.end();
      }
      t.end();
    }
    t.i64(3, num_rows);
    t.list(4, T_STRUCT, 1);
    t.elem_begin();  // RowGroup
    t.list(1, T_STRUCT, cols.size());
    int64_t rg_unc = 0, rg_comp = 0;
    for (size_t i = 0; i < cols.size(); i++) {
      const Column& c = cols[i];
      const Placed& p = placed[i];
      t.elem_begin();  // ColumnChunk
      t.i64(2, p.start);
      t.begin(3);  // ColumnMetaData
      t.i32(1, c.type);
      if (c.vocab) {
        t.list(2, T_I32, 3);
        t.elem_i32(0); t.elem_i32(3); t.elem_i32(8);  // PLAIN, RLE, RLE_DICTIONARY
      } else {
        t.list(2, T_I32, 2);
        t.elem_i32(3); t.elem_i32(0);  // RLE, PLAIN
      }
      t.list(3, T_BINARY, 1);
      t.raw_str(c.name);
      t.i32(4, 1);  // SNAPPY
      t.i64(5, c.num_values);
      t.i64(6, c.uncompressed);
      t.i64(7, p.size);
      t.i64(9, p.data_offset);
      if (c.vocab) t.i64(11, p.start);
      t.end();
      t.end();
      rg_unc += c.uncompressed;
      rg_comp += p.size;
    }
    t.i64(2, rg_unc);
    t.i64(3, num_rows);
    t.i64(5, 4);
    t.i64(6, rg_comp);
    t.i16(7, 0);
    t.end();
    t.list(5, T_STRUCT, 2);
    t.elem_begin(); t.str(1, "ARROW:schema"); t.str(2, arrow_schema); t.end();
    t.elem_begin(); t.str(1, "pandas"); t.str(2, pandas); t.end();
    t.str(6, "parquet-cpp-arrow version 15.0.2");
    t.list(7, T_STRUCT, cols.size());
    for (size_t i = 0; i < cols.size(); i++) {
      t.elem_begin();
      t.begin(1);  // TYPE_ORDER
      t.end();
      t.end();
    }
    t.stop();
  }
  put_u32le(file, static_cast<uint32_t>(file.size() - footer_start));
  file.insert(file.end(), magic, magic + 4);

  std::string hex;
  std::thread hasher([&] {
    sha256_lite::Sha256 s;
    s.update(file.data(), file.size());
    hex = s.hex();
  });
  FILE* f = std::fopen(path.c_str(), "wb");
  const bool ok = f && std::fwrite(file.data(), 1, file.size(), f) == file.size();
  const bool closed = f && std::fclose(f) == 0;
  hasher.join();
  if (!ok || !closed) throw std::runtime_error("cannot write " + path);
  return hex;
}

const char* const kTraceMsgTypes[] = {"ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED",
                                      "PARTIAL_FILL",    "ORDER_FILLED",   "QUOTE_UPDATE"};
const char* const kSides[] = {"BID", "ASK"};
constexpr size_t kTracePageRows = 64 * 1024;

}  // namespace

std::string write_trace(const TraceColumns& t, const std::string& path) {
  std::vector<Column> cols(7);
  cols[0] = {"t_ns", PT_INT64};
  cols[1] = {"agent_id", PT_INT32};
  cols[2] = {"msg_type", PT_BYTE_ARRAY, kTraceMsgTypes, 6};
  cols[3] = {"side", PT_BYTE_ARRAY, kSides, 2};
  cols[4] = {"price", PT_INT64};
  cols[5] = {"size", PT_INT64};
  cols[6] = {"order_id", PT_INT64};
  const size_t n = t.t_ns.size();
  parallel_for(cols.size(), 4, [&](size_t ci) {
    for (size_t off = 0; off < n || (off == 0 && n == 0); off += kTracePageRows) {
      const size_t k = std::min(kTracePageRows, n - off);
      switch (ci) {
        case 0: numeric_page(cols[0], t.t_ns.data() + off, nullptr, k); break;
        case 1: numeric_page(cols[1], t.agent_id.data() + off, nullptr, k); break;
        case 2: string_page(cols[2], t.msg_type.data() + off, k); break;
        case 3: string_page(cols[3], t.side.data() + off, k); break;
        case 4: numeric_page(cols[4], t.price.data() + off, nullptr, k); break;
        case 5: numeric_page(cols[5], t.size.data() + off, nullptr, k); break;
        case 6: numeric_page(cols[6], t.order_id.data() + off, nullptr, k); break;
      }
      if (n == 0) break;
    }
  });
  return write_file(path, cols, static_cast<int64_t>(n), pqmeta::kTraceArrowSchema,
                    pqmeta::kTracePandas);
}

struct MessageWriter::Impl {
  std::string path;
  std::vector<Column> cols;
  int64_t rows = 0;
};

MessageWriter::MessageWriter(std::string path) : impl_(new Impl) {
  impl_->path = std::move(path);
  auto& c = impl_->cols;
  c.resize(10);
  c[0] = {"seq", PT_INT64};
  c[1] = {"t_recv_ns", PT_INT64};
  c[2] = {"t_send_ns", PT_INT64};
  c[3] = {"latency_ns", PT_INT64};
  c[4] = {"src_id", PT_INT32};
  c[5] = {"dst_id", PT_INT32};
  c[6] = {"message_id", PT_INT64};
  c[7] = {"msg_type", PT_BYTE_ARRAY, kMsgTypeNames, MT_COUNT};
  c[8] = {"order_id", PT_INT64};
  c[9] = {"causal_parent", PT_INT64};
}

MessageWriter::~MessageWriter() = default;

void MessageWriter::append(const MessageColumns& m, size_t seq_offset) {
  const size_t n = m.t_recv.size();
  if (n == 0) return;
  std::vector<int64_t> seq(n);
  for (size_t i = 0; i < n; i++) seq[i] = static_cast<int64_t>(seq_offset + i);
  auto& c = impl_->cols;
  parallel_for(c.size(), 3, [&](size_t ci) {
    switch (ci) {
      case 0: numeric_page(c[0], seq.data(), nullptr, n); break;
      case 1: numeric_page(c[1], m.t_recv.data(), nullptr, n); break;
      case 2: numeric_page(c[2], m.t_send.data(), m.t_send_null.data(), n); break;
      case 3: numeric_page(c[3], m.latency.data(), nullptr, n); break;
      case 4: numeric_page(c[4], m.src.data(), nullptr, n); break;
      case 5: numeric_page(c[5], m.dst.data(), nullptr, n); break;
      case 6: numeric_page(c[6], m.message_id.data(), nullptr, n); break;
      case 7: string_page(c[7], m.msg_type.data(), n); break;
      case 8: numeric_page(c[8], m.order_id.data(), m.order_id_null.data(), n); break;
      case 9: numeric_page(c[9], m.causal_parent.data(), m.causal_null.data(), n); break;
    }
  });
  impl_->rows += static_cast<int64_t>(n);
}

std::string MessageWriter::close() {
  return write_file(impl_->path, impl_->cols, impl_->rows, pqmeta::kMessagesArrowSchema,
                    pqmeta::kMessagesPandas);
}

}  // namespace pqlite
}  // namespace t3
