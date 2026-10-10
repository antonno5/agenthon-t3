// See pqlite.hpp. Parquet format references: parquet-format/src/main/thrift/parquet.thrift
// (field ids used below) and Encodings.md (RLE/bit-packing hybrid, PLAIN).
#include "pqlite.hpp"

#include <algorithm>
#include <condition_variable>
#include <mutex>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <vector>

#include "pqmeta.hpp"
#include "sha256_lite.hpp"

#include <fcntl.h>
#include <limits.h>
#include <sys/mman.h>
#include <sys/uio.h>
#include <unistd.h>
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
  // Each group of 8 values packs into exactly `width` bytes: assemble it in a 64-bit word.
  uint8_t* dst = o.data() + start;
  for (size_t g = 0; g < groups; g++) {
    uint64_t word = 0;
    const size_t base = g * 8;
    for (size_t k = 0; k < 8 && base + k < n; k++)
      word |= static_cast<uint64_t>(codes[base + k]) << (k * static_cast<size_t>(width));
    std::memcpy(dst, &word, static_cast<size_t>(width));  // little-endian: low bytes first
    dst += width;
  }
}

// DELTA_BINARY_PACKED (Parquet Encodings.md): header <block size 128> <4 miniblocks>
// <value count> <first value zigzag>; per block <min delta zigzag> <4 bit widths> and the
// (delta - min_delta) values bit-packed LSB-first, 32 per miniblock. Deltas wrap like the
// reference implementation (two's-complement int64), so any int64 sequence round-trips.
void put_zigzag(Bytes& o, int64_t v) {
  put_uvarint(o, (static_cast<uint64_t>(v) << 1) ^ static_cast<uint64_t>(v >> 63));
}
void pack_bits(Bytes& o, const uint64_t* v, size_t count, int width) {
  if (width == 0) return;
  const size_t start = o.size();
  o.resize(start + (count * static_cast<size_t>(width) + 7) / 8);
  uint8_t* dst = o.data() + start;
  if (width <= 32) {
    // Common case: a 64-bit accumulator, flushed 4 bytes at a time.
    const uint64_t m = (width == 32) ? 0xffffffffull : ((1ull << width) - 1);
    uint64_t acc = 0;
    int bits = 0;
    for (size_t i = 0; i < count; i++) {
      acc |= (v[i] & m) << bits;
      bits += width;
      if (bits >= 32) {
        const uint32_t lo = static_cast<uint32_t>(acc);
        std::memcpy(dst, &lo, 4);
        dst += 4;
        acc >>= 32;
        bits -= 32;
      }
    }
    while (bits > 0) {
      *dst++ = static_cast<uint8_t>(acc);
      acc >>= 8;
      bits -= 8;
    }
    return;
  }
  // LSB-first bit stream through a 128-bit accumulator (widths up to 64).
  unsigned __int128 acc = 0;
  int bits = 0;
  const unsigned __int128 mask = (width == 64) ? ~static_cast<uint64_t>(0) : ((static_cast<uint64_t>(1) << width) - 1);
  for (size_t i = 0; i < count; i++) {
    acc |= (static_cast<unsigned __int128>(v[i]) & mask) << bits;
    bits += width;
    while (bits >= 8) {
      *dst++ = static_cast<uint8_t>(acc);
      acc >>= 8;
      bits -= 8;
    }
  }
  if (bits > 0) *dst++ = static_cast<uint8_t>(acc);
}

