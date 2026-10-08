`svml_z0_log_d_la.s` and `LICENSE` are copied verbatim from https://github.com/numpy/SVML at
commit 1b21e453f6b1ba6a6aca392b1d810d9d41576123 -- the submodule commit numpy v1.26.4 pins at
`numpy/core/src/umath/svml`. numpy 1.26.4 computes float64 `np.log` with this routine on
AVX512_SKX CPUs; `native/nplog.cpp` uses it to reproduce `np.log` bit for bit without
importing numpy.
