"""Executive summary: run one diagnostic market and expose queue waits separately from writer callbacks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
p = argparse.ArgumentParser()
p.add_argument('--module-dir', type=Path, required=True)
p.add_argument('--adapter-dir', type=Path, required=True)
p.add_argument('--scenario', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
sys.path[:0] = [str(a.module_dir), str(a.adapter_dir)]
import _t3engine
from abides_fork import native
native._t3engine = _t3engine
cfg = native.build_native_config(json.loads(a.scenario.read_text()))
assert cfg is not None
a.out.mkdir(parents=True, exist_ok=True)
begin = time.perf_counter()
r = _t3engine.run_write(cfg, str(a.out/'trace.parquet'), str(a.out/'message_trace.parquet'))
wall = time.perf_counter()-begin
assert r is not None and len(r) == 11
names = ['events', 'messages', 'engine_including_producer_wait_seconds',
         'producer_wait_seconds', 'ledger_write_callbacks_seconds', 'ledger_close_seconds',
         'trace_write_seconds', 'finish_wait_seconds', 'ledger_dispatcher_idle_seconds',
         'ledger_callback_count', 'producer_submit_count']
result = dict(zip(names, r)); result['run_write_wall_seconds'] = wall
result['sha256'] = {f: hashlib.sha256((a.out/f).read_bytes()).hexdigest()
                    for f in ['trace.parquet', 'message_trace.parquet']}
assert not list(a.out.glob('*.pipeline-*'))
print(json.dumps(result))
