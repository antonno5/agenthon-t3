"""Executive summary: consolidate fixed H1 measurements without rerunning or filtering samples."""
from pathlib import Path
import hashlib
import json
import subprocess

AREA=Path(__file__).resolve().parent
ROOT=AREA.parents[2]
CAMPAIGN=ROOT.parents[1]

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v): p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

result=read(AREA/'evidence/timing/result.json')
summary=read(AREA/'evidence/timing/summary.json')
component=read(AREA/'component-result.json')
control=read(AREA/'evidence/pinned-controls/summary.json')
standalone=read(AREA/'pinned-standalone.json')
image=read(AREA/'image.json')
chain=read(AREA/'evidence/phase2-chain.json')
assert result['complete'] and result['accepted'] and component['complete']
assert control['complete'] and control['accepted'] and standalone['accepted'] and chain['complete']
assert result['counts']=={'accepted_runs':48,'timed_samples':40,'warmups':8}
assert len(control['runs'])==18 and len(control['comparisons'])==9
assert len(component['results'])==len(result['results'])==4
assert all(len(x['pairs'])==5 for x in component['results'])
assert all(len(v)==5 for x in result['results'] for v in x['container_seconds_samples'].values())
assert all(r['actual_native'] and all(v=='native' for v in r['actual_native'].values()) for r in summary['runs']+control['runs'])
assert image['implementation_commit']==result['candidate_implementation_commit']
current={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'baselines/native').rglob('*')) if p.is_file()}
assert current==result['source_hashes']==image['source_hashes']
assert not subprocess.check_output(['git','diff','HEAD','--','baselines'],cwd=ROOT)
plan=read(AREA/'plan-snapshot.json')
result['shared_runner_baseline_source_commit']=result['baseline_image_source_commit']
result['baseline_image_source_commit']=plan['baseline_image_source_commit']
result['baseline_native_source_commit']=plan['baseline_source_commit']
assert sha(ROOT/'baselines/build_native.py')==read(AREA/'recipe.json')['build_native_sha256']
result['build_native_sha256']=sha(ROOT/'baselines/build_native.py')
result.update(executive_summary='All pinned native correctness checks pass. Compact streamed trace construction has separate measured component and complete-container outcomes on four fixed scenarios; every sample is retained and no production adoption is made.',
              component_diagnostics=component,
              pinned_controls={'complete':True,'accepted':True,'containers':18,'market_outputs':26,
                               'comparisons':control['comparisons'],'artifact':str(AREA/'evidence/pinned-controls/summary.json')},
              pinned_standalone=standalone,
              host_checks_artifact=str(AREA/'host-checks.json'),
              image_audit=image,phase2_chain=chain,
              diagnostic_boundary='Capture/logging plus actual base finalizer versus all online candidate trace construction; initial simulation/replay preparation/equality excluded. Component samples never enter full-container medians.',
              no_samples_discarded=True,no_post_measurement_tuning=True,
              scope={'production_sources':['baselines/native/engine.cpp','baselines/native/trace_stream.hpp'],
                     'unchanged':['scenario JSON','configuration mapping','RNG','float build flags','writer','scorer','dependencies','tolerances'],
                     'no_full_corpus_simulation':True,'no_merge_push_or_main_changes':True,'adopted':False},
              artifact_sha256={str(p.relative_to(AREA)):sha(p) for p in [AREA/'image.json',AREA/'pinned-standalone.json',AREA/'component-result.json',AREA/'host-checks.json',AREA/'corpus-checks.json',AREA/'recipe.json',AREA/'source-manifest.json',AREA/'evidence/pinned-controls/summary.json',AREA/'evidence/timing/summary.json',AREA/'evidence/phase2-chain.json']})
dump(AREA/'result.json',result)

