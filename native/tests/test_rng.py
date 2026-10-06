"""Differential test: native RandomState vs numpy's legacy RandomState.

usage: python test_rng.py RNGDUMP_BINARY [n_scripts]
Random scripts interleave every op (so the gauss cache, rejection loops and 32/64-bit
paths interact exactly as they would in a run) across many seeds, including the
seed-from-global-randint path the simulator uses.
"""
import random, subprocess, sys
import numpy as np

exe = sys.argv[1]
n_scripts = int(sys.argv[2]) if len(sys.argv) > 2 else 200
R = random.Random(12345)
fails = 0
for k in range(n_scripts):
    seed = R.choice([0, 1, 42, 2**32 - 1, R.randrange(2**32)])
    rs = np.random.RandomState(seed)
    lines, expect = [f"s {seed} 0"], []
    for _ in range(R.choice([10, 100, 3000])):
        op = R.choice("nnnluuepprrrwdl")
        if op == "n":
            a, b = R.choice([(10.0, 2.0), (0.0, 1.0), (1000.0, 31.622776601683793), (5.0, 0.0), (R.uniform(-1e6, 1e6), R.uniform(0, 1e3))])
            lines.append(f"n {a!r} {b!r}"); expect.append(repr(float(rs.normal(a, b))))
        elif op == "l":
            a, b = R.uniform(0, 12), R.uniform(0, 2)
            lines.append(f"l {a!r} {b!r}"); expect.append(repr(float(rs.lognormal(mean=a, sigma=b))))
        elif op == "u":
            a = R.uniform(0, 1e6); b = a + R.uniform(0, 1e7)
            lines.append(f"u {a!r} {b!r}"); expect.append(repr(float(rs.uniform(a, b))))
        elif op == "e":
            a = R.choice([3.6e17, 5e8, 1.0, R.uniform(0, 1e12)])
            lines.append(f"e {a!r} 0"); expect.append(repr(float(rs.exponential(scale=a))))
        elif op == "p":
            a = R.choice([1.5, 1.1, 3.0, R.uniform(0.5, 5)])
            lines.append(f"p {a!r} 0"); expect.append(repr(float(rs.pareto(a))))
        elif op == "r":
            lo, hi = R.choice([(0, 2), (0, 1), (0, 6), (0, 11), (0, 2**31), (5, 2**33 + 7), (0, 3)])
            lines.append(f"r {lo} {hi}"); expect.append(str(int(rs.randint(lo, hi))))
        elif op == "w":
            lines.append("w 0 0"); expect.append(str(int(rs.randint(low=0, high=2**32, dtype="uint64"))))
        elif op == "d":
            lines.append("d 0 0"); expect.append(repr(float(rs.random_sample())))
    out = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True).stdout.split()
    # Compare exactly as numbers: floats via their IEEE value, ints as ints.
    got = [repr(float(x)) if "." in e or "e" in e or "n" in e else x for x, e in zip(out, expect)]
    if got != expect:
        fails += 1
        i = next(i for i, (g, e) in enumerate(zip(got, expect)) if g != e) if len(got) == len(expect) else -1
        print(f"script {k} seed {seed}: mismatch at {i}: got {got[i] if i>=0 else len(got)} expected {expect[i] if i>=0 else len(expect)} op {lines[i+1] if i>=0 else ''}")
        if fails > 5:
            break
print("FAILS", fails, "of", k + 1)
sys.exit(1 if fails else 0)
