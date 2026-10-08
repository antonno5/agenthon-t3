"""Executive summary: run pinned H3 build and correctness under the shared exclusive slot.

No component or complete-container timing campaign is launched here.
Invoke this complete subprocess through campaign/docker_slot.py.
"""
import hashlib, json, os, subprocess, sys
from pathlib import Path
AREA=Path(__file__).resolve().parent
ROOT=AREA.parents[2]
CAMPAIGN=ROOT.parents[1]
PYTHON='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
AUDIT=Path('/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/experiments/20261008-component-radical/baseline-audit.json')

def main():
    # Owner exists only while the shared lock wrapper owns the slot.
    assert (CAMPAIGN/'docker-slot-owner.json').exists(), 'Invoke through docker_slot.py'
    recipe=json.loads((AREA/'recipe.json').read_text()); audit=json.loads(AUDIT.read_text())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    commands={k:[x.replace('IMPLEMENTATION_SHORT_COMMIT',commit[:7]).replace('IMPLEMENTATION_COMMIT',commit) for x in v] for k,v in recipe.items() if isinstance(v,list) and v and isinstance(v[0],str)}
    logdir=AREA/'artifacts/phase2a'; logdir.mkdir(parents=True,exist_ok=True)
    manifest=AREA/'phase2a-execution.json'
    history=json.loads(manifest.read_text())['operations'] if manifest.exists() else []
    result={'executive_summary':'Pinned build, column/sanitizer checks, structural diagnostics and full controls before timing. Every failure and command is retained.','checked_build_commit':commit,'complete':False,'operations':history,'timing_campaign_executed':False,'resolutions':['First pinned check could not load libasan.so.8. Linux test-only sanitizer binaries now link ASan/UBSan statically; no production source/runtime/dependency changes.']}
    def save(): manifest.write_text(json.dumps(result,indent=2)+'\n')
    def run(name,command):
        log=logdir/f'{len(history):02d}-{name}.log'
        record={'name':name,'command':command,'log':str(log),'returncode':None};history.append(record);save()
        print('START',name,flush=True)
        with log.open('w') as f:
            process=subprocess.run(command,cwd=ROOT,text=True,stdout=f,stderr=subprocess.STDOUT)
        record['returncode']=process.returncode;record['log_sha256']=hashlib.sha256(log.read_bytes()).hexdigest();save()
        if process.returncode:
            print(log.read_text()[-12000:],flush=True)
            raise RuntimeError(f'{name} failed; retained log {log}')
        print('PASS',name,flush=True)
        return log.read_text().strip()
    docker=['docker','--context','colima-agenthon']
    tagcmd=docker+['image','inspect','--format','{{.Id}}','track3-ledger-arena:286ae97','track3-ledger-arena-builder:286ae97']
    def inspect_tags(name):
        ids=run(name,tagcmd).splitlines();assert ids==[audit['baseline_image'],audit['builder_image']],ids
    inspect_tags('audit-tags-before')
    run('export-base-and-inputs',commands['host_export_pinned_sources'])
    run('candidate-build',commands['candidate_build'])
    inspect_tags('audit-tags-after')
    tag=commands['candidate_build'][commands['candidate_build'].index('-t')+1]
    image=run('candidate-image-id',docker+['image','inspect','--format','{{.Id}}',tag])
    result['candidate_image']=image;result['candidate_tag']=tag;save()
    for phase in ['pinned_remap','pinned_build_tests','pinned_checks','pinned_counters']:run(phase,commands[phase])
    runtime_code='''import hashlib,json,pathlib,platform,numpy,pandas,pyarrow,scipy
from abides_fork import _t3engine
p=pathlib.Path(_t3engine.__file__)
print(json.dumps(dict(python=platform.python_version(),platform=platform.machine(),numpy=numpy.__version__,pandas=pandas.__version__,pyarrow=pyarrow.__version__,scipy=scipy.__version__,native_path=str(p),native_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),python_hashes={str(f.relative_to(p.parent)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.parent.rglob('*.py'))})))'''
    snapshots={}
    for side,img in [('baseline',audit['baseline_image']),('candidate',image)]:
        text=run('runtime-'+side,docker+['run','--rm','--platform','linux/amd64','--cpus=4','--memory=16g','--memory-swap=16g','--network=none','--entrypoint','python',img,'-c',runtime_code]); snapshots[side]=json.loads(text)
        wanted={'python':'3.11.17','platform':'x86_64','numpy':'1.26.4','pandas':'1.5.3','pyarrow':'15.0.2','scipy':'1.17.1'}
        assert {k:snapshots[side][k] for k in wanted}==wanted
    assert snapshots['baseline']['python_hashes']==snapshots['candidate']['python_hashes']
    assert snapshots['baseline']['native_sha256']==audit['runtime']['native_sha256']
    result['runtime_audit']=snapshots;save()
    controls=AREA/'artifacts/controls-pinned'
    assert not controls.exists(), 'Retain failed controls; choose a distinct retry directory'
    controls_command=[PYTHON,str(CAMPAIGN/'run_focused.py'),'--slug','h03-protocol-fusion','--candidate-image',image,'--candidate-commit',commit,'--controls-only','--out',str(controls)]
    run('controls-only',controls_command)
    summary=json.loads((controls/'summary.json').read_text());assert summary['complete'] and summary['accepted']
    result.update(complete=True,controls_summary=str(controls/'summary.json'),controls_summary_sha256=hashlib.sha256((controls/'summary.json').read_bytes()).hexdigest());save()
    print(json.dumps({'complete':True,'commit':commit,'candidate_image':image,'controls':str(controls)}),flush=True)
if __name__=='__main__':main()
