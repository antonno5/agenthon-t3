"""Executive summary: independently audit isolated component experiment results."""
from pathlib import Path
import hashlib,json,statistics,subprocess,math
REPO=Path('/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public')
AREA=REPO/'experiments/20261008-component-radical'
PLAN=json.loads((AREA/'plan.json').read_text())
report={'executive_summary':'Independent arithmetic, source, output-digest and sequential-clock audit of three isolated native experiments.','accepted':False,'rankable':False,'hypotheses':[]}
all_intervals=[]
for exp in PLAN['experiments']:
    p=AREA/exp['slug']/'primary-result.json'
    result=json.loads(p.read_text())
    assert result['complete'] and result['accepted'],exp['slug']
    assert result['base_commit']==PLAN['base_commit']
    assert set(result['assigned_units'])==set(exp['units'])
    assert result['source_unchanged_during_measurement']
    assert result['counts']['timed_samples']==40
    assert result['counts']['warmups']==8
    evidence=Path(result['evidence_directory'])
    summary=json.loads((evidence/'summary.json').read_text())
    assert hashlib.sha256((evidence/'summary.json').read_bytes()).hexdigest()==result['summary_sha256']
    digests=0
    for run in summary['runs']:
        assert run['accepted'] and set(run['actual_native'].values())=={'native'}
        assert run['image_digest'].startswith('sha256:')
        assert run['image_digest']==result['images'][run['side']]['digest']
        if run['side']=='baseline': assert run['image_digest']==PLAN['baseline_image']
        assert run['unit'] in exp['units']
        interval=run['host_monotonic_interval_ns']
        assert interval['finish']>interval['start']
        all_intervals.append((interval['start'],interval['finish'],exp['slug'],run['unit'],run['kind'],run['side']))
        for observed in run['post_validation_storage_dedup']:
            f=evidence/observed['path']
            assert f.stat().st_size==observed['bytes']
            assert hashlib.sha256(f.read_bytes()).hexdigest()==observed['sha256_before_dedup']
            digests+=1
    assert len({r['image_digest'] for r in summary['runs'] if r['side']=='candidate'})==1
    for unit in exp['units']:
        timed=[r for r in summary['runs'] if r['unit']==unit and r['kind']=='timing']
        assert len(timed)==10
        assert [[r['side'] for r in timed if r['index']==i] for i in range(5)]==[['baseline','candidate'],['candidate','baseline'],['baseline','candidate'],['candidate','baseline'],['baseline','candidate']]
    candidate_root=Path(exp['worktree'])
    subprocess.run(['git','merge-base','--is-ancestor',result['candidate_implementation_commit'],'HEAD'],cwd=candidate_root,check=True)
    candidate_hashes={str(f.relative_to(candidate_root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((candidate_root/'baselines/native').rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
    assert candidate_hashes==result['source_hashes'],'candidate changed after timing'
    controls_paths=[f for f in (AREA/exp['slug']).rglob('summary.json') if 'controls' in str(f.parent.name)]
    assert len(controls_paths)==1,(exp['slug'],controls_paths)
    controls=json.loads(controls_paths[0].read_text())
    assigned_controls=set(exp['units']+exp['correctness_only_units'])
    assert controls['complete'] and controls['accepted']
    assert len(controls['runs'])==2*len(assigned_controls)
    assert {r['unit'] for r in controls['runs']}==assigned_controls
    assert {c['unit'] for c in controls['comparisons']}==assigned_controls
    for comparison in controls['comparisons']:
        assert all(comparison.get(k) is True for k in ('byte_equal','schema_equal','semantic_exact_equal'))
        for f in comparison['files']:
            assert all(f.get(k) is True for k in ('byte_equal','schema_equal','semantic_exact_equal'))
            assert f['left_sha256']==f['right_sha256']
    for run in controls['runs']:
        assert run['accepted'] and set(run['actual_native'].values())=={'native'}
        for observed in run['post_validation_storage_dedup']:
            f=controls_paths[0].parent/observed['path']
            assert f.stat().st_size==observed['bytes']
            assert hashlib.sha256(f.read_bytes()).hexdigest()==observed['sha256_before_dedup']
            digests+=1
    rows=[]
    for row in result['results']:
        samples=row['container_seconds_samples']
        assert len(samples['baseline'])==len(samples['candidate'])==5
        mb,mc=map(statistics.median,(samples['baseline'],samples['candidate']))
        reduction=100*(1-mc/mb)
        assert math.isclose(reduction,row['time_reduction_pct'],rel_tol=1e-12,abs_tol=1e-12)
        assert row['candidate_faster_pairs']==sum(c<b for b,c in zip(samples['baseline'],samples['candidate']))
        rows.append({'unit':row['unit'],'baseline_ms':1000*mb,'candidate_ms':1000*mc,'time_reduction_pct':reduction,'speedup_factor':mb/mc,'candidate_faster_pairs':row['candidate_faster_pairs']})
    component_rows=[]
    if exp['slug']=='h01-trace-stream':
        component=json.loads((AREA/exp['slug']/'component-result.json').read_text())
        assert component['complete']
        assert {r['case'].split('/')[0] for r in component['results']}==set(exp['units'])
        for r in component['results']:
            assert r['accepted'] and len(r['pairs'])==5
            mb=statistics.median(p['baseline_seconds'] for p in r['pairs'])
            mc=statistics.median(p['candidate_seconds'] for p in r['pairs'])
            reduction=100*(1-mc/mb)
            assert math.isclose(reduction,r['time_reduction_pct'],abs_tol=1e-10)
            component_rows.append({'unit':r['case'].split('/')[0],'boundary':r['boundary'],'time_reduction_pct':reduction,'speedup_factor':mb/mc})
    elif exp['slug']=='h03-protocol-fusion':
        component=json.loads((AREA/exp['slug']/'component-pinned.json').read_text())
        assert component['complete']
        assert {r['unit'] for r in component['records']}==set(exp['units'])
        for r in component['records']:
            assert len(r['pairs'])==5
            reduction=statistics.median(100*(1-p['candidate']['engine_seconds']/p['base']['engine_seconds']) for p in r['pairs'])
            assert math.isclose(reduction,r['median_time_reduction_percent'],abs_tol=1e-10)
            component_rows.append({'unit':r['unit'],'boundary':component['timer_boundary'],'time_reduction_pct':reduction,'speedup_factor':r['median_speedup'],'aggregation':'Median paired time reduction; primary rows use ratio of medians'})
    else:
        paths=list((AREA/exp['slug']).glob('evidence/diagnostics/run/diagnostics.json'))
        assert len(paths)==1
        component=json.loads(paths[0].read_text())
        assert component['complete']
        assert {r['unit'] for r in component['medians']}==set(exp['units'])
        for r in component['medians']:
            samples=[s['result'] for s in component['samples'] if s['unit']==r['unit'] and s['mode']==r['mode'] and s['kind']=='pair']
            assert len(samples)==10
            mb,mc=r['seconds']['baseline'],r['seconds']['candidate']
            reduction=100*(1-mc/mb)
            assert math.isclose(reduction,r['time_reduction_pct'],abs_tol=1e-10)
            if r['clock'].endswith('_write_plus_close_seconds'):
                journal=r['clock'].split('_write_plus_close_seconds')[0]
                measure=lambda s:s['result'][journal]['write_seconds']+s['result'][journal]['close_seconds']
            else:
                measure=lambda s:s['result'][r['clock']]
            for side in ('baseline','candidate'):
                actual=statistics.median(measure(s) for s in component['samples'] if s['unit']==r['unit'] and s['mode']==r['mode'] and s['kind']=='pair' and s['side']==side)
                assert math.isclose(actual,r['seconds'][side],abs_tol=1e-12)
            component_rows.append({'unit':r['unit'],'mode':r['mode'],'clock':r['clock'],'time_reduction_pct':reduction,'speedup_factor':mb/mc})
    files=subprocess.check_output(['git','diff','--name-only',PLAN['base_commit'],'HEAD'],cwd=exp['worktree'],text=True).splitlines()
    assert all(f.startswith(('baselines/native/','experiments/20261008-component-radical/')) for f in files),files
    report['hypotheses'].append({'slug':exp['slug'],'rows':rows,'component_rows':component_rows,'independent_digests_checked':digests,'correctness_controls_checked':len(controls['runs']),'changed_paths':files})
all_intervals.sort()
assert all(a[1]<=b[0] for a,b in zip(all_intervals,all_intervals[1:])), 'overlapping launches'
initial=json.loads((AREA/'corpus-preflight.json').read_text())['production_source_hashes']
current={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO/'baselines').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
assert initial==current,'production source changed'
report.update(accepted=True,container_launches_audited=len(all_intervals),production_unchanged=True)
(AREA/'independent-audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'accepted':True,'launches':len(all_intervals),'results':report['hypotheses']},ensure_ascii=False,indent=2))
