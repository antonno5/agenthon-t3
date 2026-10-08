"""Executive summary: compare H01 journal fixtures with the frozen native writer.

Host Arrow checks are preliminary. Without --host this requires pinned Arrow15.
No scenario simulations, scorer copies or performance tuning are performed here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pyarrow as pa
import pyarrow.parquet as pq

BASE = 'ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5'
TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--host', action='store_true')
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
if not a.host:
    assert pa.__version__ == '15.0.2' and sys.version_info[:2] == (3, 11)
a.out = a.out.resolve()
a.out.mkdir(parents=True, exist_ok=False)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

commands = []
def run(cmd, **kwargs):
    commands.append([str(x) for x in cmd])
    subprocess.run(cmd, check=True, timeout=300, **kwargs)

source = ROOT / 'baselines/native'
reference = a.out / 'frozen-native'
shutil.copytree(source, reference)
frozen = json.loads((TESTS / 'base-source-hashes.json').read_text())
assert frozen['base_commit'] == BASE
for name in ('pqwrite.cpp', 'pqwrite.hpp'):
    snapshot = TESTS / ('base_' + name)
    assert sha(snapshot) == frozen['sha256']['baselines/native/' + name]
    shutil.copy2(snapshot, reference / name)
# Protect against accidentally testing a different engine or pipeline in either side.
for name, digest in frozen['sha256'].items():
    if name not in ('baselines/native/pqwrite.cpp', 'baselines/native/pqwrite.hpp'):
        assert sha(ROOT / name) == digest, name
lib = Path(pa.get_library_dirs()[0])
mac = sys.platform == 'darwin'
link = ([str(next(lib.glob('libparquet.*.dylib'))), str(next(lib.glob('libarrow.*.dylib')))] if mac else
        ['-L' + str(lib), '-l:libparquet.so.1500', '-l:libarrow.so.1500']) + ['-Wl,-rpath,' + str(lib)]
flags = ['-std=c++20' if a.host else '-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off',
         '-fno-strict-aliasing', '-Wall', '-pthread']
comparisons, stream_checks, cases = [], [], []
for mode, side, src in [('regular', 'baseline', reference), ('regular', 'candidate', source),
                         ('asan-ubsan', 'candidate', source)]:
    target = a.out / mode / side
    target.mkdir(parents=True)
    exe = target / 'writer-probe'
    extra = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all'] if mode == 'asan-ubsan' else []
    run(['clang++' if mac else 'g++', *flags, *extra, '-I' + str(src), '-I' + pa.get_include(),
         '-DPQSOURCE="' + str(src / 'pqwrite.cpp') + '"', str(TESTS / 'writer_probe.cpp'),
         str(src / 'engine.cpp'), *link, '-o', str(exe)])
    with (target / 'stdout.log').open('w') as log:
        run([str(exe), str(target / 'journals')], stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
                     UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
    cases.append((mode, side, target / 'journals'))

baseline = cases[0][2]
objects = a.out / 'objects'
objects.mkdir()
for mode, side, journals in cases:
    assert {x.name for x in journals.iterdir()} == {x.name for x in baseline.iterdir()}
    for status in journals.glob('*.status'):
        assert status.read_bytes() == (baseline / status.name).read_bytes(), status
    for file in sorted(journals.glob('*.parquet')):
        expected = baseline / file.name
        left, right = pq.read_table(expected), pq.read_table(file)
        assert left.schema.equals(right.schema, check_metadata=True), file
        assert left.equals(right), file
        metadata = pq.ParquetFile(file).metadata
        groups = [metadata.row_group(i).num_rows for i in range(metadata.num_row_groups)]
        assert groups == ([0] if right.num_rows == 0 else
                          [min(1048576, right.num_rows - i) for i in range(0, right.num_rows, 1048576)])
        columns = []
        for i in range(metadata.num_row_groups):
            for j in range(metadata.num_columns):
                col = metadata.row_group(i).column(j)
                assert col.compression == 'SNAPPY', file
                dictionary = 'RLE_DICTIONARY' in col.encodings or 'PLAIN_DICTIONARY' in col.encodings
                if side == 'candidate' and metadata.row_group(i).num_rows:
                    assert dictionary == (col.path_in_schema in ('msg_type', 'side')), (file, col.path_in_schema)
                    assert col.statistics is None, (file, col.path_in_schema)
                columns.append({'group': i, 'column': col.path_in_schema, 'encodings': col.encodings,
                                'statistics_present': col.statistics is not None})
        if right.num_rows > 1:
            if 'trace' in file.name:
                assert right['order_id'][1].as_py() == 2**63 - 1
            else:
                assert right['message_id'][1].as_py() == 2**63 - 1
                assert right['order_id'][1].as_py() in (None, -(2**63))
        digest = sha(file)
        comparisons.append({'mode': mode, 'side': side, 'fixture': file.name, 'rows': right.num_rows,
                            'rowgroups': groups, 'schema_equal_including_metadata': True,
                            'ordered_values_equal': True, 'sha256': digest,
                            'baseline_sha256': sha(expected), 'byte_equal': digest == sha(expected),
                            'bytes': file.stat().st_size, 'baseline_bytes': expected.stat().st_size,
                            'physical_columns': columns})
        canonical = objects / (digest + '.parquet')
        if not canonical.exists():
            os.link(file, canonical)
        elif file.stat().st_ino != canonical.stat().st_ino:
            file.unlink()
            os.link(canonical, file)
    for file in journals.glob('*-table.parquet'):
        stream = file.with_name(file.name.replace('-table', '-stream'))
        assert pq.read_table(file).equals(pq.read_table(stream)), file
        equal = sha(file) == sha(stream)
        if not a.host:
            assert equal, (file, 'pinned table/stream bytes')
        stream_checks.append({'mode': mode, 'side': side, 'fixture': file.name, 'byte_equal': equal})
record = {'executive_summary': 'Journal schemas, ordered values, physical encoding and writer boundaries passed.',
          'scope': 'preliminary host Arrow only' if a.host else 'pinned Arrow15 writer correctness',
          'base_commit': BASE, 'python': sys.version, 'arrow': pa.__version__,
          'sanitizer_scope': 'Own test/native sources instrumented; bundled Arrow libraries uninstrumented.',
          'source_hashes': {str(x.relative_to(ROOT)): sha(x) for x in sorted(source.rglob('*')) if x.is_file()},
          'comparisons': comparisons, 'stream_table_checks': stream_checks, 'commands': commands}
(a.out / 'checks.json').write_text(json.dumps(record, indent=2) + '\n')
print('Passed: ' + str(a.out / 'checks.json'))
