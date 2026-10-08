"""Executive summary: compile baseline/candidate and verify exact isolated writers and bindings."""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import pyarrow as pa
import pyarrow.parquet as pq

p = argparse.ArgumentParser()
p.add_argument('--host', action='store_true')
p.add_argument('--out', required=True, type=Path)
p.add_argument('--corpus', required=True, type=Path)
a = p.parse_args()
a.out = a.out.resolve()
if not a.host:
    assert sys.version_info[:2] == (3, 11) and pa.__version__ == '15.0.2'
root = Path(__file__).resolve().parents[4]
tests = Path(__file__).resolve().parent
source = root/'baselines/native'
frozen = json.loads((tests.parent/'base-source-hashes.json').read_text())['sha256']
for name, expected in frozen.items():
    if name != 'baselines/native/pqwrite.cpp':
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, name
a.out.mkdir(parents=True, exist_ok=True)
lib = Path(pa.get_library_dirs()[0])
mac = sys.platform == 'darwin'
compiler = 'clang++' if mac else 'g++'
link = ([str(next(lib.glob('libparquet.*.dylib'))), str(next(lib.glob('libarrow.*.dylib')))] if mac else
        ['-L'+str(lib), '-l:libparquet.so.1500', '-l:libarrow.so.1500']) + ['-Wl,-rpath,'+str(lib)]
flags = ['-std=c++20' if a.host else '-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off', '-fno-strict-aliasing', '-Wall', '-pthread']
commands = []
def run(cmd, **kw):
    commands.append([str(x) for x in cmd])
    subprocess.run(cmd, check=True, timeout=300, **kw)

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(tests/'base_pqwrite.cpp') == '2f73e7a8277d02d02b94954f46f37ca09202662b1333a6dc3b775b32abf715bb'
assert digest(tests/'base_pqwrite.hpp') == frozen['baselines/native/pqwrite.hpp']
# Header/engine/pipeline are frozen by the native source audit; baseline writer is
# an exact git-show snapshot from 33027d7, never silently reconstructed.
reference = a.out/'reference-native'
reference.mkdir(exist_ok=True)
for f in source.glob('*'):
    if f.is_file(): shutil.copy2(f, reference/f.name)
shutil.copy2(tests/'base_pqwrite.cpp', reference/'pqwrite.cpp')
shutil.copy2(tests/'base_pqwrite.hpp', reference/'pqwrite.hpp')
comparisons = []
stream_table = []
for sanitize in [False, True]:
    tag = 'asan-ubsan' if sanitize else 'regular'
    extras = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all'] if sanitize else []
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    for side, src in [('baseline', reference), ('candidate', source)]:
        target = a.out/tag/side; target.mkdir(parents=True, exist_ok=True)
        exe = target/'writer-probe'
        run([compiler, *flags, *extras, '-I'+str(src), '-I'+pa.get_include(),
             '-DPQSOURCE="'+str(src/'pqwrite.cpp')+'"', str(tests/'writer_probe.cpp'),
             str(src/'engine.cpp'), *link, '-o', str(exe)])
        with (target/'stdout.log').open('w') as log:
            run([str(exe), str(target/'journals')], stdout=log, stderr=subprocess.STDOUT, env=env)
    left = a.out/tag/'baseline/journals'; right = a.out/tag/'candidate/journals'
    assert {f.name for f in left.iterdir()} == {f.name for f in right.iterdir()}
    for f in left.glob('*.status'):
        assert f.read_bytes() == (right/f.name).read_bytes(), (tag, f.name, 'empty error')
    for f in sorted(left.glob('*.parquet')):
        r = right/f.name
        assert digest(f) == digest(r), (tag, f.name, 'bytes')
        ltab, rtab = pq.read_table(f), pq.read_table(r)
        assert ltab.schema.equals(rtab.schema, check_metadata=True) and ltab.equals(rtab)
        meta = pq.ParquetFile(r).metadata
        rowgroups = [meta.row_group(i).num_rows for i in range(meta.num_row_groups)]
        assert rowgroups == ([0] if rtab.num_rows == 0 else [min(1048576, rtab.num_rows-i) for i in range(0, rtab.num_rows, 1048576)])
        comparisons.append({'mode': tag, 'fixture': f.name, 'sha256': digest(f), 'rows': rtab.num_rows, 'rowgroups': rowgroups, 'byte_equal': True, 'schema_equal': True, 'ordered_values_equal': True})
    for side in ['baseline', 'candidate']:
        journals = a.out/tag/side/'journals'
        for f in journals.glob('*-table.parquet'):
            stream = f.with_name(f.name.replace('-table', '-stream'))
            equal = digest(f) == digest(stream)
            stream_table.append({'mode': tag, 'side': side, 'fixture': f.name, 'byte_equal': equal})
            if not a.host: assert equal, (tag, side, f.name, 'stream/table')
    exe = a.out/tag/'pipeline-test'
    run([compiler, *flags, *extras, '-I'+str(source), str(source/'tests/pipeline_test.cpp'), '-o', str(exe)])
    run([str(exe)], env=env)

