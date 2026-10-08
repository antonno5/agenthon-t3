"""Executive summary: compare baseline/candidate bindings and cleanup in pinned image."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pyarrow
assert sys.version_info[:2] == (3,11)
assert pyarrow.__version__=='15.0.2'
p=argparse.ArgumentParser()
p.add_argument('--corpus',required=True,type=Path)
p.add_argument('--out',required=True,type=Path)
p.add_argument('--checker',required=True,type=Path)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
script=Path(__file__).with_name('extension_worker.py')
results={}
for side,module_dir in [('baseline','/opt/h02-reference'),('candidate','/opt/abides_fork')]:
    subprocess.run([sys.executable,str(script),'--module-dir',module_dir,'--adapter-dir','/opt',
                    '--corpus',str(a.corpus),'--out',str(a.out/side)],check=True)
    results[side]=json.loads((a.out/side/'summary.json').read_text())
assert results['baseline']==results['candidate']
spec=importlib.util.spec_from_file_location('checker',a.checker)
d=importlib.util.module_from_spec(spec);sys.modules[spec.name]=d;spec.loader.exec_module(d)
comparisons={}
for unit in ['t3-s001-price-time-priority','t3-s012-partial-fill-cancel-race']:
    for filename in ['trace.parquet','message_trace.parquet']:
        r=d.compare_parquet(a.out/'baseline'/unit/filename,a.out/'candidate'/unit/filename)
        assert r['byte_equal'] and r['schema_equal'] and r['semantic_exact_equal'],r
        comparisons[unit+'/'+filename]=r
(a.out/'pinned-binding-checks.json').write_text(json.dumps({'executive_summary':'Pinned binding and journal checks passed.',
    'binding':results,'comparisons':comparisons},indent=2)+'\n')