full={x['unit']:x for x in result['results']}
comp={x['case'].split('/')[0]:x for x in component['results']}
full_changes=[x['time_change_pct'] for x in full.values()]
component_speeds=[x['speedup'] for x in comp.values()]
exec_summary=(f'Executive summary: Pinned correctness passes for all 13 assigned markets. Streamed trace capture plus finalization is {min(component_speeds):.2f}–{max(component_speeds):.2f}x as fast across the four component diagnostics. Complete-container median time changes range from {min(full_changes):+.2f}% to {max(full_changes):+.2f}%. Every fixed pair and outlier is retained; these local results are non-rankable and the implementation remains isolated.')
lines=[exec_summary,'',
'Only `baselines/native/engine.cpp` and the new `trace_stream.hpp` change production behavior. Trader snapshot logs and the raw quote log are removed. Output-sized lifecycle fields accumulate for one timestamp, ordered by `(order_id, original_log_owner, append_ordinal)`, then append directly to the final columns. Quotes precede order rows at the same timestamp. The normal path has no global stable sort, row reconstruction, quote merge or final execution hash-map pass.','',
'Quote folding retains first appearance order and the last recorded value per side within a timestamp. Absent/reappearing sides keep their first slot. Equal values at different timestamps remain separate rows. A dense execution-index vector demotes the previous retained execution and marks the newest ORDER_FILLED, preserving the reference’s unusual meaning even when quantity remains or an order is later cancelled. Negative-latency configurations use guarded deferred compact sorting. One giant timestamp group still requires a large sort; execution-index memory grows with the largest executed id, including gaps. Final output columns remain resident.','',
'The complete-container comparison uses Docker FinishedAt minus StartedAt, with one excluded warmup per side and five AB/BA/AB/BA/AB pairs per unit. Negative time change means a shorter run. No sample was discarded or repeated after inspection.','',
'| Assigned scenario | Base median (s) | Candidate median (s) | Time change | Faster pairs |',
'|---|---:|---:|---:|---:|']
for name,x in full.items():
    med=x['median_container_seconds']
    lines.append(f"| {name} | {med['baseline']:.6f} | {med['candidate']:.6f} | {x['time_change_pct']:+.2f}% | {x['candidate_faster_pairs']}/5 |")
lines+=['',
'The component diagnostic replays identical real logs captured by the original native engine from those same four scenarios. It times original snapshot capture plus the actual Sim::extract against every candidate append, online quote fold, timestamp sort/flush, indexed execution update and final column emission. Initial simulation, chronological replay preparation, baseline agent scaffold initialization and equality checks are excluded. Baseline extract-only samples are secondary and are never compared with candidate finish-only time. Candidate auxiliary-buffer destruction is included by its local replay function, while baseline logger destruction follows the clock; this makes the candidate boundary slightly conservative. One excluded warmup per side and five fixed pairs per unit are retained separately from full-run medians. A separate untimed pass collects counters; production and timed candidate replay contain no per-row diagnostic counters.','',
'| Assigned scenario | Base component median (s) | Candidate component median (s) | Speedup | Time reduction |',
'|---|---:|---:|---:|---:|']
for name,x in comp.items():
    lines.append(f"| {name} | {x['baseline_median_seconds']:.6f} | {x['candidate_median_seconds']:.6f} | {x['speedup']:.2f}x | {x['time_reduction_pct']:+.2f}% |")
lines+=['',
'The 3x component aspiration is evaluated against those measured capture-plus-finalization boundaries. ' + ('Every assigned component diagnostic meets it.' if min(component_speeds)>=3 else ('It is reached on some assigned scenarios. ' if max(component_speeds)>=3 else f'It is not reached on any assigned scenario; the strongest measured ratio is {max(component_speeds):.2f}x. '))+'Complete-container changes also include simulation, serialization, hashing and startup costs, so component ratios are not end-to-end speedups.','',
'| Assigned scenario | Captured records | Baseline snapshot rows | Candidate peak pending rows | Dense execution slots | Dense capacity bytes |',
'|---|---:|---:|---:|---:|---:|']
for name,x in comp.items():
    lines.append(f"| {name} | {x['input_rows']} | {x['order_snapshot_rows_baseline']} | {x['pending_peak_rows_candidate']} | {x['dense_execution_slots_candidate']} | {x['dense_execution_capacity_bytes_candidate']} |")
