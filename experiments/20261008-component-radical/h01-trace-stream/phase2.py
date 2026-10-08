"""Executive summary: coordinator-dispatched pinned checks, component diagnostics and fixed timing.

Run this only under the campaign docker_slot.py after the coordinator dispatches a
stage. It never expands the frozen scenario selection or retimes a viewed result.
"""
from pathlib import Path
import argparse
import hashlib
import json
import statistics
import subprocess
import sys

AREA=Path(__file__).resolve().parent
ROOT=AREA.parents[2]
CAMPAIGN=ROOT.parents[1]
SLUG='h01-trace-stream'
BASE='sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c'
BUILDER='sha256:902a221eca63fc3781587c30114edd3d33e16d057049b30a23b552a0e4bc0d57'
TAG='track3-component-h01-trace-stream:33027d7'
DOCKER=['docker','--context','colima-agenthon']


def dump(p,v): p.write_text(json.dumps(v,indent=2)+'\n')


def output(argv):
    return subprocess.check_output([str(x) for x in argv],cwd=ROOT,text=True).strip()


def run(argv): subprocess.run([str(x) for x in argv],cwd=ROOT,check=True)


def inspect(image): return json.loads(output([*DOCKER,'image','inspect',image]))[0]


def sources():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'baselines/native').rglob('*')) if p.is_file()}


