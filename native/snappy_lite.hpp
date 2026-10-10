// Minimal Snappy *compressor* (raw block format: varint length + literal/copy elements, as
// in https://github.com/google/snappy/blob/main/format_description.txt). Any valid
// encoding decompresses to the same bytes, so this need not match libsnappy's choices; the
// stream is consumed by the standard Parquet readers' snappy decompressor.
// Greedy 4-byte hash matching inside 64 KiB fragments (all copy offsets < 65536).
#pragma once

#include <cstdint>
#include <cstring>
#include <vector>

namespace t3 {
namespace snappy_lite {

inline void put_varint32(std::vector<uint8_t>& o, uint32_t v) {
  while (v >= 0x80) {
    o.push_back(static_cast<uint8_t>(v | 0x80));
    v >>= 7;
  }
  o.push_back(static_cast<uint8_t>(v));
}

inline void emit_literal(std::vector<uint8_t>& o, const uint8_t* p, size_t n) {
  if (n == 0) return;
  const uint32_t m = static_cast<uint32_t>(n - 1);
  if (m < 60) {
    o.push_back(static_cast<uint8_t>(m << 2));
  } else {
    int bytes = m < (1u << 8) ? 1 : m < (1u << 16) ? 2 : m < (1u << 24) ? 3 : 4;
    o.push_back(static_cast<uint8_t>((59 + bytes) << 2));
    for (int i = 0; i < bytes; i++) o.push_back(static_cast<uint8_t>(m >> (8 * i)));
  }
  o.insert(o.end(), p, p + n);
}

// One copy element for 4 <= len <= 64 (len < 12 and offset < 2048 use the 2-byte form).
inline void emit_copy_upto64(std::vector<uint8_t>& o, uint32_t offset, uint32_t len) {
  if (len < 12 && offset < 2048) {
    o.push_back(static_cast<uint8_t>(1 | ((len - 4) << 2) | ((offset >> 8) << 5)));
    o.push_back(static_cast<uint8_t>(offset & 0xff));
  } else {
    o.push_back(static_cast<uint8_t>(2 | ((len - 1) << 2)));
    o.push_back(static_cast<uint8_t>(offset & 0xff));
    o.push_back(static_cast<uint8_t>(offset >> 8));
  }
}

inline void emit_copy(std::vector<uint8_t>& o, uint32_t offset, uint32_t len) {
  // Keep every piece >= 4 bytes (snappy's EmitCopy split).
  while (len >= 68) {
    emit_copy_upto64(o, offset, 64);
    len -= 64;
  }
  if (len > 64) {
    emit_copy_upto64(o, offset, 60);
    len -= 60;
  }
  emit_copy_upto64(o, offset, len);
}

inline uint32_t load32(const uint8_t* p) {
  uint32_t v;
  std::memcpy(&v, p, 4);
  return v;
}

inline void compress_fragment(std::vector<uint8_t>& o, const uint8_t* base, size_t len,
                              uint16_t* table) {
  constexpr int kBits = 14;
  constexpr size_t kMargin = 15;
  if (len < kMargin) {
    emit_literal(o, base, len);
    return;
  }
  std::memset(table, 0, sizeof(uint16_t) << kBits);
  auto hash = [](uint32_t v) { return (v * 0x1e35a7bdu) >> (32 - kBits); };
  const size_t limit = len - kMargin;
  size_t next_emit = 0;
  size_t ip = 1;
  // libsnappy's skipping: after 32 lookups without a match, probe every 2nd byte, after 16 more
  // every 3rd, ... so incompressible input (most delta-packed pages) costs little; a match
  // resets it.
  uint32_t skip = 32;
  while (ip < limit) {
    const uint32_t cur = load32(base + ip);
    const uint32_t h = hash(cur);
    const size_t cand = table[h];
    table[h] = static_cast<uint16_t>(ip);
    if (cand < ip && load32(base + cand) == cur) {
      skip = 32;
      emit_literal(o, base + next_emit, ip - next_emit);
      size_t matched = 4;
      while (ip + matched < len && base[cand + matched] == base[ip + matched]) matched++;
      emit_copy(o, static_cast<uint32_t>(ip - cand), static_cast<uint32_t>(matched));
      ip += matched;
      next_emit = ip;
      if (ip < limit) table[hash(load32(base + ip - 1))] = static_cast<uint16_t>(ip - 1);
    } else {
      ip += skip++ >> 5;
    }
  }
  emit_literal(o, base + next_emit, len - next_emit);
}

// Appends the compressed form of in[0, n) to `o`.
inline void compress(const uint8_t* in, size_t n, std::vector<uint8_t>& o) {
  put_varint32(o, static_cast<uint32_t>(n));
  std::vector<uint16_t> table(size_t{1} << 14);
  for (size_t pos = 0; pos < n; pos += 65536) {
    const size_t len = (n - pos) < 65536 ? (n - pos) : 65536;
    compress_fragment(o, in + pos, len, table.data());
  }
}

}  // namespace snappy_lite
}  // namespace t3