binding = {}
for side, src in [('baseline', reference), ('candidate', source)]:
    target = a.out/'bindings'/side; target.mkdir(parents=True, exist_ok=True)
    ext = target/('_t3engine'+sysconfig.get_config_var('EXT_SUFFIX'))
    extra_objects = []
    if not mac:
        svml = target/'svml.o'
        run(['gcc', '-c', str(source/'svml/svml_z0_log_d_la.s'), '-o', str(svml)])
        extra_objects.append(str(svml))
    nplog = src/'nplog.cpp'
    if mac and platform.machine() == 'arm64':
        # This x86-only adapter is irrelevant to the changed writer. Request the
        # existing Python numpy fallback on both sides; never claim pinned parity.
        nplog = target/'host-nplog.cpp'
        nplog.write_text('namespace t3 { bool numpy_log(double, double*) { return false; } const char* numpy_log_dispatch() { return "unknown"; } }\n')
    run([compiler, *flags, *(['-bundle', '-undefined', 'dynamic_lookup'] if mac else ['-shared', '-fPIC']),
         '-I'+str(src), '-I'+pa.get_include(), '-I'+sysconfig.get_path('include'),
         *[str(src/f) for f in ['engine.cpp', 'pqwrite.cpp', 'module.cpp']], str(nplog),
         *extra_objects, *link, '-o', str(ext)])
    result = a.out/'binding-results'/side
    worker = tests/'binding_worker.py'
    run([sys.executable, str(worker), '--module-dir', str(target), '--corpus', str(a.corpus), '--out', str(result), '--adapter-dir', str(root/'baselines')])
    binding[side] = json.loads((result/'summary.json').read_text())
assert binding['baseline'] == binding['candidate']
for f in (a.out/'binding-results/baseline').rglob('*.parquet'):
    other = a.out/'binding-results/candidate'/f.relative_to(a.out/'binding-results/baseline')
    assert digest(f) == digest(other), str(f)
record = {'executive_summary': 'Isolated writer byte/schema/value checks, concurrent writer checks, ASan/UBSan and binding cleanup checks passed.',
          'scope': 'host preliminary only' if a.host else 'pinned correctness', 'python': sys.version, 'arrow': pa.__version__,
          'sanitizer_library_scope': 'Instrumented own native/test sources; bundled Arrow/Parquet libraries are not instrumented.',
          'comparisons': comparisons, 'stream_table_checks': stream_table, 'bindings': binding,
          'source_hashes': {str(f.relative_to(root)): digest(f) for f in sorted(source.rglob('*')) if f.is_file()},
          'commands': commands}
(a.out/'checks.json').write_text(json.dumps(record, indent=2)+'\n')
print('checks passed: '+str(a.out/'checks.json'))