def pinned(argv, corpus=False):
    mounts=['-v',str(ROOT)+':/work','-w','/work']
    if corpus:
        plan=json.loads((AREA/'plan-snapshot.json').read_text())
        mounts+=['-v',plan['corpus']+':/corpus:ro']
    return [*DOCKER,'run','--rm','--platform=linux/amd64','--cpus=4','--memory=16g',
            '--memory-swap=16g','--network=none',*mounts,BUILDER,*argv]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['checks','component','timing'],required=True)
    ap.add_argument('--coordinator-dispatch',action='store_true',required=True)
    args=ap.parse_args()
    assert (CAMPAIGN/'docker-slot-owner.json').exists(), 'shared Docker slot must enclose this process'
    manifest=json.loads((AREA/'source-manifest.json').read_text())
    before=sources(); assert before==manifest['source_hashes'], 'native sources changed'
    assert not output(['git','diff','HEAD','--','baselines']), 'implementation must be committed'
    commit=output(['git','rev-parse','HEAD'])
    original=AREA/'evidence/build/original_engine.cpp'
    visible=AREA/'evidence/build/base_engine.cpp'
    assert hashlib.sha256(original.read_bytes()).hexdigest()==manifest['original_engine_sha256']
    assert hashlib.sha256(visible.read_bytes()).hexdigest()==manifest['visibility_only_engine_sha256']
    evidence=AREA/'evidence'; evidence.mkdir(exist_ok=True)
    rel='/work/'+str(AREA.relative_to(ROOT))
    if args.stage=='checks':
        assert inspect('track3-ledger-arena:286ae97')['Id']==BASE
        assert inspect('track3-ledger-arena-builder:286ae97')['Id']==BUILDER
        runtime=json.loads(output(pinned(['python','-c',
            "import json,platform,importlib.metadata as m; print(json.dumps({'python':platform.python_version(),'packages':{x:m.version(x) for x in ['numpy','pandas','pyarrow','scipy']}}))"])))
        assert runtime=={'python':'3.11.17','packages':{'numpy':'1.26.4','pandas':'1.5.3','pyarrow':'15.0.2','scipy':'1.17.1'}}
        run([*DOCKER,'build','--platform=linux/amd64','--network=none','-f',CAMPAIGN/'Dockerfile',
             '--build-arg','BASE_IMAGE=track3-ledger-arena:286ae97',
             '--build-arg','BUILDER_IMAGE=track3-ledger-arena-builder:286ae97','-t',TAG,'.'])
        assert inspect('track3-ledger-arena:286ae97')['Id']==BASE
        assert inspect('track3-ledger-arena-builder:286ae97')['Id']==BUILDER
        candidate=inspect(TAG)
        layers=inspect(BASE)['RootFS']['Layers']
        assert candidate['RootFS']['Layers'][:len(layers)]==layers
        image={'executive_summary':'Native extension overlay on the unchanged audited pinned runtime.',
               'implementation_commit':commit,'candidate_image':candidate['Id'],'baseline_image':BASE,
               'builder_image':BUILDER,'builder_runtime':runtime,'source_hashes':before}
        dump(AREA/'image.json',image)
        run(pinned(['python',rel+'/tests/checks.py','--plan',rel+'/plan-snapshot.json',
                    '--no-prepare','--corpus','/corpus','--sanitizers','--compiler','g++',
                    '--output',rel+'/pinned-standalone.json'],corpus=True))
        run([sys.executable,CAMPAIGN/'run_focused.py','--slug',SLUG,'--candidate-image',candidate['Id'],
             '--candidate-commit',commit,'--controls-only','--out',evidence/'pinned-controls'])
    elif args.stage=='component':
        # The binary was compiled by the same pinned g++/float flags in the checks stage.
        assert json.loads((AREA/'pinned-standalone.json').read_text())['accepted']
        assert not (AREA/'component-result.json').exists(), 'component series must not be repeated after results exist'
        standalone=json.loads((AREA/'pinned-standalone.json').read_text())
        assert standalone['runtime']['platform']=='linux'
        plan=json.loads((AREA/'plan-snapshot.json').read_text())
        exp=next(x for x in plan['experiments'] if x['slug']==SLUG)
        results=[]
        dump(AREA/'component-result.json',{'executive_summary':'One fixed component series, started; no reruns after inspection.','complete':False,'results':results})
        # Read config files exported inside the pinned runtime by the checks stage.
        # Never remap these scenarios using the host's numpy/libm environment.
        for record in standalone['reports'][0]['simulations']:
            name=record['case']
            if name.split('/')[0] not in exp['units']: continue
            config=ROOT/record['component_config']
            assert hashlib.sha256(config.read_bytes()).hexdigest()==record['config_sha256']
            result=json.loads(output(pinned([rel+'/evidence/build/component','--bench','/work/'+record['component_config']])))
            assert len(result['pairs'])==5
            a=statistics.median(x['baseline_seconds'] for x in result['pairs'])
            b=statistics.median(x['candidate_seconds'] for x in result['pairs'])
            result.update(case=name,scenario_sha256=record['scenario_sha256'],config_sha256=record['config_sha256'],accepted=True,rankable=False,
                          excluded_from_full_run_medians=True,baseline_median_seconds=a,
                          candidate_median_seconds=b,speedup=a/b,time_reduction_pct=100*(1-b/a),
                          boundary='Logging/capture plus actual finalization on identical replay of real captured logs; initial simulation, chronological replay preparation, baseline agent scaffold initialization and equality checks excluded. Candidate includes every online sort/flush and column append. Baseline extract-only samples are secondary.',
                          source_hashes=before,implementation_commit=commit)
            results.append(result)
            dump(AREA/'component-result.json',{'executive_summary':'Component diagnostics use only the four assigned timing scenarios and remain excluded from full-run medians.','results':results,'complete':len(results)==len(exp['units'])})
    else:
        image=json.loads((AREA/'image.json').read_text())
        assert image['implementation_commit']==commit and image['source_hashes']==before
        control=json.loads((evidence/'pinned-controls/summary.json').read_text())
        assert control['accepted'] and control['complete']
        run([sys.executable,CAMPAIGN/'run_focused.py','--slug',SLUG,'--candidate-image',image['candidate_image'],
             '--candidate-commit',commit,'--out',evidence/'timing'])
    assert sources()==before, 'sources changed during stage'


if __name__=='__main__': main()