lines+=['',
'Candidate retains zero full order snapshot rows. Pending rows contain the output fields plus owner/ordinal provenance; actual row size, quote-log bytes and raw maximum timestamp-group counts are retained in `component-result.json`. These counters describe retained trace structures rather than total process peak memory.','',
'Host and pinned standalone checks compare all seven lifecycle and twelve message columns against actual base source in optimized and ASan/UBSan modes, across the 13 market configurations in the nine selected units. Each mode covers 2,687,372 lifecycle and 2,944,093 message rows. Isolated checks cover stable owner/ordinal ties, partial-fill/cancellation semantics, missing fill prices, quote first/last appearance, absent/reappearing sides, cross-time duplicates, empty input, reversed time, the deferred path, sparse ids, a 4,096-row timestamp group and 64 generated histories totaling 131,072 records. Host leak detection is disabled because macOS does not support it; Linux checks enable leak detection. The initial rejected host leak-detector option is recorded in `host-checks.json`.','',
'Pinned output checks include 18 separate correctness containers covering 26 market outputs and nine baseline/candidate comparisons, followed by 48 campaign outputs (eight excluded warmups and forty timed samples). Both journals must match in bytes, schema and ordered values; every market passes the unchanged shared developer gates, digest checks and actual-native provenance. All nine assigned corpus manifests and shared public-firewall checks pass. Raw records, logs, profiles and retained Parquet outputs remain in ignored `evidence/`; the shared checker deduplicates only already validated closed outputs to save disk.','',
'Frozen measured implementation commit: `'+result['candidate_implementation_commit']+'`. Base source: `'+result['base_commit']+'`. Audited baseline image source commit: `286ae974641e4ad23e81288b5beee2d7d9da20c5`, whose native/build sources match the base. Native source hashes remained unchanged throughout the campaign. Later report/tool commits do not change the measured implementation.','',
'Baseline image: `'+image['baseline_image']+'`. Candidate image: `'+image['candidate_image']+'`. Cached compiler image: `'+image['builder_image']+'`. Local FROM tags were checked against the immutable IDs before and after build. Candidate runtime retains the complete baseline layer prefix; only the native extension is overlaid. Python 3.11.17, numpy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and scipy 1.17.1 are unchanged. Native numeric build flags, mapper, scenarios, scorer and tolerances are unchanged.','',
'The entire authorized checks/component/timing chain ran under one exclusive campaign `docker_slot.py` lock, following H3 correctness and preceding H2/H3 timings. Linux amd64, 4 CPUs, 16g memory plus equal memory-swap, and network none were fixed. These are local measurements on a Mac ARM64 host with emulated Linux amd64 containers, not official hardware. No full-corpus simulation, selective rerun, post-measurement tuning, merge, push, main-checkout edit or production adoption occurred.','',
'`result.json` retains full-container samples, pairs, phase diagnostics, component samples, structural counts, pinned controls, runtime/image/source audit and artifact digests. `phase2_chain.py` preserves stage logs and completion state. `recipe.json`, `phase2.py` and the frozen `plan-snapshot.json` define the reproducible stages. Existing component/timing outputs are guarded against accidental reruns; this archived recipe is not a new authorization to repeat them.']
(AREA/'README.md').write_text('\n'.join(lines)+'\n')
audit={'executive_summary':'Measured native sources match the frozen implementation and all required correctness/timing artifacts are accepted.',
       'accepted':True,'implementation_commit':result['candidate_implementation_commit'],
       'source_hashes':current,'candidate_image':image['candidate_image'],
       'timing_containers':48,'control_containers':18,'timed_pairs_per_unit':5,
       'component_pairs_per_unit':5,'all_samples_retained':True,
       'artifacts':result['artifact_sha256']}
dump(AREA/'report-audit.json',audit)
print(json.dumps({'complete':True,'result':str(AREA/'result.json'),'full_time_changes_pct':full_changes,'component_speedups':component_speeds}))
