"""Executive summary: validate and time the three selected changes together in Docker.

Use the campaign docker_slot.py to hold exclusive access for this entire script.
The existing differential checker and scorer are imported unchanged. Seven
relevant public units are predeclared; no full-suite run or selective rerun occurs.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import statistics
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AREA = Path('/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses')
BASE_COMMIT = '94e66380b9152d76a193ee84c70a3660c6098845'
BASE_IMAGE = 'sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89'
BASE_TAG = 'track3-native:20261008'
UNITS = ['t3-mr-deep-book-state-size', 't3-mp05-cancel-churn-newest',
         't3-s012-partial-fill-cancel-race', 't3-cancelmodify-lifecycle',
         't3-s001-price-time-priority', 't3-mp02-stp-oldest-baseline',
         't3-gbatch-hetero-mix']
DOCKER = ['docker', '--context', 'colima-agenthon']
CAPS = ['--platform', 'linux/amd64', '--network=none', '--cpus=4', '--memory=16g', '--memory-swap=16g']
OUT = ROOT / 'out/native-adoption-20261008/docker'


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'baselines/native').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def logged(name, command):
    print('START', name, flush=True)
    with (OUT/(name+'.log')).open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    dump(OUT/(name+'.status.json'), {'command':command, 'exit_code':result.returncode})
    if result.returncode:
        raise RuntimeError(f'{name}: exit {result.returncode}; see {OUT/(name+".log")}')
    print('PASS', name, flush=True)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not subprocess.check_output(['git','diff','HEAD','--','baselines'],cwd=ROOT)
    initial = hashes()
    inspect = lambda tag: subprocess.check_output(DOCKER+['image','inspect','--format','{{.Id}}',tag],text=True).strip()
    assert inspect(BASE_TAG) == BASE_IMAGE
    build = DOCKER+['build','--platform','linux/amd64','--build-arg','BASE_IMAGE='+BASE_TAG,'-f',str(AREA/'Dockerfile')]
    logged('build-builder',build+['--target','native_builder','-t','track3-native-adoption-20261008:builder',str(ROOT)])
    builder = inspect('track3-native-adoption-20261008:builder')
    logged('build-candidate',build+['-t','track3-native-adoption-20261008:candidate',str(ROOT)])
    candidate = inspect('track3-native-adoption-20261008:candidate')
    assert inspect(BASE_TAG) == BASE_IMAGE
    dump(OUT/'images.json',{'baseline':BASE_IMAGE,'builder':builder,'candidate':candidate,'source_commit':commit})
    pinned = OUT/'pinned';pinned.mkdir()
    compile_script = r'''set -eu
g++ -std=c++17 -O2 -fno-fast-math -ffp-contract=off -Wall -Wextra -Dt3=t3_baseline -c /candidate/out/native-adoption-20261008/host/baseline/engine.cpp -o /checks/baseline.o
g++ -std=c++17 -O2 -fno-fast-math -ffp-contract=off -Wall -Wextra -I/candidate/baselines/native -I/candidate/out/native-adoption-20261008/host /candidate/experiments/20261008-native-hypotheses/adoption/host_checks.cpp /checks/baseline.o -o /checks/integration
/checks/integration
g++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -I/candidate/baselines/native /candidate/baselines/native/tests/agent_orders_test.cpp -o /checks/registry-sanitized
/checks/registry-sanitized
python -c 'import platform,pyarrow; assert platform.python_version()=="3.11.17"; assert pyarrow.__version__=="15.0.2"; print("PASS: pinned runtime",platform.python_version(),pyarrow.__version__)'
'''
    logged('pinned-correctness',DOCKER+['run','--rm',*CAPS,'--entrypoint','bash','-v',str(ROOT)+':/candidate:ro','-v',str(pinned)+':/checks',builder,'-c',compile_script])
    sys.path.insert(0,str(ROOT))
    spec=importlib.util.spec_from_file_location('adoption_differential',ROOT/'scripts/run_differential_experiment.py')
    d=importlib.util.module_from_spec(spec);sys.modules[spec.name]=d;spec.loader.exec_module(d)
    original_container,original_docker=d.container_run,d.docker_output
    original_once,original_exact=d.run_once,d.exact_tree
    def strict_container(command,docker,name,timeout):
        pos=command.index('run')+1;command[pos:pos]=['-e','T3_ENGINE=native','-e','T3_REQUIRE_NATIVE=1']
        for flag in ['--network=none','--cpus=4','--memory=16g','--memory-swap=16g']:assert flag in command
        return original_container(command,docker,name,timeout)
    def strict_docker(docker,argv):
        if argv[:1]==['run'] and not any(x.startswith('--memory-swap') for x in argv):argv=['run','--memory-swap=16g',*argv[1:]]
        return original_docker(docker,argv)
    def strict_exact(unit,left,right):
        check=original_exact(unit,left,right)
        assert d.exact_ok(check) and check['byte_equal'],check
        return check
    def strict_once(args,unit,inputs,image,side,kind,index,directory,docker):
        record=original_once(args,unit,inputs,image,side,kind,index,directory,docker)
        assert record['accepted'],record.get('error',record.get('check'))
        kept=directory/'runs'/unit.name/f'{kind}-{index:02d}'/side/'retained'
        native,phases={},{}
        for _,sub in d.trace_layout(unit):
            events=json.loads((kept/sub/'events.json').read_text());profile=json.loads((kept/sub/'profile.json').read_text())
            assert events['engine']==profile['engine']=='native'
            for file,key in [('trace.parquet','trace_sha256'),('message_trace.parquet','message_trace_sha256')]:assert events[key]==d.sha(kept/sub/file)
            native[sub or 'single']='native';phases[sub or 'single']=profile['phases']
        record.update(actual_native=native,phase_seconds_by_market=phases)
        d.dump(kept.parent/'record.json',record)
        return record
    d.container_run,d.docker_output=strict_container,strict_docker
    d.run_once,d.exact_tree=strict_once,strict_exact
    for image in [BASE_IMAGE,candidate]:
        meta=d.image_metadata(DOCKER,image,'linux/amd64')
        assert meta['versions']['python']=='3.11.17' and meta['versions']['packages']['pyarrow']=='15.0.2'
        logged('native-probe-'+('baseline' if image==BASE_IMAGE else 'candidate'),DOCKER+['run','--rm',*CAPS,'-e','T3_ENGINE=native','-e','T3_REQUIRE_NATIVE=1',image,'python','-c','import abides_fork._t3engine; print("PASS: native import")'])
    assert initial==hashes()
    timing=OUT/'timing'
    print('START seven-unit warmup + five paired repeats',flush=True)
    rc=d.main(['run','--baseline-image',BASE_IMAGE,'--candidate-image',candidate,
               '--baseline-commit',BASE_COMMIT,'--candidate-commit',commit,'--units-dir',str(ROOT/'units'),
               '--units',*UNITS,'--repeats','5','--trace-mode','buffered','--platform','linux/amd64',
               '--no-profile','--timeout','600','--out',str(timing)])
    summary=json.loads((timing/'summary.json').read_text())
    assert rc==0 and summary['complete'] and summary['accepted'] and initial==hashes()
    rows=[]
    for unit in UNITS:
        runs={side:[r for r in summary['runs'] if r['unit']==unit and r['side']==side and r['kind']=='timing'] for side in ['baseline','candidate']}
        samples={side:[r['container_sec'] for r in values] for side,values in runs.items()}
        assert all(len(values)==5 for values in samples.values())
        median={side:statistics.median(values) for side,values in samples.items()}
        phases={side:{key:[sum(p.get(key,0) for p in r['phase_seconds_by_market'].values()) for r in values] for key in ['simulation_and_trace_finalize','parquet_write','hashing']} for side,values in runs.items()}
        rows.append({'unit':unit,'container_seconds_samples':samples,'median_container_seconds':median,
                     'time_reduction_pct':100*(1-median['candidate']/median['baseline']),
                     'candidate_faster_pairs':sum(c<b for b,c in zip(samples['baseline'],samples['candidate'])),
                     'secondary_market_phase_sum_samples':phases})
    report={'executive_summary':'The three selected optimizations are integrated and validated together. Every scheduled native run passes shared developer gates and both journals match exactly. Percentages measure median complete-container time against fresh production controls.',
            'accepted':True,'rankable':False,'selected_hypotheses':['h01-trace-finalize','h02-time-groups','h04-agent-orders'],
            'baseline_commit':BASE_COMMIT,'candidate_source_commit':commit,'images':summary['images'],
            'assigned_units':UNITS,'source_hashes':initial,'source_unchanged_during_measurement':initial==hashes(),
            'counts':{'accepted_runs':len(summary['runs']),'timed_samples':sum(r['kind']=='timing' for r in summary['runs']),'warmups':sum(r['kind']=='warmup' for r in summary['runs'])},
            'policy':{'warmups_per_side':1,'timed_pairs':5,'pair_order':'AB BA AB BA AB','primary_clock':'Docker State FinishedAt - StartedAt','context':'colima-agenthon','platform':'linux/amd64','cpus':4,'memory':'16g','memory_swap':'16g','network':'none','outliers_retained':True,'full_suite':False},
            'results':rows,'raw_evidence_directory':str(OUT),'summary_sha256':d.sha(timing/'summary.json'),
            'runner_sha256':d.sha(Path(__file__)),'checker_sha256':d.sha(ROOT/'scripts/run_differential_experiment.py'),
            'limitations':['Local ARM64 Mac with emulated amd64 containers; not official timing hardware.','Core includes trace finalization and is secondary.','Batch phase sums are not batch critical-path time.','Separate hypothesis percentages cannot be added.']}
    dump(HERE/'result.json',report)
    print(json.dumps({'accepted':True,'results':[{'unit':r['unit'],'time_reduction_pct':r['time_reduction_pct']} for r in rows]}),flush=True)


if __name__=='__main__':main()
