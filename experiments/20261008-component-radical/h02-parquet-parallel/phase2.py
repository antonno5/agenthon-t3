"""Executive summary: hold the shared Docker slot for the complete fixed H2 campaign."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
report = Path(__file__).resolve().parent
root = report.parents[2]
out = report/'evidence/phase2'; out.mkdir(exist_ok=True, parents=True)
commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
frozen=json.loads((report/'host-validation.json').read_text())['source_hashes']
for path,digest in frozen.items():
    assert hashlib.sha256((root/path).read_bytes()).hexdigest()==digest, path
assert not subprocess.check_output(['git','diff','HEAD','--','baselines'],cwd=root)
assert not (out/'status.json').exists(), 'Fixed campaign already started; do not add adaptive repeats.'
env = dict(os.environ,H02_PHASE2_AUTHORIZED='yes')
record = {'executive_summary':'Sequential H2 campaign inside the shared exclusive Docker slot; no adaptive performance repeats.',
          'implementation_commit':'c9ec65640d6904ab01a26d2369caef5075aca86b',
          'campaign_checkout_commit':commit,'started_unix':time.time(),'steps':[],'complete':False}
state = out/'status.json'
def dump(): state.write_text(json.dumps(record,indent=2)+'\n')
dump()
for step in ['build','runtime-audit','isolated','controls','diagnostic-build','timing','diagnostics']:
    command=['bash',str(report/'recipe.sh'),step]
    if step=='runtime-audit':
        docker=['docker','--context','colima-agenthon']
        image=subprocess.check_output(docker+['image','inspect','--format','{{.Id}}','track3-component-h02-parquet-parallel:phase2'],text=True).strip()
        record['candidate_image']=image
        command=[sys.executable,str(report/'audit_images.py'),image]
    item = {'step':step,'start_unix':time.time(),'command':command}
    record['steps'].append(item); dump()
    with (out/(step+'.stdout.log')).open('w') as stdout, (out/(step+'.stderr.log')).open('w') as stderr:
        p = subprocess.run(item['command'],cwd=root,env=env,stdout=stdout,stderr=stderr)
    item.update(exit_code=p.returncode,finish_unix=time.time()); dump()
    if p.returncode:
        record['error'] = 'Step failed: '+step; dump(); sys.exit(p.returncode)
record['complete']=True;record['finish_unix']=time.time();dump()
