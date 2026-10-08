"""Executive summary: bind the experiment baseline to frozen source, pinned runtime and a real public correctness run."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

AREA = Path(__file__).resolve().parent
REPO = Path('/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public')
PYTHON = REPO / '.venv/bin/python'

def output(argv):
    return subprocess.check_output(argv, text=True).strip()

def main():
    plan = json.loads((AREA / 'plan.json').read_text())
    docker = ['docker', '--context', 'colima-agenthon']
    runtime = output(docker + ['image', 'inspect', '--format', '{{.Id}}', plan['baseline_tag']])
    builder = output(docker + ['image', 'inspect', '--format', '{{.Id}}', plan['baseline_builder_tag']])
    probe = '''import sys,json,hashlib,pathlib,importlib.metadata
from abides_fork import _t3engine
paths=list(pathlib.Path('/opt/abides_fork').glob('*.py'))+[pathlib.Path(_t3engine.__file__)]
print(json.dumps({'python':sys.version,'packages':{x:importlib.metadata.version(x) for x in ['numpy','pandas','pyarrow','scipy']},'dispatch':_t3engine.numpy_log_dispatch(),'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}))'''
    actual = json.loads(output(docker + ['run', '--rm', '--platform', 'linux/amd64', '--cpus', '4', '--memory', '16g', '--memory-swap', '16g', '--network', 'none', '--entrypoint', 'python', runtime, '-c', probe]))
    source_probe = '''import pathlib,hashlib,json
paths=[p for p in pathlib.Path('/src/native').rglob('*') if p.is_file()]+[pathlib.Path('/src/native_build.py')]
print(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))'''
    installed_sources = json.loads(output(docker + ['run', '--rm', '--platform', 'linux/amd64', '--cpus', '4', '--memory', '16g', '--memory-swap', '16g', '--network', 'none', '--entrypoint', 'python', builder, '-c', source_probe]))
    bound = {}
    for p in (REPO / 'baselines/native').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            key = '/src/native/' + str(p.relative_to(REPO / 'baselines/native'))
            rel = str(p.relative_to(REPO))
            frozen = subprocess.check_output(['git', 'show', plan['base_commit'] + ':' + rel], cwd=REPO)
            digest = hashlib.sha256(frozen).hexdigest()
            assert installed_sources[key] == digest, rel
            bound[rel] = digest
    build_script = subprocess.check_output(['git', 'show', plan['base_commit'] + ':baselines/build_native.py'], cwd=REPO)
    assert installed_sources['/src/native_build.py'] == hashlib.sha256(build_script).hexdigest()
    for p in (REPO / 'baselines/abides_fork').glob('*.py'):
        rel = str(p.relative_to(REPO))
        frozen = subprocess.check_output(['git', 'show', plan['base_commit'] + ':' + rel], cwd=REPO)
        assert actual['files']['/opt/abides_fork/' + p.name] == hashlib.sha256(frozen).hexdigest(), rel
    assert actual['packages'] == {'numpy':'1.26.4','pandas':'1.5.3','pyarrow':'15.0.2','scipy':'1.17.1'}
    plan['baseline_image'] = runtime
    plan['baseline_builder_image'] = builder
    (AREA / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    (Path(plan['report_directory']) / 'plan.json').write_text((AREA / 'plan.json').read_text())
    sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location('base_differential', REPO / 'scripts/run_differential_experiment.py')
    d = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = d
    spec.loader.exec_module(d)
    from throughput.run_unit import _stage_input
    unit = REPO / 'units/t3-s001-price-time-priority'
    assert not any(d.corpus_check(unit).values())
    evidence = AREA / 'baseline-evidence'
    evidence.mkdir(exist_ok=False)
    staging = evidence / 'inputs' / unit.name
    staging.mkdir(parents=True)
    _stage_input(unit, staging, False)
    args = argparse.Namespace(trace_mode='buffered', platform='linux/amd64', timeout=600,
                              baseline_batch_args_json=[], candidate_batch_args_json=[])
    record = d.run_once(args, unit, staging, runtime, 'baseline', 'correctness', 0, evidence, docker)
    assert record['accepted'], record
    ev = json.loads((evidence / 'runs' / unit.name / 'correctness-00/baseline/retained/events.json').read_text())
    assert ev['engine'] == 'native'
    audit = dict(executive_summary='The current combined native baseline is source-bound and passes the selected canonical public correctness check.',
                 accepted=True, rankable=False, base_commit=plan['base_commit'], runtime_image=runtime,
                 builder_image=builder, runtime=actual, frozen_native_source_hashes=bound, correctness_record=record)
    (AREA / 'baseline-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    (Path(plan['report_directory']) / 'baseline-audit.json').write_text((AREA / 'baseline-audit.json').read_text())
    (AREA / 'BASELINE_READY.json').write_text(json.dumps(dict(accepted=True, runtime_image=runtime, builder_image=builder, base_commit=plan['base_commit']), indent=2)+'\n')
    print(json.dumps({'baseline_ready':True,'runtime_image':runtime,'builder_image':builder}))

if __name__ == '__main__':
    main()
