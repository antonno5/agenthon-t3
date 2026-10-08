"""Executive summary: audit fresh combined measurements and publish every scenario result."""
import hashlib,json,math,shutil,statistics,subprocess
from pathlib import Path
report=Path(__file__).resolve().parent;root=report.parents[1]
def read(p): return json.loads(p.read_text())
def dump(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()
plan=read(report/'plan.json');build=read(report/'build-record.json')
control=read(report/'evidence/controls/summary.json');result=read(report/'evidence/timing/result.json');summary=read(report/'evidence/timing/summary.json')
assert control['complete'] and control['accepted']
assert result['complete'] and result['accepted'] and summary['complete'] and summary['accepted']
assert result['source_unchanged_during_measurement']
assert result['assigned_units']==plan['experiments'][0]['units']
assert {r['unit'] for r in result['results']}==set(result['assigned_units'])
assert result['summary_sha256']==sha(report/'evidence/timing/summary.json')
assert result['candidate_implementation_commit']==build['candidate_implementation_commit']
assert result['images']['candidate']['digest']==build['candidate_image']
assert result['images']['baseline']['digest']==plan['baseline_image']
assert result['source_hashes']==build['native_build_audit']['native_source_sha256']
assert len(summary['runs'])==84 and len(control['runs'])==22
journal_hashes=0;intervals=[];wall_anomalies=[]
for kind,records in [('controls',control['runs']),('timing',summary['runs'])]:
    previous=None
    for r in records:
        assert r['accepted'] and all(x=='native' for x in r['actual_native'].values())
        assert r['state']['Status']=='exited' and not r['state']['Running']
        assert r['state']['ExitCode']==0 and not r['state']['OOMKilled']
        interval=r['host_monotonic_interval_ns']; assert interval['start']<interval['finish']
        if previous:
            assert previous['host_monotonic_interval_ns']['finish']<=interval['start']
            if previous['state']['FinishedAt']>r['state']['StartedAt']:
                wall_anomalies.append({'series':kind,'previous':{k:previous[k] for k in ['unit','side','kind','index','state']},'next':{k:r[k] for k in ['unit','side','kind','index','state']},'cause':'unknown; host monotonic launch intervals confirm sequential execution'})
        previous=r;intervals.append(interval)
        kept=report/'evidence'/kind/'runs'/r['unit']/f"{r['kind']}-{r['index']:02d}"/r['side']/'retained'
        for events in kept.rglob('events.json'):
            ev=read(events);assert ev['engine']=='native'
            for file,key in [('trace.parquet','trace_sha256'),('message_trace.parquet','message_trace_sha256')]:
                assert sha(events.with_name(file))==ev[key];journal_hashes+=1
for cmp in control['comparisons']:
    assert cmp['byte_equal'] and cmp['schema_equal'] and cmp['semantic_exact_equal']
    for f in cmp['files']: assert sha(Path(f['left']))==f['left_sha256']==f['right_sha256']==sha(Path(f['right']))
cli=[]
for row in result['results']:
    rs={side:sorted([r for r in summary['runs'] if r['unit']==row['unit'] and r['side']==side and r['kind']=='timing'],key=lambda r:r['index']) for side in ['baseline','candidate']}
    samples={side:[r['container_sec'] for r in rows] for side,rows in rs.items()}
    assert all(len(v)==5 for v in samples.values()) and samples==row['container_seconds_samples']
    med={k:statistics.median(v) for k,v in samples.items()};assert med==row['median_container_seconds']
    assert abs(100*(1-med['candidate']/med['baseline'])-row['time_reduction_pct'])<1e-9
    cm={k:statistics.median(r['host_launch_sec'] for r in v) for k,v in rs.items()}
    cli.append({'unit':row['unit'],'median_host_launch_seconds':cm,'time_reduction_pct':100*(1-cm['candidate']/cm['baseline'])})
ratio=math.exp(statistics.mean(math.log(r['median_container_seconds']['candidate']/r['median_container_seconds']['baseline']) for r in result['results']))
result.update(adopted=True,host_launch_secondary=cli,aggregate={'method':'equal-weight geometric mean of the seven candidate/baseline median ratios; applies only to this selected set','time_reduction_pct':100*(1-ratio),'speedup_factor':1/ratio},clock_anomalies=wall_anomalies)
dump(report/'result.json',result)
audit={'executive_summary':'All fresh runs passed exact journals and native provenance. Percentages and digests were independently rechecked; monotonic host intervals prove serial launches.','accepted':True,'complete':True,'previous_develop_commit':plan['base_commit'],'implementation_commit':build['candidate_implementation_commit'],'correctness_runs':22,'timing_runs':70,'warmup_runs':14,'journal_digests_independently_rechecked':journal_hashes,'host_monotonic_intervals_checked':len(intervals),'all_host_launches_serial':True,'docker_wall_clock_anomalies':wall_anomalies,'controls_summary_sha256':sha(report/'evidence/controls/summary.json'),'timing_summary_sha256':result['summary_sha256'],'native_source_and_image_build_hashes_match':True,'working_sources_unchanged':not bool(subprocess.check_output(['git','diff',build['candidate_implementation_commit'],'--','baselines'],cwd=root))};assert audit['working_sources_unchanged'];dump(report/'validation.json',audit)
text=['Ledger streaming and the arena order book are integrated in develop. This report compares fresh paired runs with the previous develop revision; all selected scenarios preserve both journals exactly. Measurements are local and non-rankable.','',f"Предыдущий develop: `{plan['base_commit']}`. Реализация: `{build['candidate_implementation_commit']}`.",'','Положительный процент — сокращение полного времени контейнера; отрицательный — замедление. Формула: `100 × (1 − median(candidate) / median(baseline))`. Для каждого сценария выполнены один прогрев каждой стороны и пять AB/BA-пар. Прогревы исключены, все samples и выбросы сохранены.','', '| Сценарий | До, мс | После, мс | Ускорение / замедление | Быстрее в парах |','|---|---:|---:|---:|---:|']
for r in result['results']:
    m=r['median_container_seconds'];text.append(f"| `{r['unit']}` | {1000*m['baseline']:.3f} | {1000*m['candidate']:.3f} | **{r['time_reduction_pct']:+.2f}%** | {r['candidate_faster_pairs']}/5 |")
text+=['',f"Геометрическое среднее отношений медиан на этих семи сценариях: **{100*(1-ratio):+.2f}%**, коэффициент ускорения **{1/ratio:.3f}×**. Это сводка выбранного набора, без переноса на остальные testcase.",'','Проверки: 22 correctness-запуска на 11 units, 70 timing-запусков и 14 прогревов; оба журнала совпали побайтно, по схеме и порядку значений. Shared developer gates прошли, native подтверждён в каждом рынке. ASan/UBSan прошли 80 000 мутаций стакана и проверки pipeline; pinned Arrow 15 прошёл синтетические границы блоков/row groups и binding-проверки пустого результата и ошибок.','',f"Независимо перепроверено {journal_hashes} journal digests. Host monotonic timestamps подтверждают последовательность всех {len(intervals)} запусков. Аномалии Docker wall-clock timestamps: {len(wall_anomalies)}; детали сохранены в validation.json.",'','Среда: Mac ARM64, Colima linux/amd64 с эмуляцией, 4 CPU, 16 GiB memory, 16 GiB memory+swap, network none; `rankable:false`. RNG, float flags, mapping и зависимости сохранены. Baseline image ранее построен из a7fb6c3: исходники baselines у предыдущего develop 18af3d5 идентичны, разница только в отчётах.','', 'Pipeline переносит запись ledger внутрь симуляции: core phase включает backpressure, Parquet phase отражает оставшуюся запись после simulation. Поэтому основные выводы сделаны по полному Docker времени.','', 'Все samples, попарные результаты, фазы и пути evidence сохранены в [result.json](result.json). Проверки: [validation.json](validation.json), [build-record.json](build-record.json), [source-audit.json](source-audit.json). Raw outputs, журналы и логи остаются под evidence/ и исключены из Git.','', 'Измеряемые сценарии и дополнительные correctness-only units зафиксированы до timing в [plan.json](plan.json). Полный public corpus в этом прогоне не запускался.','', '| Сценарий | Host Docker CLI clock, вторичная метрика |','|---|---:|']
for r in cli: text.append(f"| `{r['unit']}` | {r['time_reduction_pct']:+.2f}% |")
(report/'README.md').write_text('\n'.join(text)+'\n')
print(json.dumps({'accepted':True,'aggregate':result['aggregate'],'results':[{k:r[k] for k in ['unit','time_reduction_pct','candidate_faster_pairs']} for r in result['results']],'clock_anomalies':len(wall_anomalies)},ensure_ascii=False))
