"""Build the standalone CLI against the exact pinned wheel's Arrow/Parquet libraries.

Executive summary: only the front end changes; compile the existing simulation and writer
with their existing IEEE flags. No package installation or runtime download is involved.
"""
import pathlib
import subprocess
import sys
import pyarrow

src = pathlib.Path(sys.argv[1]).resolve() / "native"
out = pathlib.Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
assert pyarrow.__version__ == "15.0.2", pyarrow.__version__
lib = pyarrow.get_library_dirs()[0]
obj = out / "cli_svml.o"
subprocess.run(["gcc", "-c", str(src / "svml/svml_z0_log_d_la.s"), "-o", str(obj)], check=True)
subprocess.run([
    "g++", "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
    "-fno-strict-aliasing", "-Wall", "-Wno-unused-function", "-pthread",
    f"-I{src}", f"-I{pyarrow.get_include()}",
    *[str(src / name) for name in ("cli.cpp", "engine.cpp", "pqwrite.cpp", "nplog.cpp")],
    str(obj), f"-L{lib}", "-l:libparquet.so.1500", "-l:libarrow.so.1500", "-l:libcrypto.so.3",
    f"-Wl,-rpath,{lib}", "-o", str(out / "t3-native"),
], check=True)
obj.unlink()
