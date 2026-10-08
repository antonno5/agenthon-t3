"""Build the standalone CLI as ONE fully static executable.

The run path links no shared library at all: the engine, numpy-exact RNG/log (vendored
SVML), the dependency-free Parquet writer (native/pqlite.cpp: own Snappy, Thrift footer,
SHA-256) and the JSON front end. A container start then maps a single ~3 MB file instead of
Python, libarrow (59 MB), libparquet, libcrypto and libstdc++ -- the dominant cost of a run
with a cold page cache. glibc/libm come from this same Debian image, so exp/log are the
same code the Python reference runs. IEEE-strict flags, no -march.
"""
import pathlib
import subprocess
import sys

src = pathlib.Path(sys.argv[1]).resolve() / "native"
out = pathlib.Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
obj = out / "cli_svml.o"
subprocess.run(["gcc", "-c", str(src / "svml/svml_z0_log_d_la.s"), "-o", str(obj)], check=True)
subprocess.run([
    "g++", "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
    "-fno-strict-aliasing", "-Wall", "-Wno-unused-function", "-pthread", f"-I{src}",
    *[str(src / name) for name in ("cli.cpp", "engine.cpp", "pqlite.cpp", "nplog.cpp")],
    str(obj), "-static", "-s", "-o", str(out / "t3-native"),
], check=True)
obj.unlink()
