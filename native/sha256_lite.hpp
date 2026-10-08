// SHA-256 (FIPS 180-4) without OpenSSL: x86 SHA extensions when the CPU has them (runtime
// cpuid check), portable scalar rounds otherwise. tools/test_sha256_lite.py checks both
// paths against hashlib.
#pragma once

#include <cpuid.h>
#include <immintrin.h>

#include <cstdint>
#include <cstring>
#include <string>

namespace t3 {
namespace sha256_lite {

constexpr uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};

inline uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

inline void blocks_scalar(uint32_t h[8], const uint8_t* p, size_t nblocks) {
  for (; nblocks; nblocks--, p += 64) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
      w[i] = (uint32_t(p[4 * i]) << 24) | (uint32_t(p[4 * i + 1]) << 16) |
             (uint32_t(p[4 * i + 2]) << 8) | uint32_t(p[4 * i + 3]);
    for (int i = 16; i < 64; i++) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
      const uint32_t t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i];
      const uint32_t t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
}

// Intel SHA extensions (SHA-NI) block function, the standard sequence from Intel's
// "Intel SHA Extensions" paper.
__attribute__((target("sha,sse4.1,ssse3"))) inline void blocks_shani(uint32_t h[8],
                                                                  const uint8_t* p,
                                                                  size_t nblocks) {
  const __m128i MASK = _mm_set_epi64x(0x0c0d0e0f08090a0bULL, 0x0405060700010203ULL);
  __m128i TMP = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&h[0]));
  __m128i STATE1 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&h[4]));
  TMP = _mm_shuffle_epi32(TMP, 0xB1);
  STATE1 = _mm_shuffle_epi32(STATE1, 0x1B);
  __m128i STATE0 = _mm_alignr_epi8(TMP, STATE1, 8);
  STATE1 = _mm_blend_epi16(STATE1, TMP, 0xF0);
  for (; nblocks; nblocks--, p += 64) {
    const __m128i ABEF_SAVE = STATE0, CDGH_SAVE = STATE1;
    __m128i MSG;
    __m128i W[4];  // message schedule, 4 words per register, used round-robin
    auto K4 = [](int i) { return _mm_loadu_si128(reinterpret_cast<const __m128i*>(&K[i])); };
    for (int q = 0; q < 4; q++)
      W[q] = _mm_shuffle_epi8(_mm_loadu_si128(reinterpret_cast<const __m128i*>(p + 16 * q)), MASK);
    // Rounds 0-11: no schedule completion yet; msg1 starts after W[1] and W[2] exist.
    for (int q = 0; q < 3; q++) {
      MSG = _mm_add_epi32(W[q], K4(4 * q));
      STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
      STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, _mm_shuffle_epi32(MSG, 0x0E));
      if (q > 0) W[q - 1] = _mm_sha256msg1_epu32(W[q - 1], W[q]);
    }
    // Rounds 12-59: block q (rounds 4q..4q+3) uses W[q%4]; it completes the schedule block
    // W[(q+1)%4] with msg2 and starts W[(q-1)%4] with msg1 (up to q = 12).
    for (int q = 3; q < 15; q++) {
      __m128i& cur = W[q & 3];
      __m128i& prev = W[(q + 3) & 3];
      __m128i& next = W[(q + 1) & 3];
      MSG = _mm_add_epi32(cur, K4(4 * q));
      STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
      TMP = _mm_alignr_epi8(cur, prev, 4);
      next = _mm_add_epi32(next, TMP);
      next = _mm_sha256msg2_epu32(next, cur);
      STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, _mm_shuffle_epi32(MSG, 0x0E));
      if (q <= 12) prev = _mm_sha256msg1_epu32(prev, cur);
    }
    // Rounds 60-63
    MSG = _mm_add_epi32(W[3], K4(60));
    STATE1 = _mm_sha256rnds2_epu32(STATE1, STATE0, MSG);
    STATE0 = _mm_sha256rnds2_epu32(STATE0, STATE1, _mm_shuffle_epi32(MSG, 0x0E));
    STATE0 = _mm_add_epi32(STATE0, ABEF_SAVE);
    STATE1 = _mm_add_epi32(STATE1, CDGH_SAVE);
  }
  TMP = _mm_shuffle_epi32(STATE0, 0x1B);
  STATE1 = _mm_shuffle_epi32(STATE1, 0xB1);
  STATE0 = _mm_blend_epi16(TMP, STATE1, 0xF0);
  STATE1 = _mm_alignr_epi8(STATE1, TMP, 8);
  _mm_storeu_si128(reinterpret_cast<__m128i*>(&h[0]), STATE0);
  _mm_storeu_si128(reinterpret_cast<__m128i*>(&h[4]), STATE1);
}

inline bool cpu_has_shani() {
  if (std::getenv("T3_SHA_SCALAR")) return false;  // test hook for the portable path
  unsigned a, b, c, d;
  if (!__get_cpuid(1, &a, &b, &c, &d)) return false;
  const bool ssse3 = c & (1u << 9), sse41 = c & (1u << 19);
  if (__get_cpuid_max(0, nullptr) < 7) return false;
  __cpuid_count(7, 0, a, b, c, d);
  return ssse3 && sse41 && (b & (1u << 29));
}

class Sha256 {
 public:
  void update(const uint8_t* p, size_t n) {
    total_ += n;
    if (used_) {
      const size_t k = n < 64 - used_ ? n : 64 - used_;
      std::memcpy(buf_ + used_, p, k);
      used_ += k; p += k; n -= k;
      if (used_ == 64) { blocks(buf_, 1); used_ = 0; }
    }
    if (n >= 64) {
      blocks(p, n / 64);
      p += n & ~size_t{63};
      n &= 63;
    }
    if (n) { std::memcpy(buf_, p, n); used_ = n; }
  }
  std::string hex() {
    const uint64_t bits = total_ * 8;
    uint8_t pad[72] = {0x80};
    const size_t padlen = (used_ < 56 ? 56 - used_ : 120 - used_);
    uint8_t len[8];
    for (int i = 0; i < 8; i++) len[i] = uint8_t(bits >> (56 - 8 * i));
    update(pad, padlen);
    update(len, 8);
    static const char* digits = "0123456789abcdef";
    std::string s;
    for (uint32_t v : h_)
      for (int i = 28; i >= 0; i -= 4) s += digits[(v >> i) & 0xf];
    return s;
  }
  static const char* provider() { return cpu_has_shani() ? "sha-ni" : "scalar"; }

 private:
  void blocks(const uint8_t* p, size_t n) {
    static const bool shani = cpu_has_shani();
    if (shani) blocks_shani(h_, p, n); else blocks_scalar(h_, p, n);
  }
  uint32_t h_[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t buf_[64];
  size_t used_ = 0;
  uint64_t total_ = 0;
};

}  // namespace sha256_lite
}  // namespace t3
