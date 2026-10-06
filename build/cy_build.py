"""Compile every module of the given package dirs with Cython, in place.

usage: python cy_build.py ROOT   (ROOT holds abides_core/, abides_markets/, abides_fork/)

Sources under ROOT are rewritten first (annotations stripped, see below), so ROOT must be
a scratch copy. __init__.py, the CLI entry modules, configs/ and examples/ stay pure
Python. Directives are chosen so compiled code keeps Python semantics: no annotation
typing, no type inference, Python division/overflow/bounds behaviour; binding=True keeps
functions as normal descriptors so monkeypatching and introspection behave as before.
"""

import ast
import os
import pathlib
import sys


def strip_function_annotations(tree: ast.Module) -> ast.Module:
    """Remove annotations on function parameters/returns and on assignments inside
    function bodies (an AnnAssign becomes a plain Assign, or ``pass`` if it had no value).

    CPython ignores these at runtime, but Cython derives C types from some of them even
    with annotation_typing off -- e.g. it infers a comprehension variable is an exact
    ``list`` from ``bids: List[List[...]]`` and then raises on tuples. Class-body
    annotations are kept: the message dataclasses need them to define their fields.
    """
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        args = fn.args
        for a in args.posonlyargs + args.args + args.kwonlyargs:
            a.annotation = None
        for a in (args.vararg, args.kwarg):
            if a is not None:
                a.annotation = None
        fn.returns = None
        for parent in ast.walk(fn):
            for _, value in ast.iter_fields(parent):
                if not isinstance(value, list):
                    continue
                for i, child in enumerate(value):
                    if isinstance(child, ast.AnnAssign):
                        if child.value is None:
                            new = ast.Pass()
                        else:
                            new = ast.Assign(targets=[child.target], value=child.value)
                        value[i] = ast.copy_location(new, child)
    return ast.fix_missing_locations(tree)


SKIP_DIRS = {"configs", "examples", "tests", "__pycache__"}
# Entry points stay plain Python so `python -m abides_fork.simulate` keeps working.
KEEP_PY = {"__init__.py", "simulate.py", "simulate_batch.py"}
DIRECTIVES = {
    "language_level": 3,
    "binding": True,
    "annotation_typing": False,
    "infer_types": False,
}


def main() -> None:
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    root = pathlib.Path(sys.argv.pop(1)).resolve()
    os.chdir(root)
    mods = []
    for pkg in ("abides_core", "abides_markets", "abides_fork"):
        for p in sorted(pathlib.Path(pkg).rglob("*.py")):
            if p.name in KEEP_PY or SKIP_DIRS & set(p.parts):
                continue
            p.write_text(ast.unparse(strip_function_annotations(ast.parse(p.read_text()))) + "\n")
            mods.append(
                Extension(
                    ".".join(p.with_suffix("").parts),
                    [str(p)],
                    extra_compile_args=["-O2", "-Wno-unused-function", "-Wno-unused-variable"],
                )
            )
    n = os.cpu_count() or 4
    sys.argv[1:] = ["build_ext", "--inplace", "-j", str(n)]
    setup(ext_modules=cythonize(mods, compiler_directives=DIRECTIVES, nthreads=n, quiet=True))


if __name__ == "__main__":
    main()
