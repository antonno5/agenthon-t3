"""Install the Python book layers over the exact seven-patch ABIDES source.

Executive summary: reorganize the existing book without changing how orders trade.
Reject different engine sources or an unrecorded overlay before writing files.
"""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil


SOURCE_SHA256 = {
    "order_book.py": "2c02c494028b9fb6e31f48f1df1de2e0c478f24ca2987b2fbe5527a7c454b7b4",
    "price_level.py": "d448ccf12f49c8078994c6d1d2ca150bfed169dbfa393fcfd4d8bc7e4eb9c1b1",
}
LAYERS = {
    "state.py": "OrderBookState",
    "matcher.py": "Matching",
    "queries.py": "BookQueries",
    "facade.py": "OrderBook",
}

# Intentional stage-3 changes are covered by runtime differential tests and the
# checked-in overlay digest manifest. Every other upstream body stays identical.
BOOK_CHANGED_METHODS = {
    "enter_order",
    "cancel_order",
    "modify_order",
    "partial_cancel_order",
    "execute_order",
}
LEVEL_CHANGED_METHODS = {"update_order_quantity", "remove_order", "pop"}


def overlay_files(layers_dir: Path, compat_dir: Path) -> dict[str, Path]:
    return {
        f"{directory.name}/{path.name}": path
        for directory in (layers_dir, compat_dir)
        for path in directory.glob("*.py")
    }


def check_methods(original, extracted, changed, label):
    missing = original.keys() - extracted.keys()
    extra = {
        name for name in extracted.keys() - original.keys() if not name.startswith("_")
    }
    if missing or extra:
        raise ValueError(
            f"{label} methods differ: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for name, method in original.items():
        candidate = extracted[name]
        # AST dumps are compared below; signature dumps include decorators.
        if name not in changed and method != candidate:
            raise ValueError(f"{label} method differs: {name}")


def class_node(path: Path, name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError(f"{path}: require exactly one {name} class")
    return nodes[0]


def normalize_book_init(method: ast.FunctionDef) -> ast.FunctionDef:
    """Allow only direct empty-side initialization with the matching Side."""
    method = deepcopy(method)
    expected = {
        name: ast.dump(ast.parse(f"_PriceLevels(Side.{side})", mode="eval").body)
        for name, side in (("bids", "BID"), ("asks", "ASK"))
    }
    for statement in method.body:
        if isinstance(statement, ast.AnnAssign):
            target = statement.target
        elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        else:
            continue
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr in expected
            and statement.value is not None
            and ast.dump(statement.value) == expected[target.attr]
        ):
            statement.value = ast.List(elts=[], ctx=ast.Load())
    return method


def methods(node: ast.ClassDef, normalize_init: bool = False) -> dict[str, str]:
    result = {}
    for method in node.body:
        if isinstance(method, ast.FunctionDef):
            if method.name in result:
                raise ValueError(f"duplicate method: {method.name}")
            if normalize_init and method.name == "__init__":
                method = normalize_book_init(method)
            result[method.name] = ast.dump(method, include_attributes=False)
    return result


def validate(markets_dir: Path, layers_dir: Path, compat_dir: Path) -> None:
    for name, digest in SOURCE_SHA256.items():
        path = markets_dir / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"{path}: not the pinned seven-patch ABIDES source")

    original = methods(class_node(markets_dir / "order_book.py", "OrderBook"))
    extracted = {}
    for filename, class_name in LAYERS.items():
        for name, body in methods(
            class_node(layers_dir / filename, class_name),
            normalize_init=filename == "state.py",
        ).items():
            if name in extracted:
                raise ValueError(f"method appears in multiple layers: {name}")
            extracted[name] = body
    check_methods(original, extracted, BOOK_CHANGED_METHODS, "OrderBook")
    original_level = class_node(markets_dir / "price_level.py", "PriceLevel")
    extracted_level = class_node(layers_dir / "price_level.py", "PriceLevel")
    check_methods(
        methods(original_level),
        methods(extracted_level),
        LEVEL_CHANGED_METHODS,
        "PriceLevel",
    )

    # Public signatures and decorators must remain identical even where bodies change.
    for source, candidates in [
        (
            class_node(markets_dir / "order_book.py", "OrderBook"),
            [class_node(layers_dir / file, name) for file, name in LAYERS.items()],
        ),
        (original_level, [extracted_level]),
    ]:
        signatures = {
            m.name: (
                ast.dump(m.args),
                ast.dump(m.returns) if m.returns else None,
                [ast.dump(d) for d in m.decorator_list],
            )
            for node in candidates
            for m in node.body
            if isinstance(m, ast.FunctionDef)
        }
        for m in source.body:
            if isinstance(m, ast.FunctionDef):
                expected = (
                    ast.dump(m.args),
                    ast.dump(m.returns) if m.returns else None,
                    [ast.dump(d) for d in m.decorator_list],
                )
                if signatures[m.name] != expected:
                    raise ValueError(f"public signature differs: {m.name}")

    manifest = json.loads((layers_dir / "overlay_manifest.json").read_text())
    files = overlay_files(layers_dir, compat_dir)
    if set(manifest["sha256"]) != set(files):
        raise ValueError("overlay file inventory differs")
    for name, path in files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"][name]:
            raise ValueError(f"unrecorded overlay change: {name}")

    if ast.get_docstring(
        class_node(layers_dir / "facade.py", "OrderBook")
    ) != ast.get_docstring(class_node(markets_dir / "order_book.py", "OrderBook")):
        raise ValueError("OrderBook class documentation differs")

    for directory in (layers_dir, compat_dir):
        for path in directory.glob("*.py"):
            compile(path.read_text(), str(path), "exec")


def install(markets_dir: Path, source_dir: Path | None = None) -> None:
    source_dir = source_dir or Path(__file__).resolve().parent
    layers_dir = source_dir / "matching"
    compat_dir = source_dir / "matching_compat"
    if (markets_dir / "matching").exists():
        raise ValueError("matching package already exists; require a fresh baseline")
    validate(markets_dir, layers_dir, compat_dir)
    shutil.copytree(
        layers_dir,
        markets_dir / "matching",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for name in SOURCE_SHA256:
        shutil.copyfile(compat_dir / name, markets_dir / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markets_dir", type=Path)
    args = parser.parse_args()
    install(args.markets_dir)


if __name__ == "__main__":
    main()
