"""Read installed source identity without running a scenario."""

from pathlib import Path
import hashlib
import importlib.metadata
import json


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


markets = Path("/usr/local/lib/python3.11/site-packages/abides_markets")
core = Path("/usr/local/lib/python3.11/site-packages/abides_core")
adapter = Path("/opt/abides_fork")
files = {}
for prefix, root in [("markets", markets), ("core", core), ("adapter", adapter)]:
    for p in root.rglob("*.py"):
        files[prefix + "/" + str(p.relative_to(root))] = sha(p)
for p in adapter.glob("_t3engine*.so"):
    files["native_extension/" + p.name] = sha(p)
print(
    json.dumps(
        {
            "files": files,
            "versions": {
                p: importlib.metadata.version(p)
                for p in ["numpy", "pandas", "pyarrow", "scipy"]
            },
        },
        indent=2,
    )
)