template <class T>
void delta_binary_packed(Bytes& o, const T* v, size_t n) {
  constexpr size_t kBlock = 128, kMini = 4, kPer = kBlock / kMini;
  put_uvarint(o, kBlock);
  put_uvarint(o, kMini);
  put_uvarint(o, n);
  put_zigzag(o, n ? static_cast<int64_t>(v[0]) : 0);
  uint64_t d[kBlock];
  for (size_t i = 1; i < n; i += kBlock) {
    const size_t cnt = std::min(kBlock, n - i);
    int64_t min_delta = 0;
    for (size_t k = 0; k < cnt; k++) {
      // wrapping difference in the column's own width, widened like the reader does
      const int64_t delta = static_cast<int64_t>(static_cast<T>(
          static_cast<std::make_unsigned_t<T>>(v[i + k]) - static_cast<std::make_unsigned_t<T>>(v[i + k - 1])));
      d[k] = static_cast<uint64_t>(delta);
      if (k == 0 || delta < min_delta) min_delta = delta;
    }
    put_zigzag(o, min_delta);
    int widths[kMini] = {0, 0, 0, 0};
    for (size_t m = 0; m < kMini; m++) {
      uint64_t mx = 0;
      for (size_t k = m * kPer; k < std::min(cnt, (m + 1) * kPer); k++) {
        d[k] = d[k] - static_cast<uint64_t>(min_delta);
        mx |= d[k];
      }
      int w = 0;
      while (w < 64 && (mx >> w) != 0) w++;
      widths[m] = m * kPer < cnt ? w : 0;
    }
    for (size_t m = 0; m < kMini; m++) o.push_back(static_cast<uint8_t>(widths[m]));
    for (size_t m = 0; m < kMini && m * kPer < cnt; m++) {
      uint64_t tmp[kPer] = {0};
      for (size_t k = 0; k < kPer && m * kPer + k < cnt; k++) tmp[k] = d[m * kPer + k];
      pack_bits(o, tmp, kPer, widths[m]);  // a partial last miniblock is padded to 32 values
    }
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
  // Encoded chunk: [dictionary page][data pages...], each page kept as its own buffers
  // (header, compressed body) and written in order -- never concatenated in memory.
  std::vector<Bytes> dict_page, pages;
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
int64_t add_page(std::vector<Bytes>& out, const Bytes& body, bool dictionary,
                 int32_t num_values, int32_t encoding) {
  Bytes comp;
  comp.reserve(32 + body.size() + body.size() / 6);  // snappy worst case: no growth
  snappy_lite::compress(body.data(), body.size(), comp);
  Bytes header;
  page_header(header, dictionary, static_cast<int32_t>(body.size()),
              static_cast<int32_t>(comp.size()), num_values, encoding);
  const int64_t unc = static_cast<int64_t>(header.size() + body.size());
  out.push_back(std::move(header));
  out.push_back(std::move(comp));
  return unc;
}
size_t bytes_of(const std::vector<Bytes>& v) {
  size_t n = 0;
  for (const Bytes& b : v) n += b.size();
  return n;
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
  body.reserve(64 + n / 8 + n * (sizeof(T) + 1) + n / 32);  // levels + worst-case delta
  def_levels(body, nulls, n);
  if (!nulls) {
    delta_binary_packed(body, v, n);
  } else {
    std::vector<T> present;
    present.reserve(n);
    for (size_t i = 0; i < n; i++)
      if (!nulls[i]) present.push_back(v[i]);
    delta_binary_packed(body, present.data(), present.size());
  }
  c.uncompressed += add_page(c.pages, body, false, static_cast<int32_t>(n), 5);  // DELTA_BINARY_PACKED
  c.num_values += static_cast<int64_t>(n);
}

void string_page(Column& c, const uint8_t* codes, size_t n) {
  ensure_dict_page(c);
  Bytes body;
  body.reserve(64 + n);
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

// Where a column chunk lies in the file.
struct Placed { int64_t start, data_offset, size; };

// The file footer for row groups whose column chunks may lie anywhere in the file:
// rgs[g][ci] is the chunk of column ci in row group g (pages may already be released, the
// counts are kept), placed[g][ci] where it was written, rows[g] its row count.
Bytes footer_bytes(const std::vector<std::vector<Column>>& rgs,
                   const std::vector<std::vector<Placed>>& placed, const std::vector<int64_t>& rows,
                   const char* arrow_schema, const char* pandas) {
  static const uint8_t magic[4] = {'P', 'A', 'R', '1'};
  const std::vector<Column>& cols = rgs.front();
  int64_t num_rows = 0;
  for (int64_t r : rows) num_rows += r;
  Bytes footer;
  {
    Thrift t(footer);
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
    t.list(4, T_STRUCT, rgs.size());
    for (size_t g = 0; g < rgs.size(); g++) {
      t.elem_begin();  // RowGroup
      t.list(1, T_STRUCT, cols.size());
      int64_t rg_unc = 0, rg_comp = 0;
      for (size_t i = 0; i < cols.size(); i++) {
        const Column& c = rgs[g][i];
        const Placed& p = placed[g][i];
        t.elem_begin();  // ColumnChunk
        t.i64(2, p.start);
        t.begin(3);  // ColumnMetaData
        t.i32(1, c.type);
        if (c.vocab) {
          t.list(2, T_I32, 3);
          t.elem_i32(0); t.elem_i32(3); t.elem_i32(8);  // PLAIN, RLE, RLE_DICTIONARY
        } else {
          t.list(2, T_I32, 2);
          t.elem_i32(3); t.elem_i32(5);  // RLE, DELTA_BINARY_PACKED
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
      t.i64(3, rows[g]);
      t.i64(5, placed[g][0].start);
      t.i64(6, rg_comp);
      t.i16(7, static_cast<int16_t>(g));
      t.end();
    }
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
  put_u32le(footer, static_cast<uint32_t>(footer.size()));
  footer.insert(footer.end(), magic, magic + 4);
  return footer;
}

// Writes the file from the column page buffers in order (no concatenation), hashing the same
// pieces on a second thread; returns the SHA-256 hex. One row group.
std::string write_file(const std::string& path, std::vector<Column>& cols, int64_t num_rows,
                       const char* arrow_schema, const char* pandas) {
  static const uint8_t magic[4] = {'P', 'A', 'R', '1'};
  std::vector<Placed> placed;
  int64_t pos = 4;
  for (auto& c : cols) {
    Placed p;
    p.start = pos;
    pos += static_cast<int64_t>(bytes_of(c.dict_page));
    p.data_offset = pos;
    pos += static_cast<int64_t>(bytes_of(c.pages));
    p.size = pos - p.start;
    placed.push_back(p);
  }
  const Bytes footer = footer_bytes({cols}, {placed}, {num_rows}, arrow_schema, pandas);

  // Ordered list of byte ranges making up the file.
  std::vector<std::pair<const uint8_t*, size_t>> pieces;
  pieces.emplace_back(magic, 4);
  for (auto& c : cols) {
    for (const Bytes& b : c.dict_page) pieces.emplace_back(b.data(), b.size());
    for (const Bytes& b : c.pages) pieces.emplace_back(b.data(), b.size());
  }
  pieces.emplace_back(footer.data(), footer.size());

  std::string hex;
  std::thread hasher([&] {
    sha256_lite::Sha256 s;
    for (const auto& pc : pieces) s.update(pc.first, pc.second);
    hex = s.hex();
  });
  FILE* f = std::fopen(path.c_str(), "wb");
  bool ok = f != nullptr;
  if (ok) {
    static thread_local std::vector<char> iobuf(1 << 20);
    std::setvbuf(f, iobuf.data(), _IOFBF, iobuf.size());
    for (const auto& pc : pieces)
      if (std::fwrite(pc.first, 1, pc.second, f) != pc.second) { ok = false; break; }
  }
  const bool closed = f && std::fclose(f) == 0;
  hasher.join();
  if (!ok || !closed) throw std::runtime_error("cannot write " + path);
  return hex;
}

// A file written front to back while it is still being encoded: put() places a column chunk
// at the current end of the file and hands its pages to a writer thread, which writes and
// hashes them in order (and frees them); finish() appends the footer and returns the SHA-256
// hex. The chunk's counts stay with the caller for the footer.
class StreamFile {
 public:
  explicit StreamFile(std::string path) : path_(std::move(path)) {
    worker_ = std::thread([this] { run(); });
  }
  ~StreamFile() {
    if (worker_.joinable()) {
      { std::lock_guard<std::mutex> l(m_); done_ = true; }
      cv_.notify_one();
      worker_.join();
    }
  }
  Placed put(Column& c) {
    Placed p;
    p.start = pos_;
    pos_ += static_cast<int64_t>(bytes_of(c.dict_page));
    p.data_offset = pos_;
    pos_ += static_cast<int64_t>(bytes_of(c.pages));
    p.size = pos_ - p.start;
    std::vector<Bytes> pieces = std::move(c.dict_page);
    for (Bytes& b : c.pages) pieces.push_back(std::move(b));
    c.dict_page.clear();
    c.pages.clear();
    {
      std::lock_guard<std::mutex> l(m_);
      queue_.push_back(std::move(pieces));
    }
    cv_.notify_one();
    return p;
  }
  std::string finish(Bytes footer) {
    {
      std::lock_guard<std::mutex> l(m_);
      queue_.push_back({std::move(footer)});
      done_ = true;
    }
    cv_.notify_one();
    worker_.join();
    if (!ok_) throw std::runtime_error("cannot write " + path_);
    return hex_;
  }

 private:
  std::string path_;
  int64_t pos_ = 4;  // after the leading magic
  std::thread worker_;
  std::mutex m_;
  std::condition_variable cv_;
  std::vector<std::vector<Bytes>> queue_;
  bool done_ = false, ok_ = true;
  std::string hex_;

  void run() {
    static const uint8_t magic[4] = {'P', 'A', 'R', '1'};
    sha256_lite::Sha256 sha;
    // Plain write(2) per queued batch, no stdio buffer: the bytes reach the file while the
    // run goes on, so close() only waits for the last row group and the footer.
    const int fd = ::open(path_.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0666);
    ok_ = fd >= 0;
    std::vector<iovec> iov;
    auto write_all = [&](const std::vector<std::vector<Bytes>>& batch) {
      iov.clear();
      for (const auto& pieces : batch)
        for (const Bytes& b : pieces) {
          sha.update(b.data(), b.size());
          if (!b.empty()) iov.push_back({const_cast<uint8_t*>(b.data()), b.size()});
        }
      for (size_t i = 0; ok_ && i < iov.size();) {
        const int n = static_cast<int>(std::min<size_t>(iov.size() - i, IOV_MAX));
        ssize_t w = ::writev(fd, iov.data() + i, n);
        if (w < 0) { ok_ = false; break; }
        // Skip what was written (a short write resumes inside an iovec).
        while (w > 0 && i < iov.size()) {
          if (static_cast<size_t>(w) >= iov[i].iov_len) { w -= iov[i].iov_len; i++; }
          else { iov[i].iov_base = static_cast<uint8_t*>(iov[i].iov_base) + w; iov[i].iov_len -= w; w = 0; }
        }
      }
    };
    write_all({{Bytes(magic, magic + 4)}});
    for (;;) {
      std::vector<std::vector<Bytes>> batch;
      bool last;
      {
        std::unique_lock<std::mutex> l(m_);
        cv_.wait(l, [this] { return done_ || !queue_.empty(); });
        batch.swap(queue_);
        last = done_;
      }
      write_all(batch);
      if (last) break;
    }
    if (fd >= 0 && ::close(fd) != 0) ok_ = false;
    hex_ = sha.hex();
  }
};

const char* const kTraceMsgTypes[] = {"ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED",
                                      "PARTIAL_FILL",    "ORDER_FILLED",   "QUOTE_UPDATE"};
const char* const kSides[] = {"BID", "ASK"};
constexpr size_t kTracePageRows = 64 * 1024;
// Row group size of the streamed trace: small, so close() has little left to encode.
constexpr size_t kTraceGroupRows = 16 * 1024;

}  // namespace

namespace {
std::vector<Column> trace_columns() {
  std::vector<Column> cols(7);
  cols[0] = {"t_ns", PT_INT64};
  cols[1] = {"agent_id", PT_INT32};
  cols[2] = {"msg_type", PT_BYTE_ARRAY, kTraceMsgTypes, 6};
  cols[3] = {"side", PT_BYTE_ARRAY, kSides, 2};
  cols[4] = {"price", PT_INT64};
  cols[5] = {"size", PT_INT64};
  cols[6] = {"order_id", PT_INT64};
  return cols;
}
// Encodes the trace page [off, off + k) of column ci.
void trace_page(std::vector<Column>& cols, const TraceColumns& t, size_t ci, size_t off, size_t k) {
  switch (ci) {
    case 0: numeric_page(cols[0], t.t_ns.data() + off, nullptr, k); break;
    case 1: numeric_page(cols[1], t.agent_id.data() + off, nullptr, k); break;
    case 2: string_page(cols[2], t.msg_type.data() + off, k); break;
    case 3: string_page(cols[3], t.side.data() + off, k); break;
    case 4: numeric_page(cols[4], t.price.data() + off, nullptr, k); break;
    case 5: numeric_page(cols[5], t.size.data() + off, nullptr, k); break;
    case 6: numeric_page(cols[6], t.order_id.data() + off, nullptr, k); break;
  }
}
// Encodes the pages of column ci from row `from` (a page boundary) to the end.
void trace_pages_from(std::vector<Column>& cols, const TraceColumns& t, size_t ci, size_t from) {
  const size_t n = t.t_ns.size();
  for (size_t off = from; off < n || (off == 0 && n == 0); off += kTracePageRows) {
    trace_page(cols, t, ci, off, std::min(kTracePageRows, n - off));
    if (n == 0) break;
  }
}
}  // namespace

std::string write_trace(const TraceColumns& t, const std::string& path) {
  std::vector<Column> cols = trace_columns();
  parallel_for(cols.size(), 4, [&](size_t ci) { trace_pages_from(cols, t, ci, 0); });
  return write_file(path, cols, static_cast<int64_t>(t.t_ns.size()), pqmeta::kTraceArrowSchema,
                    pqmeta::kTracePandas);
}

// Every kTraceGroupRows rows become a row group, written as soon as its final columns
// are encoded; msg_type (which can still change) is encoded per row group at close() and its
// chunks follow all the others. The file decodes to the same table as write_trace()'s.
struct TraceWriter::Impl {
  std::string path;
  std::unique_ptr<StreamFile> file;
  size_t encoded = 0;  // rows already in a row group (a multiple of kTraceGroupRows)
  std::vector<std::vector<Column>> rgs;
  std::vector<std::vector<Placed>> placed;
  std::vector<int64_t> rows;
  // Encodes rows [off, off + k) of every column but msg_type as a new row group and queues it.
  void row_group(const TraceColumns& t, size_t off, size_t k, bool parallel) {
    if (!file) file = std::make_unique<StreamFile>(path);
    rgs.push_back(trace_columns());
    std::vector<Column>& cols = rgs.back();
    auto encode = [&](size_t ci) { if (ci != 2) trace_page(cols, t, ci, off, k); };
    if (parallel)
      parallel_for(cols.size(), 4, encode);
    else
      for (size_t ci = 0; ci < cols.size(); ci++) encode(ci);
    placed.emplace_back(cols.size());
    for (size_t ci = 0; ci < cols.size(); ci++)
      if (ci != 2) placed.back()[ci] = file->put(cols[ci]);
    rows.push_back(static_cast<int64_t>(k));
  }
};

// Returns the memory of rows [from, to) of a column to the OS. Only for rows that are encoded
// and never read again: nothing reads a trace value after its page is encoded except msg_type
// (a later execution can still change it), and the process exits right after the file is
// written -- so the exit no longer has to free tens of MB on the largest runs.
template <class T>
void release_rows(const std::vector<T>& v, size_t from, size_t to) {
  constexpr uintptr_t kPage = 4096;
  const uintptr_t base = reinterpret_cast<uintptr_t>(v.data());
  const uintptr_t lo = (base + from * sizeof(T) + kPage - 1) & ~(kPage - 1);
  const uintptr_t hi = (base + to * sizeof(T)) & ~(kPage - 1);
  if (hi > lo) madvise(reinterpret_cast<void*>(lo), hi - lo, MADV_DONTNEED);
}

TraceWriter::TraceWriter(std::string path) : impl_(new Impl) { impl_->path = std::move(path); }
TraceWriter::~TraceWriter() = default;

void TraceWriter::rows_final(const TraceColumns& t, size_t n) {
  Impl& w = *impl_;
  const size_t before = w.encoded;
  for (; w.encoded + kTraceGroupRows <= n; w.encoded += kTraceGroupRows)
    w.row_group(t, w.encoded, kTraceGroupRows, false);
  if (w.encoded > before) {
    release_rows(t.t_ns, before, w.encoded);
    release_rows(t.agent_id, before, w.encoded);
    release_rows(t.side, before, w.encoded);
    release_rows(t.price, before, w.encoded);
    release_rows(t.size, before, w.encoded);
    release_rows(t.order_id, before, w.encoded);
  }
}

std::string TraceWriter::close(const TraceColumns& t) {
  Impl& w = *impl_;
  const size_t n = t.t_ns.size();
  if (n == 0) return write_trace(t, w.path);  // nothing streamed: one empty page per column
  if (w.encoded < n) w.row_group(t, w.encoded, n - w.encoded, n - w.encoded > kTraceGroupRows);
  parallel_for(w.rgs.size(), 4, [&](size_t g) {
    trace_page(w.rgs[g], t, 2, g * kTraceGroupRows, static_cast<size_t>(w.rows[g]));
  });
  for (size_t g = 0; g < w.rgs.size(); g++) w.placed[g][2] = w.file->put(w.rgs[g][2]);
  return w.file->finish(footer_bytes(w.rgs, w.placed, w.rows, pqmeta::kTraceArrowSchema,
                                     pqmeta::kTracePandas));
}

// Every appended block becomes its own row group, written while the run goes on; close()
// only adds the footer.
struct MessageWriter::Impl {
  std::string path;
  std::vector<Column> cols;
  std::unique_ptr<StreamFile> file;
  std::vector<std::vector<Column>> rgs;
  std::vector<std::vector<Placed>> placed;
  std::vector<int64_t> rows;
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
  Impl& w = *impl_;
  if (!w.file) w.file = std::make_unique<StreamFile>(w.path);
  std::vector<int64_t> seq(n);
  for (size_t i = 0; i < n; i++) seq[i] = static_cast<int64_t>(seq_offset + i);
  w.rgs.push_back(w.cols);  // empty chunks with the column names and types
  auto& c = w.rgs.back();
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
  w.placed.emplace_back();
  for (Column& col : c) w.placed.back().push_back(w.file->put(col));
  w.rows.push_back(static_cast<int64_t>(n));
}

std::string MessageWriter::close() {
  Impl& w = *impl_;
  if (!w.file)  // no rows: one empty page per column, as before
    return write_file(w.path, w.cols, 0, pqmeta::kMessagesArrowSchema, pqmeta::kMessagesPandas);
  return w.file->finish(footer_bytes(w.rgs, w.placed, w.rows, pqmeta::kMessagesArrowSchema,
                                     pqmeta::kMessagesPandas));
}

}  // namespace pqlite
}  // namespace t3
