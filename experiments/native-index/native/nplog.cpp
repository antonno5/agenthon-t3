// Bit-exact float64 np.log (numpy 1.26.4) for a scalar, without importing numpy.
//
// numpy's DOUBLE_log loop (loops_exponent_log.dispatch.c.src) runs the variant for the best
// CPU target available at run time:
//   AVX512_SKX (+ SVML linked, as in the Linux x86-64 wheels): __svml_log8 (vendored asm)
//   AVX512F only:                                       numpy's own AVX512F_log_DOUBLE
//   anything else:                                      npy_log == libm log
// A Python float goes through the loop as a 1-element array, so on SKX lane 0 of
// __svml_log8 is the result (SVML is element-wise; numpy pads the other lanes with 1.0).
// The AVX512F-without-SKX case (Knights Landing class) is not reproduced here: numpy_log
// reports "unknown" and the caller imports numpy instead. So does an environment that
// changes numpy's dispatch (NPY_DISABLE_CPU_FEATURES / NPY_ENABLE_CPU_FEATURES).
#include "nplog.hpp"

#include <cpuid.h>
#include <immintrin.h>

#include <cmath>
#include <cstdint>
#include <cstdlib>

extern "C" __m512d __svml_log8(__m512d);

namespace t3 {
namespace {

enum Dispatch { D_LIBM, D_SVML, D_UNKNOWN };

uint64_t xgetbv0() {
  uint32_t eax, edx;
  __asm__ volatile("xgetbv" : "=a"(eax), "=d"(edx) : "c"(0));
  return (static_cast<uint64_t>(edx) << 32) | eax;
}

// Mirrors numpy/core/src/common/npy_cpu_features.c (x86 part) for the features that pick
// the DOUBLE_log variant.
Dispatch detect() {
  if (std::getenv("NPY_DISABLE_CPU_FEATURES") || std::getenv("NPY_ENABLE_CPU_FEATURES"))
    return D_UNKNOWN;
  unsigned a, b, c, d;
  if (!__get_cpuid(1, &a, &b, &c, &d)) return D_LIBM;
  const bool osxsave = (c & (1u << 27)) != 0;
  if (!osxsave) return D_LIBM;
  const uint64_t xcr = xgetbv0();
  const bool os_avx = (xcr & 0x6) == 0x6;
  const bool os_avx512 = (xcr & 0xe6) == 0xe6;
  if (!os_avx || !os_avx512) return D_LIBM;
  if (__get_cpuid_max(0, nullptr) < 7) return D_LIBM;
  __cpuid_count(7, 0, a, b, c, d);
  const bool f = b & (1u << 16), dq = b & (1u << 17), cd = b & (1u << 28),
             bw = b & (1u << 30), vl = b & (1u << 31);
  if (!f) return D_LIBM;
  if (cd && bw && dq && vl) return D_SVML;  // AVX512_SKX
  return D_UNKNOWN;                         // AVX512F without SKX: numpy's own kernel
}

__attribute__((target("avx512f"))) double svml_lane0(double x) {
  alignas(64) double in[8] = {x, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};
  alignas(64) double out[8];
  _mm512_store_pd(out, __svml_log8(_mm512_load_pd(in)));
  return out[0];
}

}  // namespace

bool numpy_log(double x, double* out) {
  static const Dispatch d = detect();
  switch (d) {
    case D_SVML: *out = svml_lane0(x); return true;
    case D_LIBM: *out = std::log(x); return true;
    default: return false;
  }
}

const char* numpy_log_dispatch() {
  static const Dispatch d = detect();
  return d == D_SVML ? "svml" : (d == D_LIBM ? "libm" : "unknown");
}

}  // namespace t3
