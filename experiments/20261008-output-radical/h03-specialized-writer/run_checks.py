"""Executive summary: compile real frozen and candidate writers and compare journal semantics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5'
p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--prepare-only', action='store_true')
p.add_argument('--prepared', action='store_true')
p.add_argument('--require-pinned', action='store_true')
p.add_argument('--sanitize', action='store_true')
args = p.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=True)
if args.require_pinned:
    assert pa.__version__ == '15.0.2', pa.__version__
if not args.prepared:
    original = subprocess.check_output(['git', 'show', f'{BASE}:baselines/native/pqwrite.cpp'], cwd=ROOT)
    (out / 'baseline.cpp').write_bytes(original)
if args.prepare_only:
    print(json.dumps({'prepared': str(out / 'baseline.cpp')}))
    sys.exit(0)

def run(command, label):
    with (out / f'{label}.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{label} failed ({result.returncode}); preserved in {out / (label + ".log")}')

lib = Path(pa.get_library_dirs()[0])
std = 'c++17' if pa.__version__ == '15.0.2' else 'c++20'
compiler = os.environ.get('CXX', 'c++')
links = ([str(next(lib.glob('libparquet.[0-9]*.dylib'))), str(next(lib.glob('libarrow.[0-9]*.dylib')))]
         if platform.system() == 'Darwin' else
         [f'-L{lib}', '-l:libparquet.so.1500', '-l:libarrow.so.1500'])
for side, source in [('baseline', out / 'baseline.cpp'), ('candidate', ROOT / 'baselines/native/pqwrite.cpp')]:
    command = [compiler, f'-std={std}', '-O2', '-fno-fast-math', '-ffp-contract=off',
               '-Wall', '-Wextra', '-pthread', f'-I{ROOT / "baselines/native"}', f'-I{pa.get_include()}',
               f'-DPQSOURCE="{source}"', str(HERE / 'tests/writer_probe.cpp'),
               *links, f'-Wl,-rpath,{lib}', '-o', str(out / side)]
    if side == 'candidate':
        command.append('-DSPECIALIZED=1')
    if args.sanitize:
        command.extend(['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g'])
    (out / f'{side}-command.json').write_text(json.dumps(command, indent=2))
    run(command, f'{side}-compile')


candidate_files = out / 'candidate-files'
baseline_files = out / 'baseline-files'
checks = []
empty_schemas = {}
row_counts = [1, 0, 1023, 1024, 1025, 65535, 65536, 65537, 1048575, 1048576, 1048577, 2098689]
for rows in row_counts:
    for side in ['baseline', 'candidate']:
        run([str(out / side), str(out / f'{side}-files'), str(rows)], f'{side}-probe-{rows}')
    for f in sorted(candidate_files.glob('*.parquet')):
        if f.name in {'errors.parquet', 'malformed.parquet'}:
            continue
        b = baseline_files / f.name
        empty_diagnostic = not b.exists() and f.name.startswith('0-')
        candidate = pq.read_table(f)
        if empty_diagnostic:
            baseline = empty_schemas[f.name.split('-', 1)[1]]
        else:
            assert b.exists(), f
            baseline = pq.read_table(b)
        assert baseline.schema.equals(candidate.schema, check_metadata=True), f'schema: {f.name}'
        assert baseline.equals(candidate, check_metadata=True), f'ordered values: {f.name}'
        assert all(not pa.types.is_dictionary(field.type) for field in candidate.schema)
        if rows == 1:
            empty_schemas[f.name.split('-', 1)[1]] = baseline.slice(0, 0)
        checks.append({'file': f.name, 'rows': candidate.num_rows,
                       'empty_host_diagnostic': empty_diagnostic,
                       'candidate_sha256': hashlib.sha256(f.read_bytes()).hexdigest(),
                       'baseline_sha256': hashlib.sha256(b.read_bytes()).hexdigest() if b.exists() else None})
    for f in candidate_files.glob('*-messages-table.parquet'):
        stream = f.with_name(f.name.replace('-table.', '-stream.'))
        assert pq.read_table(f).equals(pq.read_table(stream), check_metadata=True)
    # Successful host fixture values and digests are retained in summary. The
    # generated Parquet files are disposable, preventing large fixture copies.
    for directory in [baseline_files, candidate_files]:
        for f in directory.glob('*.parquet'):
            f.unlink()
summary = {'base': BASE, 'runtime': {'python': platform.python_version(), 'arrow': pa.__version__,
           'system': platform.system(), 'machine': platform.machine(), 'cxx_standard': std},
           'sanitize': args.sanitize, 'comparison': 'schema_metadata_and_ordered_decoded_values_exact',
           'files_checked': len(checks), 'checks': checks,
           'source_sha256': hashlib.sha256((ROOT / 'baselines/native/pqwrite.cpp').read_bytes()).hexdigest()}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k != 'checks'}, indent=2))
