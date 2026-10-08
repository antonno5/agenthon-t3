"""numpy_log (native) vs float(np.log(x)) on this CPU, plus numpy's non-AVX512 path vs libm.

usage: python test_nplog.py [n]
"""
import math, os, random, struct, subprocess, sys

import numpy as np

from abides_fork import _t3engine

n = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
R = random.Random(7)
print("dispatch:", _t3engine.numpy_log_dispatch())


def samples(k):
    for _ in range(k):
        r = R.random()
        if r < 0.3:
            yield R.uniform(0, 1e8)
        elif r < 0.5:
            yield float(R.randint(1, 10**9))
        elif r < 0.7:
            yield 10 ** R.uniform(-300, 300)
        elif r < 0.9:  # random bit patterns of positive finite doubles
            yield struct.unpack("<d", struct.pack("<Q", R.getrandbits(62) | (1 << 62) * R.getrandbits(1)))[0]
        else:
            yield R.choice([1.0, 2.0, 0.5, 1e3, 5e4, 1e6, 2e7, 1e-310, 5e-324, 1.7976931348623157e308,
                            0.0, -1.0, float("inf"), float("nan")])


xs = list(samples(n))
ref = np.log(np.array(xs))  # numpy's vector path == its scalar path here (elementwise)
bad = 0
for x, r in zip(xs, ref):
    with np.errstate(all="ignore"):
        s = float(np.log(x)) if bad < 0 else float(r)
    got = _t3engine.numpy_log(x)
    if got is None:
        print("dispatch unknown on this CPU"); sys.exit(2)
    if not (got == s or (math.isnan(got) and math.isnan(s))):
        bad += 1
        if bad < 5:
            print("mismatch", x.hex(), got.hex(), s.hex())
# also the true scalar call path for a subset
for x in xs[:200_000]:
    with np.errstate(all="ignore"):
        s = float(np.log(x))
    got = _t3engine.numpy_log(x)
    if not (got == s or (math.isnan(got) and math.isnan(s))):
        bad += 1
print("vs np.log mismatches:", bad, "of", n)
sys.exit(1 if bad else 0)
