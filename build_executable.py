"""Build the standalone CLI as ONE fully static executable.

The run path links no shared library at all: the engine, numpy-exact RNG/log (vendored
SVML), the dependency-free Parquet writer (native/pqlite.cpp: own Snappy, Thrift footer,
SHA-256) and the JSON front end. A container start then maps a single ~3 MB file instead of
Python, libarrow (59 MB), libparquet, libcrypto and libstdc++ -- the dominant cost of a run
with a cold page cache. glibc/libm come from this same Debian image, so exp/log are the
same code the Python reference runs. IEEE-strict flags, no -march.

Profile-guided: an instrumented build first runs the synthetic scenarios in pgo/ (our own
configurations, not the public units), then the final build uses that profile for code
layout and inlining. Both builds use the same strict floating-point flags, so the profile
cannot change any output.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1]).resolve()
src = root / "native"
out = pathlib.Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
SOURCES = ("cli", "engine", "pqlite", "nplog")
FLAGS = ["-std=c++17", "-O3", "-fno-fast-math", "-ffp-contract=off", "-fno-strict-aliasing",
         "-Wall", "-Wno-unused-function", "-pthread", f"-I{src}"]

work = pathlib.Path(tempfile.mkdtemp(prefix="t3-build-"))
try:
    svml = work / "svml.o"
    subprocess.run(["gcc", "-c", str(src / "svml/svml_z0_log_d_la.s"), "-o", str(svml)], check=True)
    profile = work / "profile"
    objects = [work / f"{name}.o" for name in SOURCES]  # same paths in both stages

    def build(stage_flags, link_flags, binary):
        for name, obj in zip(SOURCES, objects):
            subprocess.run(["g++", *FLAGS, *stage_flags, "-c", str(src / f"{name}.cpp"),
                            "-o", str(obj)], check=True)
        subprocess.run(["g++", "-pthread", *stage_flags, *map(str, objects), str(svml), "-static",
                        *link_flags, "-o", str(binary)], check=True)

    # 1. Instrumented build, trained on pgo/train (single markets) and pgo/train-batch.
    trainer = work / "bin" / "t3-native"
    trainer.parent.mkdir()
    # The CLI leaves through _exit(); it calls __gcov_dump through a weak reference, which a
    # static link resolves only when the symbol is pulled in explicitly.
    build(["-fprofile-generate", "-fprofile-update=atomic", f"-fprofile-dir={profile}"],
          ["-Wl,--undefined=__gcov_dump"], trainer)
    for verb in ("simulate", "simulate-batch"):
        (trainer.parent / verb).symlink_to("t3-native")
    runs = work / "runs"
    for unit in sorted((root / "pgo/train").iterdir()):
        dest = runs / unit.name
        dest.mkdir(parents=True)
        subprocess.run([str(trainer.parent / "simulate"), "--config", str(unit / "scenario.json"),
                        "--out", str(dest / "trace.parquet")], check=True,
                       stdout=subprocess.DEVNULL)
    subprocess.run([str(trainer.parent / "simulate-batch"), "--batch-dir",
                    str(root / "pgo/train-batch/scenarios"), "--out-dir", str(runs / "batch")],
                   check=True, stdout=subprocess.DEVNULL)

    # 2. Final build with the profile.
    build(["-fprofile-use", "-fprofile-partial-training", "-Werror=missing-profile",
           f"-fprofile-dir={profile}"], ["-s"], out / "t3-native")
finally:
    shutil.rmtree(work, ignore_errors=True)
