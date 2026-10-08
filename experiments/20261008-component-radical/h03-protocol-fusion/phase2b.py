"""Executive summary: run one fixed H3 component and primary campaign under one shared lock.

The prepared native sources, component binaries and pinned images are reused.
No timing campaign is repeated or adapted after its results are inspected.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path
AREA=Path(__file__).resolve().parent
ROOT=AREA.parents[2]
CAMPAIGN=ROOT.parents[1]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--frozen-commit',required=True);args=ap.parse_args()
    assert (CAMPAIGN/'docker-slot-owner.json').exists(), 'Invoke whole chain through docker_slot.py'
    ready=json.loads((CAMPAIGN/'PINNED-READY-h03-protocol-fusion.json').read_text())
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head==args.frozen_commit
    assert not subprocess.check_output(['git','diff','HEAD','--','baselines'],cwd=ROOT)
    binaries={s:AREA/'artifacts/pinned/bin'/f'{s}-component' for s in ['base','candidate']}
    def verify():
        sources={p:sha(ROOT/p) for p in ready['source_hashes']}
        hashes={s:sha(p) for s,p in binaries.items()}
        assert sources==ready['source_hashes'];assert hashes==ready['component_binary_sha256']
        for item in json.loads((AREA/'pinned-inputs.json').read_text())['inputs']:
            assert sha(AREA/'artifacts/pinned/inputs'/Path(item['path']).name)==item['mapped_sha256']
        return dict(source_hashes=sources,component_binary_sha256=hashes)
    before=verify()
    assert not (AREA/'component-pinned.json').exists()
    assert not (AREA/'focused-pinned').exists()
    result={'executive_summary':'One frozen uninstrumented component campaign followed by one primary container campaign, held under the same exclusive Docker slot. Every failure and sample is retained.','frozen_commit':head,'candidate_image':ready['candidate_image_id'],'complete':False,'before':before,'operations':[]}
    manifest=AREA/'performance-execution.json';assert not manifest.exists()
    logdir=AREA/'artifacts/performance';logdir.mkdir(parents=True,exist_ok=True)
    def save():manifest.write_text(json.dumps(result,indent=2)+'\n')
    def run(name,command):
        print('START',name,flush=True)
        record=dict(name=name,command=command,returncode=None,log=str(logdir/(name+'.log')))
        result['operations'].append(record);save()
        with Path(record['log']).open('w') as stream:
            process=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        record.update(returncode=process.returncode,log_sha256=sha(Path(record['log'])));save()
        if process.returncode:
            result['error']=Path(record['log']).read_text()[-20000:];save()
            raise RuntimeError(name+' failed; campaign is retained and will not be rerun')
        print('PASS',name,flush=True)
    try:
        docker=['docker','--context','colima-agenthon']
        command=docker+['image','inspect','--format','{{.Id}}',ready['baseline_image_id'],ready['candidate_image_id']]
        run('immutable-image-audit',command)
        assert (logdir/'immutable-image-audit.log').read_text().splitlines()==[ready['baseline_image_id'],ready['candidate_image_id']]
        run('component',ready['pending_component_command'][3:])
        primary=ready['pending_timing_command'][3:]
        primary[primary.index('--candidate-commit')+1]=head
        run('primary',primary)
        result['complete']=True
    finally:
        result['after']=verify();save()
    print(json.dumps(dict(complete=True,frozen_commit=head,candidate_image=ready['candidate_image_id'])),flush=True)
if __name__=='__main__':main()
