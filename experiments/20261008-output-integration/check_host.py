"""Executive summary: check the combined sources locally without Docker or timing.

Reuse the original H1/H2 probes with temporary outputs. Host Arrow25/libm checks
do not replace the prior pinned Arrow15/x86 experiment validation.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

artifact = pathlib.Path(__file__).resolve().parent
root = artifact.parents[1]
src = root / "baselines/native"
previous = root / "experiments/20261008-output-radical"
commands = []


def run(argv, **kwargs):
    commands.append([str(x) for x in argv])
    return subprocess.run(argv, check=True, timeout=180, capture_output=True, text=True, **kwargs)


def digest(data):
    return hashlib.sha256(data).hexdigest()


identity = {}
for revision, names in (
    ("fc1fff3ac35152577a4fb4cabd5197dd596325d3", ["baselines/native/pqwrite.cpp", "baselines/native/pqwrite.hpp"]),
    ("a91b789ef63f7bb0a70e7a734e5657a999b90c10", ["baselines/build_executable.py", "baselines/native/cli.cpp",
      "baselines/native/scenario.hpp", "baselines/native/sha256.hpp", "baselines/native/vendor/json.hpp",
      "baselines/native/vendor/LICENSE.json", "baselines/native/vendor/README.md"]),
):
    for name in names:
        frozen = subprocess.run(["git", "show", f"{revision}:{name}"], cwd=root, check=True, capture_output=True).stdout
        actual = (root / name).read_bytes()
        assert actual == frozen, name
        identity[name] = {"experiment_revision": revision, "sha256": digest(actual), "exact": True}

result = {"pass": False, "docker_builds": 0, "docker_test_runs": 0, "timing_runs": 0,
          "platform": sys.platform, "arrow_version": pa.__version__, "source_identity": identity}
with tempfile.TemporaryDirectory(prefix="t3-output-integration-") as temp:
    tmp = pathlib.Path(temp)
    mapper = tmp / "mapper"
    run(["c++", "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off", f"-I{src}",
         str(previous / "h02-native-executable/tests/mapper.cpp"), "-o", str(mapper)])
    # Only redirect the historical check's report destination; retain all fixtures/assertions.
    check = (previous / "h02-native-executable/tests/check_mapping.py").read_text()
    original = '(artifact / "evidence/mapping-checks.json")'
    assert check.count(original) == 1
    check = check.replace(original, f"Path({str(tmp / 'mapping.json')!r})")
    run([sys.executable, "-c", "import sys; sys.argv = " + repr([str(previous / "h02-native-executable/tests/check_mapping.py"), str(mapper)])
         + "; __file__ = sys.argv[0]; exec(compile(" + repr(check) + ", __file__, 'exec'))"])
    result["mapping"] = json.loads((tmp / "mapping.json").read_text())
    run(["c++", "-std=c++20", "-fsyntax-only", f"-I{src}", f"-I{pa.get_include()}", str(src / "cli.cpp")])
    result["cli_host_syntax"] = True

    probe = (previous / "h01-parquet-encoding/tests/writer_probe.cpp").read_text()
    start = probe.index("  for (size_t n : {")
    end = probe.index(") {", start)
    probe = probe[:start] + "  for (size_t n : {size_t(0), size_t(1), size_t(1025), size_t(65537)}" + probe[end:]
    (tmp / "probe.cpp").write_text(probe)
    library = pathlib.Path(pa.get_library_dirs()[0])
    links = [str(next(library.glob("libparquet.*.dylib"))), str(next(library.glob("libarrow.*.dylib")))]
    for side in ("baseline", "candidate"):
        folder = tmp / side
        folder.mkdir()
        if side == "baseline":
            source = tmp / "frozen-writer"
            source.mkdir()
            for name in ("pqwrite.cpp", "pqwrite.hpp"):
                (source / name).write_bytes((previous / "h01-parquet-encoding/tests" / ("base_" + name)).read_bytes())
        else:
            source = src
        binary = tmp / (side + "-probe")
        run(["c++", "-std=c++20", "-O2", "-fno-fast-math", "-ffp-contract=off", "-pthread",
             f"-I{src}", f"-I{pa.get_include()}", '-DPQSOURCE="' + str(source / "pqwrite.cpp") + '"',
             str(tmp / "probe.cpp"), str(src / "engine.cpp"), *links, f"-Wl,-rpath,{library}", "-o", str(binary)])
        run([str(binary), str(folder)])
    comparisons = []
    left, right = tmp / "baseline", tmp / "candidate"
    assert {p.name for p in left.iterdir()} == {p.name for p in right.iterdir()}
    for file in sorted(right.iterdir()):
        baseline = left / file.name
        if file.suffix == ".status":
            assert file.read_bytes() == baseline.read_bytes(), file.name
            continue
        a, b = pq.read_table(baseline), pq.read_table(file)
        assert a.schema.equals(b.schema, check_metadata=True) and a.equals(b), file.name
        meta, oldmeta = pq.ParquetFile(file).metadata, pq.ParquetFile(baseline).metadata
        assert [meta.row_group(i).num_rows for i in range(meta.num_row_groups)] == [oldmeta.row_group(i).num_rows for i in range(oldmeta.num_row_groups)]
        for i in range(meta.num_row_groups):
            group = meta.row_group(i)
            for j in range(group.num_columns):
                column = group.column(j)
                assert column.compression == "SNAPPY" and column.statistics is None
                if group.num_rows:
                    dictionary = bool({"RLE_DICTIONARY", "PLAIN_DICTIONARY"}.intersection(column.encodings))
                    assert dictionary == (column.path_in_schema in ("msg_type", "side"))
        comparisons.append({"fixture": file.name, "rows": b.num_rows, "schema_metadata_and_ordered_values_exact": True})
    result["writer_comparisons"] = comparisons
    result["writer_error_and_empty_status_exact"] = True

for path in (root / "baselines/build_executable.py", root / "baselines/abides_fork/native.py"):
    compile(path.read_text(), str(path), "exec")
run([sys.executable, str(root / "tests/test_verb_dispatch.py")])
run(["git", "diff", "--check"], cwd=root)
result["verb_dispatch_checks"] = 7
result["python_syntax_and_diff_check"] = True
result["limitations"] = ["Host ARM/libm mapping only; no production x86 executable link or run.",
                         "Host Arrow25 writer fixtures only; pinned Arrow15 validation is historical.",
                         "Combined performance and complete-container correctness were not measured."]
result["pass"] = True
(artifact / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"pass": True, "mapping_checks": result["mapping"]["count"],
                  "writer_comparisons": len(result["writer_comparisons"]), "docker_runs": 0}))
