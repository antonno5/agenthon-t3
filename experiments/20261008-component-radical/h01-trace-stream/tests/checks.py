"""Executive summary: build and compare isolated trace logic and both complete native journals.

No Docker or timing is launched here. Only the frozen H1 scenarios may be simulated.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import types

AREA = Path(__file__).resolve().parents[1]
ROOT = AREA.parents[2]
BASE = '33027d74553e9a318d66557fe0f7b7bed84cfa38'
KEYS = ('seed start_time mkt_open mkt_close stop_time oracle_close default_delay r_bar '
        'kappa fund_vol megashock_lambda_a megashock_mean megashock_var pipeline_delay '
        'computation_delay stp lat_model lat_mu lat_sigma lat_min lat_max lat_alpha lat_mean').split()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def command(argv, **kw):
    p = subprocess.run([str(x) for x in argv], text=True, capture_output=True, **kw)
    if p.returncode:
        raise RuntimeError(f'{argv}: exit {p.returncode}\n{p.stdout}\n{p.stderr}')
    return p.stdout.strip()


def prepare(build):
    original = subprocess.check_output(['git', 'show', BASE + ':baselines/native/engine.cpp'], cwd=ROOT)
    (build / 'original_engine.cpp').write_bytes(original)
    # Change access control only, allowing the test to populate original logs and call
    # the actual original Sim::extract; its executable statements remain untouched.
    visible = original.replace(b' private:', b' public:')
    (build / 'base_engine.cpp').write_bytes(visible)
    (build / 'trace_stream_visible.hpp').write_bytes((ROOT/'baselines/native/trace_stream.hpp').read_bytes().replace(b' private:', b' public:'))
    sources = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT/'baselines/native').rglob('*')) if p.is_file()}
    (AREA/'source-manifest.json').write_text(json.dumps({
        'executive_summary':'Frozen base finalization and current native sources for reproducible isolated checks.',
        'base_commit':BASE, 'original_engine_sha256':hashlib.sha256(original).hexdigest(),
        'visibility_only_engine_sha256':hashlib.sha256(visible).hexdigest(),
        'source_hashes':sources}, indent=2)+'\n')


def compile_tests(build, compiler, sanitized):
    flags = ['-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-fno-strict-aliasing','-Wall','-Wextra',
             '-Wno-unused-function','-I'+str(ROOT/'baselines/native'), '-I'+str(build)]
    if sanitized:
        flags += ['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g']
    suffix = '-san' if sanitized else ''
    command([compiler,*flags, AREA/'tests/component.cpp','-o',build/('component'+suffix)])
    for side, source in [('base',build/'original_engine.cpp'),('candidate',ROOT/'baselines/native/engine.cpp')]:
        command([compiler,*flags,AREA/'tests/sim_driver.cpp',source,'-o',build/(side+suffix)])


def cases(plan, corpus):
    sys.path.insert(0,str(ROOT/'baselines'))
    from abides_fork import native
    # Standalone drivers do not link the Python extension. This supplies only the
    # mapper's normal numpy-log fallback, identically for base and candidate.
    native._t3engine = types.SimpleNamespace(numpy_log=lambda x: None)
    exp=next(x for x in plan['experiments'] if x['slug']=='h01-trace-stream')
    for name in exp['units']+exp['correctness_only_units']:
        unit=corpus/name
        paths = [unit/'scenario.json']
        if (unit/'batch.json').exists():
            batch=json.loads((unit/'batch.json').read_text())
            paths=[unit/x['scenario_file'] for x in batch['subs']]
        for path in paths:
            scenario=json.loads(path.read_text()); cfg=native.build_native_config(scenario)
            if cfg is None:
                raise RuntimeError('native mapping rejected '+str(path))
            yield name+'/'+path.stem, cfg, sha(path)


def config_text(cfg):
    values=[cfg[k] for k in KEYS]+[len(cfg['jumps'])]
    for jump in cfg['jumps']: values.extend(jump)
    values.append(len(cfg['agents']))
    for agent in cfg['agents']: values.extend(agent)
    return '\n'.join(map(str,values))+'\n'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--plan',required=True,type=Path)
    ap.add_argument('--corpus',type=Path)
    ap.add_argument('--compiler',default='c++')
    ap.add_argument('--no-prepare',action='store_true')
    ap.add_argument('--sanitizers',action='store_true')
    ap.add_argument('--output',type=Path,default=AREA/'host-checks.json')
    args=ap.parse_args()
    plan=json.loads(args.plan.read_text()); assert plan['base_commit']==BASE
    corpus=args.corpus or Path(plan['corpus'])
    timing_units=next(x for x in plan['experiments'] if x['slug']=='h01-trace-stream')['units']
    build=AREA/'evidence/build'; build.mkdir(parents=True,exist_ok=True)
    if not args.no_prepare: prepare(build)
    reports=[]
    for sanitized in ([False,True] if args.sanitizers else [False]):
        compile_tests(build,args.compiler,sanitized)
        suffix='-san' if sanitized else ''
        env=dict(os.environ,ASAN_OPTIONS=('detect_leaks=0:halt_on_error=1' if sys.platform=='darwin' else 'detect_leaks=1:halt_on_error=1'),UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        unit=json.loads(command([build/('component'+suffix)],env=env))
        runs=[]
        for name,cfg,digest in cases(plan,corpus):
            text=config_text(cfg)
            (build/'config.txt').write_text(text)
            component_config=None
            if name.split('/')[0] in timing_units:
                component_config=build/('component-'+name.split('/')[0]+'.txt')
                component_config.write_text(text)
            outputs=[]; counts=[]
            for side in ('base','candidate'):
                output=build/(side+'.bin')
                counts.append(json.loads(command([build/(side+suffix),build/'config.txt',output],env=env)))
                outputs.append(sha(output))
            assert outputs[0]==outputs[1] and counts[0]==counts[1], (name,outputs,counts)
            runs.append({'case':name,'scenario_sha256':digest,
                         'component_config':str(component_config.relative_to(ROOT)) if component_config else None,
                         'config_sha256':hashlib.sha256(text.encode()).hexdigest(),**counts[0],
                         'base_column_bytes_sha256':outputs[0],'candidate_column_bytes_sha256':outputs[1]})
        reports.append({'sanitizers':sanitized,'leak_detection':sys.platform!='darwin','isolated_component':unit,'simulations':runs,'accepted':True})
    for name in ('base.bin','candidate.bin'): (build/name).unlink(missing_ok=True)
    result={'executive_summary':'All focused lifecycle tests and the assigned full native simulations match the original source exactly in all 7 trace and 12 message columns.',
            'accepted':True,'base_commit':BASE,'runtime':{'python':platform.python_version(),'platform':sys.platform,'machine':platform.machine()},'compiler':command([args.compiler,'--version']),
            'plan_sha256':sha(args.plan),'reports':reports,
            'limits':['Standalone host columns do not establish pinned Parquet byte equality or shared scoring gates.',
                      'Only frozen H1 units were simulated; no performance loops were run.']}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'accepted':True,'output':str(args.output),'configurations_per_mode':len(runs),'modes':len(reports)}))


if __name__=='__main__': main()
