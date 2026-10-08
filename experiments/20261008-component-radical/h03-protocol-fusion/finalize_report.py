"""Executive summary: summarize the single frozen H3 campaigns without rerunning simulations."""
import hashlib, json, statistics, shutil
from pathlib import Path
AREA=Path(__file__).resolve().parent

def load(name):return json.loads((AREA/name).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    primary=load('focused-pinned/result.json');component=load('component-pinned.json')
    execution=load('performance-execution.json');controls=load('pinned-controls.json')
    structural=load('pinned-structural.json')
    assert primary['complete'] and primary['accepted'] and component['complete'] and execution['complete'] and controls['accepted']
    assert primary['counts']['timed_samples']==40 and primary['counts']['warmups']==8
    assert len(component['records'])==4 and all(len(x['pairs'])==5 for x in component['records'])
    components={x['unit']:x for x in component['records']}
    structures={x['unit']:x for x in structural['records'] if x['timing']}
    rows=[]
    for p in primary['results']:
        c=components[p['unit']]
        c['median_engine_seconds']={s:statistics.median(x[s]['engine_seconds'] for x in c['pairs']) for s in ['base','candidate']}
        rows.append({'unit':p['unit'],'end_to_end':p,'component':c,'structural':structures[p['unit']]})
    assert len(rows)==4
    target=all(x['component']['median_speedup']>=2 for x in rows)
    any_target=any(x['component']['median_speedup']>=2 for x in rows)
    target_text='was achieved on every timing unit' if target else ('was achieved on some timing units' if any_target else 'was not achieved on any timing unit')
    changes=[x['end_to_end']['time_reduction_pct'] for x in rows]
    core=[x['component']['median_time_reduction_percent'] for x in rows]
    summary=f"Exact pinned correctness passes on all selected units. End-to-end time reductions range from {min(changes):+.2f}% to {max(changes):+.2f}%; event-engine paired median reductions range from {min(core):+.2f}% to {max(core):+.2f}%. The aspirational 2x target {target_text}. This isolated candidate is not adopted."
    if all(x<0 for x in core):
        summary=f'Exact pinned correctness passes. Event-engine execution is {min(-x for x in core):.2f}% to {max(-x for x in core):.2f}% slower on all four timing units. Complete-container reductions range from {min(changes):+.2f}% to {max(changes):+.2f}%. The 2x engine target was not achieved; this candidate is not adopted.'
    shutil.copyfile(AREA/'focused-pinned/summary.json',AREA/'primary-summary.json')
    result={'executive_summary':summary,'slug':'h03-protocol-fusion','complete':True,'accepted':True,'rankable':False,'adopted':False,'source_implementation_commit':'df7adc299079eec4af1911436514dbf5d39b3a97','checked_build_commit':controls['checked_build_commit'],'frozen_timing_commit':execution['frozen_commit'],'candidate_image_id':execution['candidate_image'],'primary':primary,'component_policy':{k:v for k,v in component.items() if k!='records'},'results':rows,'correctness':{'units':10,'control_runs':20,'native_markets':28,'both_journals_bytes_schema_ordered_values':True,'shared_gates':True,'asan_ubsan_inputs':14,'leak_detection':True,'isolated_queue_probe':True,'evidence':'pinned-controls.json'},'aspirational_2x_all_units_achieved':target,'all_samples_retained':True,'no_repeat_after_inspection':True,'evidence_sha256':{name:sha(AREA/name) for name in ['primary-summary.json','focused-pinned/result.json','focused-pinned/summary.json','component-pinned.json','performance-execution.json','pinned-controls.json','pinned-correctness.json','pinned-structural.json']},'limitations':['Local Mac ARM64 host with Linux amd64 emulation; not official timing hardware.','Only the four frozen timing units are speed evidence; six correctness-only units are excluded.','Main-heap bypass covers only a small fraction of deliveries; payload copies and receiver binding remain costs.','Component includes initialization, event execution, mandatory ledger/log appends and Sim destruction; excludes parsing, process startup, trace finalization, Parquet writers and returned-column destruction.','Component paired median reduction and primary ratio-of-medians reduction use different predeclared summaries; every raw pair remains available.','Five pairs per unit cannot establish a general speedup across the corpus.', 'All primary medians are under 1.08 seconds; short container runs and emulation limit interpretation of small end-to-end changes.', 'Component executables are compiled separately from the production CPython extension; the common standalone build/boundary does not isolate per-event cost in the production binary layout.','The first pre-timing sanitizer launch failed due to absent libasan.so.8; test binaries were statically linked, with production sources/runtime untouched.']}
    (AREA/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    old=(AREA/'README.md').read_text()
    end='Reproduction and pending phase 2' if 'Reproduction and pending phase 2' in old else 'Pinned validation, provenance and reproduction'
    implementation=old[old.index('Implementation and ordering proof'):old.index(end)]
    lines=[summary,'','Measured results','----------------','', 'Positive time reduction means a shorter candidate run; negative means a regression. The primary numbers use the ratio of five-sample median complete-container times. The component reduction is the median of the five paired time reductions. Each series has its own one excluded warmup per side and fixed AB/BA sequence; no sample or outlier is discarded.','', '| Unit | Container base / candidate (s) | Container reduction | Engine base / candidate median (s) | Engine paired reduction | Engine paired speedup |','|---|---:|---:|---:|---:|---:|']
    for x in rows:
        p=x['end_to_end'];c=x['component'];pm=p['median_container_seconds'];cm=c['median_engine_seconds']
        lines.append(f"| {x['unit']} | {pm['baseline']:.6f} / {pm['candidate']:.6f} | {p['time_reduction_pct']:+.2f}% | {cm['base']:.6f} / {cm['candidate']:.6f} | {c['median_time_reduction_percent']:+.2f}% | {c['median_speedup']:.3f}x |")
    lines += ['', 'The two series measure different boundaries. Complete-container timing is Docker State FinishedAt minus StartedAt and uses the production extension without added counters. The standalone component timer includes initialization, ordering, handlers, RNG, every ledger-column append, lifecycle/quote logging, and simulation-state destruction. It excludes parsing, process startup, trace extraction/sorting, both Parquet writers and destruction of returned columns. Separate diagnostic binaries increment structural counters. Both component sides use identical flags and boundaries.','', '| Unit | Inline deliveries | Main heap push reduction | Main heap pop reduction | Pool allocation reduction | Typed dispatches |','|---|---:|---:|---:|---:|---:|']
    for x in rows:
        s=x['structural'];counts=s['candidate']
        lines.append(f"| {x['unit']} | {s['fast_delivery_fraction']*100:.2f}% | {s['heap_push_reduction']*100:.2f}% | {s['heap_pop_reduction']*100:.2f}% | {s['pool_allocation_reduction']*100:.2f}% | {counts['typed_dispatches']} |")
    lines += ['', 'The fast path applies to few events on the largest units, and requeue counts remain equal to the base. Receiver binding and inline payload copies also cost work. The experiment therefore does not establish a general radical improvement; the actual four-unit measurements above determine its local outcome.','',implementation.rstrip(),'','Pinned validation, provenance and reproduction','----------------------------------------------','', 'Phase 2a passed both journals’ bytes, schema and ordered values, shared developer gates, and actual native execution on all ten units: twenty complete baseline/candidate launches and twenty-eight market executions. All fourteen mapped C++ inputs and isolated queue probes passed ASan/UBSan and Linux leak detection. The initial missing-libasan failure is retained in `pinned-controls.json`; test-only sanitizer binaries then linked ASan/UBSan statically. Production sources/runtime never changed.','',f"The frozen timing HEAD was `{execution['frozen_commit']}`; candidate image was `{execution['candidate_image']}`. `performance-execution.json` records the source/input/binary hashes before and after both campaigns under a single shared exclusive lock. Reports added later do not change native sources. `phase2b.py` and `recipe.json` reproduce the commands; repeating viewed samples is outside this campaign policy.",'', '`primary-summary.json` preserves the complete primary run records and checks in a compact committed snapshot. `result.json` retains all forty primary samples and forty component samples, warmups, per-unit counters and evidence hashes. Raw primary checks, records and retained journals are in `focused-pinned/`; raw component pairs are in `component-pinned.json`. No production change followed timing, no second campaign was run, and no merge/push/adoption occurred.','', 'The numbers are local and non-rankable on Linux amd64 emulation on a Mac ARM64 host. They apply only to the four frozen timing units. Correctness-only units provide no speed evidence; five pairs cannot justify a general corpus-wide conclusion. All primary medians are under 1.08 seconds, which limits interpretation of small complete-run changes. The component binaries are separate standalone builds; their common boundaries do not isolate per-event costs within the production extension layout.']
    (AREA/'README.md').write_text('\n'.join(lines)+'\n')
    print(summary)
if __name__=='__main__':main()
