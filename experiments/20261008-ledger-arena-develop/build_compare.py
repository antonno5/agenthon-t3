"""Executive summary: build a combined image and retain immutable-source provenance."""
import hashlib,json,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2]
report=Path(__file__).resolve().parent
out=report/'evidence/build';out.mkdir()
plan=json.loads((report/'plan.json').read_text())
docker=['docker','--context','colima-agenthon']
def run(args,**kw):
    return subprocess.run(args,check=True,**kw)
def inspect(image):
    return json.loads(subprocess.check_output(docker+['image','inspect',image],text=True))[0]
def dump(name,value): (out/name).write_text(json.dumps(value,indent=2)+'\n')
assert not subprocess.check_output(docker+['ps','-q'],text=True).strip()
base=inspect(plan['baseline_tag']);assert base['Id']==plan['baseline_image'];dump('baseline-before.json',base)
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert not subprocess.check_output(['git','diff','HEAD','--','baselines'],cwd=root)
builder='track3-ledger-arena-builder:286ae97';candidate='track3-ledger-arena:286ae97'
commands=[]
for target,tag in [('builder',builder),(None,candidate)]:
    command=docker+['build','--platform=linux/amd64','-f',str(report/'Dockerfile'),'-t',tag]
    if target: command+=['--target',target]
    command+=['--build-arg','BASE_IMAGE='+plan['baseline_tag'],str(root)];commands.append(command)
    with (out/(('builder' if target else 'candidate')+'-build.log')).open('w') as log:
        run(command,stdout=log,stderr=subprocess.STDOUT)
    print('built',tag,flush=True)
assert inspect(plan['baseline_tag'])['Id']==base['Id'];dump('baseline-after.json',inspect(plan['baseline_tag']))
cand=inspect(candidate);dump('candidate-inspect.json',cand)
for image,items in [(builder,[('/native-output/h02-checks/pinned-build-checks.json',out/'pinned-build-checks.json'),('/native-output/h02-checks/native-build-audit.json',out/'native-build-audit.json')]),(plan['baseline_image'],[('/opt/abides_fork',out/'baseline-reference')])]:
    container=subprocess.check_output(docker+['create',image],text=True).strip()
    try:
        for src,dst in items: run(docker+['cp',container+':'+src,str(dst)])
    finally: run(docker+['rm',container],stdout=subprocess.DEVNULL)
record={'executive_summary':'Combined candidate built on the immutable previous runtime. Previous develop differs from the original image source only in reports; baselines sources are identical.','base_commit':plan['base_commit'],'baseline_image':base['Id'],'baseline_image_source_commit':plan['baseline_source_commit'],'candidate_implementation_commit':commit,'candidate_image':cand['Id'],'candidate_tag':candidate,'commands':commands,'host_checks':json.loads((report/'evidence/host/checks.json').read_text()),'pinned_build_checks':json.loads((out/'pinned-build-checks.json').read_text()),'native_build_audit':json.loads((out/'native-build-audit.json').read_text())}
(report/'build-record.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'candidate':cand['Id'],'commit':commit}),flush=True)
