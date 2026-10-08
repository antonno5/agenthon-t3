"""Executive summary: test combined bindings and failure cleanup in the pinned runtime."""
import json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2];report=Path(__file__).resolve().parent
out=report/'evidence/pinned-bindings';out.mkdir()
record=json.loads((report/'build-record.json').read_text());image=record['candidate_image']
docker=['docker','--context','colima-agenthon']
assert not subprocess.check_output(docker+['ps','-q'],text=True).strip()
command=docker+['run','--rm','--platform=linux/amd64','--network=none','--cpus=4','--memory=16g','--memory-swap=16g','-v',str(root)+':/repo:ro','-v',str(out)+':/checks','-v',str(report/'evidence/build/baseline-reference')+':/opt/h02-reference:ro',image,'python','/repo/expirements/20261008-ledger-arena-develop/tests/run_pinned.py','--corpus','/repo/units','--out','/checks','--checker','/repo/scripts/run_differential_experiment.py']
(out/'command.json').write_text(json.dumps(command,indent=2)+'\n')
with (out/'stdout.log').open('w') as stdout,(out/'stderr.log').open('w') as stderr:
 p=subprocess.run(command,stdout=stdout,stderr=stderr)
(out/'exit.json').write_text(json.dumps({'exit_code':p.returncode})+'\n');p.check_returncode()
print('pinned bindings passed',flush=True)
