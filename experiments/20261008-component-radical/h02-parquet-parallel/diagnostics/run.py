"""Executive summary: reproduce fixed paired component diagnostics on the assigned large scenarios only.

Build-only host mode prepares/compiles tools without running performance loops.
Measured mode requires pinned Python/Arrow and a frozen plan plus real journals.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import sysconfig
import pyarrow as pa
import pyarrow.parquet as pq
from instrument import instrument

p = argparse.ArgumentParser()
p.add_argument('--out', type=Path, required=True)
p.add_argument('--build-only', action='store_true')
p.add_argument('--host', action='store_true')
p.add_argument('--plan', type=Path)
p.add_argument('--journals-root', type=Path, help='Focused controls output containing runs/UNIT/correctness-00/baseline/retained')
p.add_argument('--corpus', type=Path)
p.add_argument('--mode', choices=['encode', 'pipeline', 'all'], default='all')
a = p.parse_args()
assert not a.host or a.build_only, 'Host performance loops are intentionally unavailable.'
if not a.host: assert sys.version_info[:2] == (3, 11) and pa.__version__ == '15.0.2'
root = Path(__file__).resolve().parents[4]
here = Path(__file__).resolve().parent
src = root/'baselines/native'
frozen = json.loads((here.parent/'base-source-hashes.json').read_text())['sha256']
for name, expected in frozen.items():
    if name != 'baselines/native/pqwrite.cpp':
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, name
a.out = a.out.resolve(); a.out.mkdir(parents=True, exist_ok=False)
mac = sys.platform == 'darwin'
lib = Path(pa.get_library_dirs()[0])
flags = ['-std=c++20' if a.host else '-std=c++17', '-O2', '-fno-fast-math', '-ffp-contract=off', '-fno-strict-aliasing', '-pthread', '-Wall']
link = ([str(next(lib.glob('libparquet.*.dylib'))), str(next(lib.glob('libarrow.*.dylib')))] if mac else
        ['-L'+str(lib), '-l:libparquet.so.1500', '-l:libarrow.so.1500']) + ['-Wl,-rpath,'+str(lib)]
compiler = 'clang++' if mac else 'g++'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
commands = []
def run(cmd, **kw):
    commands.append(list(map(str, cmd)))
    return subprocess.run(cmd, check=True, timeout=600, **kw)
def dump(path, obj): path.write_text(json.dumps(obj, indent=2)+'\n')

for side in ['baseline', 'candidate']:
    target = a.out/'build'/side; target.mkdir(parents=True)
    source = target/'native'; source.mkdir()
    for f in src.glob('*'):
        if f.is_file(): shutil.copy2(f, source/f.name)
    if side == 'baseline':
        for ext in ['cpp', 'hpp']:
            shutil.copy2(here.parent/'tests'/('base_pqwrite.'+ext), source/('pqwrite.'+ext))
        assert sha(source/'pqwrite.cpp') == frozen['baselines/native/pqwrite.cpp']
        # OutputStream generalization changes only the diagnostic sink type.
        text = (source/'pqwrite.cpp').read_text()
        assert text.count('const std::shared_ptr<arrow::io::FileOutputStream>& sink') == 1
        (source/'pqwrite.cpp').write_text(text.replace('const std::shared_ptr<arrow::io::FileOutputStream>& sink', 'const std::shared_ptr<arrow::io::OutputStream>& sink'))
    run([compiler, *flags, '-I'+str(source), '-I'+pa.get_include(),
         '-DPQSOURCE="'+str(source/'pqwrite.cpp')+'"', *(['-DCANDIDATE'] if side=='candidate' else []),
         str(here/'encode.cpp'), str(source/'engine.cpp'), *link, '-o', str(target/'encode')])
    instrument(source)
    nplog = source/'nplog.cpp'; objects = []
    if mac and platform.machine() == 'arm64':
        nplog = target/'host-nplog.cpp'
        nplog.write_text('namespace t3 { bool numpy_log(double, double*) { return false; } const char* numpy_log_dispatch() { return "unknown"; } }\n')
    if not mac:
        obj = target/'svml.o'; run(['gcc', '-c', str(src/'svml/svml_z0_log_d_la.s'), '-o', str(obj)]); objects.append(str(obj))
    run([compiler, *flags, *(['-bundle', '-undefined', 'dynamic_lookup'] if mac else ['-shared', '-fPIC']),
         '-I'+str(source), '-I'+pa.get_include(), '-I'+sysconfig.get_path('include'),
         *[str(source/f) for f in ['engine.cpp', 'pqwrite.cpp', 'module.cpp']], str(nplog), *objects,
         *link, '-o', str(target/('_t3engine'+sysconfig.get_config_var('EXT_SUFFIX')))])
record = {'executive_summary': 'Fixed paired diagnostics distinguish in-memory encoding, queue waits and overlapped writer wall time.',
          'complete': False, 'rankable': False, 'arrow': pa.__version__, 'python': sys.version,
          'policy': {'warmups_per_side': 1, 'paired_repeats': 5, 'order': ['AB', 'BA', 'AB', 'BA', 'AB'], 'encoder_workers': 2, 'maximum_active_production_threads': 4},
          'boundaries': {'encode': 'Read/combine real columns outside timers; writer setup reported separately; encode and close write to memory; file persistence and hashing outside timers. No simulation or producer wait.',
                         'overlap': 'Two outer caller threads share the same two-worker encoder pool. Wall includes setup/write/close/thread join. Sum of per-file timers overlaps and is never treated as elapsed run time.',
                         'pipeline': 'Direct instrumented run_write: unchanged simulation plus normal file output. Engine includes trace assembly and producer wait. Ledger callbacks include array construction, RecordBatch encoding and group flush. Trace write includes array conversion and file close. Producer condition-variable wait excludes mutex acquisition. Ledger idle is not encode time. finish_wait overlaps work already counted in callbacks. Hashing/import/config parsing outside timer.'},
          'source_hashes': {str(f.relative_to(root)): sha(f) for f in sorted(src.rglob('*')) if f.is_file()},
          'instrumented_hashes': {str(f.relative_to(a.out)): sha(f) for f in sorted((a.out/'build').rglob('*')) if f.is_file() and f.suffix in ['.cpp', '.hpp']},
          'build_commands': commands.copy(), 'samples': [], 'inputs': {}}
dump(a.out/'diagnostics.json', record)
if a.build_only:
    record['build_only'] = True; dump(a.out/'diagnostics.json', record); print('diagnostics compiled'); sys.exit()
assert a.plan and a.journals_root and a.corpus
plan = json.loads(a.plan.read_text())
exp = next(e for e in plan['experiments'] if e['slug']=='h02-parquet-parallel')
assert plan['base_commit'] == '33027d74553e9a318d66557fe0f7b7bed84cfa38'
units = exp['units']
assert units == ['t3-gb-mega-throughput', 't3-gb-pop-horizon-scale', 't3-gb-horizon-240s', 't3-mr-deep-book-state-size']
record['plan_sha256'] = sha(a.plan)
for unit in units:
    journal = a.journals_root/'runs'/unit/'correctness-00/baseline/retained'
    inputs = a.out/'inputs'/unit; inputs.mkdir(parents=True)
    expected = {}
    for name, file in [('trace', 'trace.parquet'), ('messages', 'message_trace.parquet')]:
        original = journal/file; table = pq.read_table(original).combine_chunks()
        expected[file] = sha(original)
        with pa.OSFile(str(inputs/(name+'.arrow')), 'wb') as sink:
            with pa.ipc.new_file(sink, table.schema) as writer: writer.write_table(table)
        record['inputs'][unit+'/'+file] = {'parquet_sha256': expected[file], 'ipc_sha256': sha(inputs/(name+'.arrow')), 'rows': table.num_rows, 'columns': table.num_columns}
    modes = (['trace', 'messages', 'overlap'] if a.mode in ['encode', 'all'] else []) + (['pipeline'] if a.mode in ['pipeline', 'all'] else [])
    for mode in modes:
        schedule = [('warmup', 0, ['baseline', 'candidate'])] + [('pair', i, ['baseline', 'candidate'] if i % 2 == 0 else ['candidate', 'baseline']) for i in range(5)]
        for kind, index, sides in schedule:
            for side in sides:
                target = a.out/'samples'/unit/mode/f'{kind}-{index:02d}'/side; target.mkdir(parents=True)
                build = a.out/'build'/side
                if mode == 'pipeline':
                    cmd = [sys.executable, str(here/'pipeline_worker.py'), '--module-dir', str(build), '--adapter-dir', str(root/'baselines'),
                           '--scenario', str(a.corpus/unit/'scenario.json'), '--out', str(target)]
                else: cmd = [str(build/'encode'), str(inputs), mode, str(target)]
                with (target/'stdout.log').open('w') as stdout, (target/'stderr.log').open('w') as stderr:
                    run(cmd, stdout=stdout, stderr=stderr)
                result = json.loads((target/'stdout.log').read_text())
                digests = {f.name: sha(f) for f in target.glob('*.parquet')}
                assert digests and all(digest==expected[name] for name, digest in digests.items()), (unit, mode, side, digests, expected)
                sample = {'unit': unit, 'mode': mode, 'kind': kind, 'pair': index, 'side': side, 'result': result,
                          'command': cmd, 'byte_equal_to_real_baseline': True, 'sha256': digests}
                record['samples'].append(sample); dump(a.out/'diagnostics.json', record)
                # Keep all clocks/digests/logs; output columns already live in the
                # coordinator's validated object store. Avoid redundant large copies.
                for f in target.glob('*.parquet'): f.unlink()
    for f in inputs.glob('*.arrow'): f.unlink()
record['medians'] = []
for unit in units:
    for mode in ['trace', 'messages', 'overlap', 'pipeline']:
        samples = [s for s in record['samples'] if s['unit']==unit and s['mode']==mode and s['kind']=='pair']
        if not samples: continue
        field = 'run_write_wall_seconds' if mode=='pipeline' else 'wall_seconds'
        med = {side: statistics.median(s['result'][field] for s in samples if s['side']==side) for side in ['baseline', 'candidate']}
        record['medians'].append({'unit': unit, 'mode': mode, 'clock': field, 'seconds': med,
                                  'time_change_pct': 100*(med['candidate']/med['baseline']-1),
                                  'time_reduction_pct': 100*(1-med['candidate']/med['baseline']),
                                  'speedup': med['baseline']/med['candidate']})
        if mode != 'pipeline':
            for journal in (['trace', 'messages'] if mode == 'overlap' else [mode]):
                encode = {side: statistics.median(s['result'][journal]['write_seconds'] + s['result'][journal]['close_seconds']
                                                  for s in samples if s['side']==side) for side in ['baseline', 'candidate']}
                record['medians'].append({'unit': unit, 'mode': mode, 'clock': journal+'_write_plus_close_seconds',
                                          'seconds': encode, 'time_change_pct': 100*(encode['candidate']/encode['baseline']-1),
                                          'time_reduction_pct': 100*(1-encode['candidate']/encode['baseline']),
                                          'speedup': encode['baseline']/encode['candidate'],
                                          'overlaps_other_journal': mode == 'overlap'})
record['complete'] = True; dump(a.out/'diagnostics.json', record)
print('fixed diagnostics complete')
