"""Executive summary: hold one shared Docker slot for checks, diagnostics and fixed timing."""
from pathlib import Path
import datetime
import json
import subprocess
import sys

area=Path(__file__).resolve().parent
root=area.parents[2]
evidence=area/'evidence'
evidence.mkdir(exist_ok=True)
assert (root.parents[1]/'docker-slot-owner.json').exists()
state={'executive_summary':'One coordinator-authorized sequential H1 campaign; every stage and failure is retained.',
       'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'stages':[],'complete':False}
def save():
    (evidence/'phase2-chain.json').write_text(json.dumps(state,indent=2)+'\n')
save()
for stage in ['checks','component','timing']:
    command=[sys.executable,str(area/'phase2.py'),'--stage',stage,'--coordinator-dispatch']
    record={'stage':stage,'command':command,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'log':str(evidence/('phase2-'+stage+'.log'))}
    state['stages'].append(record);save()
    print('H1 stage started: '+stage,flush=True)
    with Path(record['log']).open('w') as log:
        process=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        for line in process.stdout:
            log.write(line);log.flush();print(line,end='',flush=True)
        code=process.wait()
    record.update(exit_code=code,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save()
    if code: raise SystemExit(code)
state['complete']=True;save()
print('H1 authorized campaign complete',flush=True)
