"""Build the native engine extension ``abides_fork._t3engine``.

usage: python build/native_build.py SRC_ROOT OUT_DIR
SRC_ROOT holds native/*.cpp; the .so lands in OUT_DIR (the abides_fork package dir).
Floating-point flags keep IEEE semantics identical to the Python reference: no fast-math,
no FMA contraction, no -march (the image must run on any x86-64 host).
"""
import os
import pathlib
import shutil
import sys
import tempfile

from setuptools import Extension, setup

src = pathlib.Path(sys.argv[1]).resolve() / "native"
out = pathlib.Path(sys.argv[2]).resolve()
work = tempfile.mkdtemp(prefix="t3native-")
ext = Extension(
    "_t3engine",
    sources=[str(src / "engine.cpp"), str(src / "module.cpp")],
    include_dirs=[str(src)],
    language="c++",
    extra_compile_args=["-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
                        "-fno-strict-aliasing", "-Wall", "-Wno-unused-function"],
)
sys.argv[1:] = ["build_ext", "--build-lib", work, "--build-temp", os.path.join(work, "tmp")]
setup(name="t3engine", ext_modules=[ext])
for f in pathlib.Path(work).glob("_t3engine*.so"):
    shutil.copy2(f, out / f.name)
    print("built", out / f.name)
shutil.rmtree(work)
