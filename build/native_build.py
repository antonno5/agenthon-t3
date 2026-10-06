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
# Parquet output links the libarrow/libparquet bundled in the pinned pyarrow wheel (same
# code pyarrow.parquet.write_table runs); rpath points at that directory.
import pyarrow

pa_inc = pyarrow.get_include()
pa_lib = pyarrow.get_library_dirs()[0]
work_obj = pathlib.Path(tempfile.mkdtemp(prefix="t3svml-"))
svml_obj = work_obj / "svml_z0_log_d_la.o"
import subprocess

subprocess.run(["gcc", "-c", str(src / "svml" / "svml_z0_log_d_la.s"), "-o", str(svml_obj)],
               check=True)
ext = Extension(
    "_t3engine",
    sources=[str(src / "engine.cpp"), str(src / "module.cpp"), str(src / "pqwrite.cpp"),
             str(src / "nplog.cpp")],
    extra_objects=[str(svml_obj)],
    include_dirs=[str(src), pa_inc],
    language="c++",
    extra_compile_args=["-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
                        "-fno-strict-aliasing", "-Wall", "-Wno-unused-function"],
    extra_link_args=[f"-L{pa_lib}", "-l:libparquet.so.1500", "-l:libarrow.so.1500",
                     f"-Wl,-rpath,{pa_lib}"],
)
sys.argv[1:] = ["build_ext", "--build-lib", work, "--build-temp", os.path.join(work, "tmp")]
setup(name="t3engine", ext_modules=[ext])
for f in pathlib.Path(work).glob("_t3engine*.so"):
    shutil.copy2(f, out / f.name)
    print("built", out / f.name)
shutil.rmtree(work)
shutil.rmtree(work_obj)
