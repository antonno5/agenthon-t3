#pragma once
namespace t3 {
// float64 np.log(x) as numpy 1.26.4 computes it on this CPU; false if not reproducible here.
bool numpy_log(double x, double* out);
const char* numpy_log_dispatch();  // "svml" | "libm" | "unknown"
}  // namespace t3
