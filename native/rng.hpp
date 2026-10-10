// Bit-exact re-implementation of numpy's legacy ``np.random.RandomState`` (numpy 1.26):
// MT19937 core, ``mt19937_seed`` integer seeding, the 53-bit double, and the *legacy*
// distribution routines RandomState dispatches to (polar-method gauss with its cached
// second value, legacy exponential/pareto/lognormal, masked-rejection bounded integers).
//
// Every routine mirrors numpy/random/src/{mt19937,legacy,distributions}/*.c line for line;
// the math calls (exp, log, sqrt) resolve to the same libm numpy itself links against.
// tests/test_rng.py checks millions of draws per distribution against numpy.
#pragma once

#include <cmath>
#include <cstdint>

namespace t3 {

class RandomState {
 public:
  static constexpr int N = 624;
  static constexpr int M = 397;

  explicit RandomState(uint32_t seed = 0) { this->seed(seed); }

  // numpy: mt19937_seed (used by RandomState(seed=int) / np.random.seed(int)).
  void seed(uint32_t s) {
    for (int pos = 0; pos < N; pos++) {
      key_[pos] = s;
      s = (1812433253u * (s ^ (s >> 30)) + static_cast<uint32_t>(pos) + 1u);
    }
    pos_ = N;
    has_gauss_ = false;
    gauss_ = 0.0;
  }

  uint32_t next_uint32() {
    if (pos_ == N) gen();
    uint32_t y = key_[pos_++];
    y ^= (y >> 11);
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= (y >> 18);
    return y;
  }

  // numpy: mt19937_next_double (legacy_double resolves to the same thing).
  double next_double() {
    int32_t a = static_cast<int32_t>(next_uint32() >> 5);
    int32_t b = static_cast<int32_t>(next_uint32() >> 6);
    return (a * 67108864.0 + b) / 9007199254740992.0;
  }

  // numpy: legacy_gauss (polar Box-Muller, caches the second variate).
  double gauss() {
    if (has_gauss_) {
      const double temp = gauss_;
      has_gauss_ = false;
      gauss_ = 0.0;
      return temp;
    }
    double f, x1, x2, r2;
    do {
      x1 = 2.0 * next_double() - 1.0;
      x2 = 2.0 * next_double() - 1.0;
      r2 = x1 * x1 + x2 * x2;
    } while (r2 >= 1.0 || r2 == 0.0);
    f = std::sqrt(-2.0 * std::log(r2) / r2);
    gauss_ = f * x1;
    has_gauss_ = true;
    return f * x2;
  }

  // RandomState.normal(loc, scale) -> legacy_normal.
  double normal(double loc, double scale) { return loc + scale * gauss(); }
  // RandomState.lognormal(mean, sigma) -> legacy_lognormal.
  double lognormal(double mean, double sigma) { return std::exp(normal(mean, sigma)); }
  // RandomState.uniform(low, high) -> random_uniform(low, high - low).
  double uniform(double low, double high) {
    const double range = high - low;
    return low + range * next_double();
  }
  // legacy_standard_exponential / legacy_exponential / legacy_pareto.
  double standard_exponential() { return -std::log(1.0 - next_double()); }
  double exponential(double scale) { return scale * standard_exponential(); }
  double pareto(double a) { return std::exp(standard_exponential() / a) - 1.0; }

  // RandomState.randint(low, high) for the default int64 dtype, high exclusive
  // (numpy: _rand_int64 -> random_bounded_uint64_fill with use_masked=True).
  int64_t randint(int64_t low, int64_t high) {
    const uint64_t rng = static_cast<uint64_t>(high - 1) - static_cast<uint64_t>(low);
    return static_cast<int64_t>(static_cast<uint64_t>(low) + bounded_uint64(rng));
  }

  // RandomState.randint(0, 2**32, dtype="uint64"): rng == 0xFFFFFFFF -> one raw uint32.
  uint32_t randint_u32_full() { return next_uint32(); }

 private:
  void gen() {
    constexpr uint32_t MATRIX_A = 0x9908b0dfu, UPPER = 0x80000000u, LOWER = 0x7fffffffu;
    uint32_t y;
    int i;
    for (i = 0; i < N - M; i++) {
      y = (key_[i] & UPPER) | (key_[i + 1] & LOWER);
      key_[i] = key_[i + M] ^ (y >> 1) ^ (-(y & 1u) & MATRIX_A);
    }
    for (; i < N - 1; i++) {
      y = (key_[i] & UPPER) | (key_[i + 1] & LOWER);
      key_[i] = key_[i + (M - N)] ^ (y >> 1) ^ (-(y & 1u) & MATRIX_A);
    }
    y = (key_[N - 1] & UPPER) | (key_[0] & LOWER);
    key_[N - 1] = key_[M - 1] ^ (y >> 1) ^ (-(y & 1u) & MATRIX_A);
    pos_ = 0;
  }

  static uint64_t gen_mask(uint64_t max) {
    uint64_t mask = max;
    mask |= mask >> 1;
    mask |= mask >> 2;
    mask |= mask >> 4;
    mask |= mask >> 8;
    mask |= mask >> 16;
    mask |= mask >> 32;
    return mask;
  }

  uint64_t next_uint64() {
    // mt19937_next64: high word first.
    const uint64_t hi = next_uint32();
    return (hi << 32) | next_uint32();
  }

  // random_bounded_uint64_fill, single value, use_masked=true.
  uint64_t bounded_uint64(uint64_t rng) {
    if (rng == 0) return 0;
    if (rng <= 0xFFFFFFFFull) {
      if (rng == 0xFFFFFFFFull) return next_uint32();
      const uint32_t mask = static_cast<uint32_t>(gen_mask(rng));
      uint32_t val;
      while ((val = (next_uint32() & mask)) > rng) {
      }
      return val;
    }
    if (rng == 0xFFFFFFFFFFFFFFFFull) return next_uint64();
    const uint64_t mask = gen_mask(rng);
    uint64_t val;
    while ((val = (next_uint64() & mask)) > rng) {
    }
    return val;
  }

  // The small state first: an owner that keeps hot fields just before a RandomState then
  // touches one cache line for them and pos_, plus the line of key_[pos_].
  int pos_;
  bool has_gauss_;
  double gauss_;
  uint32_t key_[N];
};

}  // namespace t3
