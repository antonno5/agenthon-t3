"""Executive summary: verify binding outputs, compatibility and cleanup per process."""
import argparse
import copy
import json
from pathlib import Path
import sys

p = argparse.ArgumentParser()
p.add_argument('--module-dir', type=Path, required=True)
p.add_argument('--corpus', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--adapter-dir', type=Path)
a = p.parse_args()
a.adapter_dir = a.adapter_dir or Path(__file__).resolve().parents[4]/'baselines'
sys.path[:0] = [str(a.module_dir), str(a.adapter_dir)]
import _t3engine
from abides_fork import native
native._t3engine = _t3engine

a.out.mkdir(parents=True, exist_ok=True)
summary = {}
for name in ['t3-s001-price-time-priority', 't3-s012-partial-fill-cancel-race']:
    scenario = json.loads((a.corpus / name / 'scenario.json').read_text())
    cfg = native.build_native_config(scenario)
    assert cfg is not None
    cols = _t3engine.run(cfg)
    target = a.out / name
    target.mkdir(exist_ok=True)
    # Serialized buffer equality also includes validity masks, string offsets and values.
    digest = __import__('hashlib').sha256()
    for key, value in sorted(cols.items()):
        digest.update(key.encode())
        digest.update(value if isinstance(value, bytes) else str(value).encode())
    result = _t3engine.run_write(cfg, str(target/'trace.parquet'), str(target/'message_trace.parquet'))
    assert result[:2] == (len(cols['t_ns']) // 8, len(cols['m_t_recv']) // 8)
    assert _t3engine.run(cfg) == cols
    assert not list(target.glob('*.pipeline-*'))
    summary[name] = {'buffer_sha256': digest.hexdigest(), 'n_events': result[0], 'n_messages': result[1]}

# Empty trace must preserve existing files and return None; exercise zero and nonzero ledger.
for label, mutate in [('zero', lambda c: c.update(stop_time=c['start_time']-1)),
                      ('no-traders', lambda c: c.update(agents=[]))]:
    c = copy.deepcopy(cfg)
    mutate(c)
    target = a.out / ('empty-' + label)
    target.mkdir(exist_ok=True)
    for name in ['trace.parquet','message_trace.parquet']:
        (target/name).write_bytes(b'existing output')
    assert _t3engine.run_write(c, str(target/'trace.parquet'),str(target/'message_trace.parquet')) is None
    assert all((target/n).read_bytes() == b'existing output' for n in ['trace.parquet','message_trace.parquet'])
    assert not list(target.glob('*.pipeline-*'))
c = copy.deepcopy(cfg)
c['stop_time'] = c['start_time'] - 1
missing = a.out/'missing-empty-parent'
assert _t3engine.run_write(c, str(missing/'trace.parquet'), str(missing/'message_trace.parquet')) is None
assert not missing.exists()
summary['empty-controls'] = 'passed'

# Simulation exception and trace writer failure must join and remove staged message output.
bad = copy.deepcopy(cfg)
ag = list(bad['agents'][0]); ag[0] = 99; bad['agents'][0] = tuple(ag)
for label, c, trace in [('simulation', bad, a.out/'bad-trace.parquet'),
                        ('trace-writer',cfg, a.out/'missing-parent'/'trace.parquet'),
                        ('message-writer',cfg,a.out/'msg-error-trace.parquet')]:
    msg = a.out/(label+'-message.parquet')
    if label == 'message-writer': msg = a.out/'missing-msg-parent'/'message_trace.parquet'
    try:
        _t3engine.run_write(c,str(trace),str(msg))
    except RuntimeError:
        pass
    else:
        raise AssertionError('missing '+label+' exception')
    assert not list(a.out.glob('*.pipeline-*'))
summary['exception-controls'] = 'passed'
(a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
