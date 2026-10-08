"""Executive summary: summarize the fixed primary and diagnostic series without adding measurements."""
import json
from pathlib import Path
import shutil
import statistics
report=Path(__file__).resolve().parent;evidence=report/'evidence'
primary=json.loads((evidence/'timing/result.json').read_text())
diag=json.loads((evidence/'diagnostics/run/diagnostics.json').read_text())
controls=json.loads((evidence/'controls/summary.json').read_text())
pinned=json.loads((evidence/'pinned/checks.json').read_text())
assert primary['complete'] and primary['accepted'] and primary['source_unchanged_during_measurement']
assert diag['complete'] and len(diag['samples'])==192
assert controls['complete'] and controls['accepted'] and len(controls['runs'])==14
assert all(s['byte_equal_to_real_baseline'] for s in diag['samples'])
shutil.copy2(evidence/'timing/result.json',report/'result.json')
shutil.copy2(evidence/'pinned/checks.json',report/'pinned-validation.json')
shutil.copy2(evidence/'controls/summary.json',report/'controls-validation.json')
shutil.copy2(evidence/'diagnostics/run/diagnostics.json',report/'component-results.json')
units=primary['assigned_units']
med=lambda unit,mode,clock:next(v for v in diag['medians'] if v['unit']==unit and v['mode']==mode and v['clock']==clock)
fields=['engine_including_producer_wait_seconds','producer_wait_seconds','ledger_write_callbacks_seconds',
        'ledger_close_seconds','trace_write_seconds','finish_wait_seconds','ledger_dispatcher_idle_seconds',
        'ledger_callback_count','producer_submit_count']
pipeline={}
for unit in units:
    samples=[s for s in diag['samples'] if s['unit']==unit and s['mode']=='pipeline' and s['kind']=='pair']
    pipeline[unit]={side:{key:statistics.median(s['result'][key] for s in samples if s['side']==side)
                         for key in fields} for side in ['baseline','candidate']}
(report/'pipeline-medians.json').write_text(json.dumps({'executive_summary':'Pipeline clocks are overlapping medians, not additive elapsed times; producer waits and dispatcher idle are separate from encoding.',
    'units':pipeline},indent=2)+'\n')
lines=['Executive summary: bounded parallel Parquet encoding passed pinned byte correctness, but did not deliver a radical gain. Standalone write-plus-close improved by 1.23–1.46×, below the aspirational 2× encoding target. Complete-container median time fell by 14.32%, 5.09%, 0.41% and 7.91% on the four assigned large scenarios. The 0.41% horizon result is small and only three of five pairs were faster. All fixed samples are retained; there were no adaptive repeats, source changes, adoption, merge or push.',
'', 'The implementation is commit `c9ec65640d6904ab01a26d2369caef5075aca86b` on `codex/exp-20261008-component-h02-parquet-parallel`. Only `baselines/native/pqwrite.cpp` changes production behavior. One process-wide Arrow ThreadPool with two workers encodes both journals; simulation and ledger dispatch remain outside it. Trace uses buffered RecordBatch row groups of 1,048,576 rows; messages retain 65,536-row callbacks. Dense columns retain progressive dictionary growth, default 1,024-row encoder write batches, original page/dictionary thresholds, Snappy, metadata/nulls, 64Mi property maximum and staged ledger publication. Input validation and empty/error behavior are preserved.',
'', 'Primary complete-container timing (seconds). Positive reduction means faster. All five samples per side, pair ordering and outliers are in [result.json](result.json). The clock is Docker State FinishedAt minus StartedAt. These are local non-rankable measurements.',
'', '| Scenario | Baseline median | Candidate median | Time reduction | Faster pairs |', '|---|---:|---:|---:|---:|']
for r in primary['results']:
    m=r['median_container_seconds'];lines.append(f"| {r['unit']} | {m['baseline']:.6f} | {m['candidate']:.6f} | {r['time_reduction_pct']:.2f}% | {r['candidate_faster_pairs']}/5 |")
lines+=['', 'Standalone encoding on identical real baseline engine columns (write plus close to an in-memory sink, excluding setup). Output hashes matched the original real Parquet files on every sample. These clocks include Arrow/Parquet encoding, compression, group/file close and memory sink copying. They exclude simulation, vector-to-Arrow construction, input reading, disk output and producer waiting.',
'', '| Scenario | Trace baseline → candidate, s | Trace speedup / reduction | Ledger baseline → candidate, s | Ledger speedup / reduction |', '|---|---:|---:|---:|---:|']
for unit in units:
    t=med(unit,'trace','trace_write_plus_close_seconds');m=med(unit,'messages','messages_write_plus_close_seconds')
    lines.append(f"| {unit} | {t['seconds']['baseline']:.6f} → {t['seconds']['candidate']:.6f} | {t['speedup']:.3f}× / {t['time_reduction_pct']:.2f}% | {m['seconds']['baseline']:.6f} → {m['seconds']['candidate']:.6f} | {m['speedup']:.3f}× / {m['time_reduction_pct']:.2f}% |")
lines+=['', 'Separate overlap and pipeline diagnostics. Overlap starts two outside writer callers on the same real columns, sharing the two-worker encoder pool. Its wall clock includes writer setup, write, close and join. Pipeline uses disposable instrumented extensions with identical clocks on both sides and the normal simulation/file-output path; its run_write wall excludes imports/config building/hashing. Neither is the primary container clock.',
'', '| Scenario | Two-file overlap baseline → candidate, s | Overlap reduction | Instrumented pipeline baseline → candidate, s | Pipeline reduction |','|---|---:|---:|---:|---:|']
for unit in units:
    o=med(unit,'overlap','wall_seconds');p=med(unit,'pipeline','run_write_wall_seconds')
    lines.append(f"| {unit} | {o['seconds']['baseline']:.6f} → {o['seconds']['candidate']:.6f} | {o['time_reduction_pct']:.2f}% | {p['seconds']['baseline']:.6f} → {p['seconds']['candidate']:.6f} | {p['time_reduction_pct']:.2f}% |")
lines+=['', 'Median pipeline waits and callbacks, seconds (baseline → candidate). These medians overlap and must not be added into total elapsed time. Engine wall includes producer wait and lifecycle assembly; producer condition-variable wait excludes mutex acquisition. Ledger callbacks include array construction, RecordBatch encoding and row-group flush. Trace wall includes conversion and file finalization. finish_wait is the extra wait after trace writing; ledger close/finish may describe the same work.',
'', '| Scenario | Producer wait | Ledger callbacks | Ledger close | Trace writer | finish_wait |', '|---|---:|---:|---:|---:|---:|']
for unit in units:
    d=pipeline[unit]
    cells=[f"{d['baseline'][k]:.6f} → {d['candidate'][k]:.6f}" for k in ['producer_wait_seconds','ledger_write_callbacks_seconds','ledger_close_seconds','trace_write_seconds','finish_wait_seconds']]
    lines.append('| '+unit+' | '+' | '.join(cells)+' |')
lines+=['', 'Structural counters and input identity. Both sides use exactly the same rows, schema, nulls and vocabulary; the IPC input hash and real Parquet digest are stored in [component-results.json](component-results.json). Both writer modes preserve the original 1Mi groups. Callback/submission counts match exactly on every pipeline sample.',
'', '| Scenario | Trace rows / groups | Ledger rows / groups | Ledger callbacks / submissions, both sides |', '|---|---:|---:|---:|']
for unit in units:
    t=diag['inputs'][unit+'/trace.parquet'];m=diag['inputs'][unit+'/message_trace.parquet'];d=pipeline[unit]
    assert d['baseline']['ledger_callback_count']==d['candidate']['ledger_callback_count']==d['baseline']['producer_submit_count']==d['candidate']['producer_submit_count']
    lines.append(f"| {unit} | {t['rows']:,} / {(t['rows']+1048575)//1048576} | {m['rows']:,} / {(m['rows']+1048575)//1048576} | {int(d['baseline']['ledger_callback_count'])} / {int(d['baseline']['producer_submit_count'])} |")
lines+=['', 'The source audit is in [source-audit.json](source-audit.json). Arrow 15.0.2 WriteTable is serial even with use_threads enabled. Buffered WriteRecordBatch creates distinct column contexts and invokes ParallelFor with the configured executor. The two blocking writer callers never run inside that executor, avoiding nested executor deadlock. Row-group close serializes column writers in schema order. Pending column work is bounded by the two synchronous outside writers; the existing three ledger buffers/backpressure remain unchanged.',
'', f"Pinned correctness passed {len(pinned['comparisons'])} baseline/candidate journal fixture comparisons in normal and ASan/UBSan builds; original full-table/stream byte equivalence passed on Arrow15. Fixtures cover page/write-batch/block/group boundaries, late vocabulary, high-cardinality UTF8 dictionary fallback, mixed/all/no nulls, concurrent writers, malformed tables and append errors. Binding checks cover the two assigned single-market correctness scenarios and all five hetero-batch markets, including native buffers, empty controls and staged-output cleanup. The shared controls runner accepted 14 runs across all seven allowed units, with exact bytes, schemas, ordered values, actual native execution and unchanged gates. See [pinned-validation.json](pinned-validation.json) and [controls-validation.json](controls-validation.json). Sanitizers instrument our sources, not the prebuilt Arrow libraries.",
'', 'Measurement contract: context colima-agenthon, Linux amd64 on a Mac ARM64 host, four CPUs, 16GiB memory+swap, network none. The whole build/check/control/diagnostic-build/primary-series/diagnostic-series chain held the shared exclusive slot. Baseline FROM tags were verified before and after build; subsequent runs used immutable IDs. Python 3.11.17, numpy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and scipy 1.17.1 were audited. The candidate image is `sha256:8be4efb0eff25eeb35fb63ea33b370919ca70e55a2494232c005429056429941`; baseline is `sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c`. Exact runtime extension binaries/digests are retained in `evidence/runtime-audit`.',
'', 'The primary series contains 48 accepted runs: 8 excluded warmups and 40 timed runs (five AB/BA pairs per unit). Separate diagnostics contain exactly 192 samples: 4 units × 4 modes × (2 excluded warmups + 10 timed samples), or 160 timed samples and 32 warmups. Each uses its predeclared AB/BA order. All outputs are byte-equal to the real baseline journals. No extra benchmark was run after viewing results. No production source changed after pinned correctness or during timing.',
'', 'All diagnostic samples, setup/write/close/CPU clocks, pair identities and hashes are in [component-results.json](component-results.json); engine/idle/callback counters are in [pipeline-medians.json](pipeline-medians.json). Raw logs, commands, binaries, validated journal paths and pinned sources are in `evidence`. The storage manifest records independently checked equal-byte hardlinks. Diagnostic outputs originally compared and hashed after each timed region are retained as hardlinks to those identical validated control bytes; uncompressed IPC input files are preserved with their originally recorded pinned-serializer hashes. This storage-only preservation repeats no simulation or measurement.',
'', 'Interpretation: reducing producer backpressure and the ledger callback wall is useful, but the measured standalone encoding never reaches 2×. The overlap gain falls to 0.35–8.20% when the two files share their bounded pool. This is consistent with shared-worker contention and serial close/conversion costs limiting parallel benefit; it is an inference from the clocks, not a measured per-column CPU breakdown. Ledger final close/join does not consistently get faster, and the pool does not accelerate serial lifecycle construction, Python/runtime startup or disk publication. Pipeline clocks and the complete-container clock measure different scopes, so the larger instrumented pipeline percentages do not override the primary result.',
'', 'Limitations: five pairs provide a small local sample, not statistical assurance or official timing hardware. The horizon container result is particularly weak (0.41%, 3/5 faster). One market caller is assumed for the four-active-thread claim; unrelated concurrent callers add outside threads. Buffered trace groups can raise memory use. Pool submission/shutdown infrastructure faults were not injected. The hypothesis gives moderate local improvement on some scenarios and misses the radical-speedup target. This isolated experiment is not adopted.',
'', 'Reproduction: [recipe.sh](recipe.sh) runs individual authorized steps; [phase2.py](phase2.py) chains them under `CAMPAIGN/docker_slot.py`. It must be dispatched by the coordinator with the frozen assigned scenario plan and audited cached builder. Primary timing uses the unchanged shared run_focused.py and production extension. Instrumentation is confined to disposable diagnostic source copies. [host-validation.json](host-validation.json) remains preliminary host Arrow25 evidence; pinned evidence supersedes its library-specific differences. No sealed data, scorer changes or dependency changes are involved.']
(report/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'primary_complete':primary['complete'],'diagnostic_samples':len(diag['samples']),
 'max_standalone_encoding_speedup':max(x['speedup'] for x in diag['medians'] if x['mode'] in ['trace','messages'] and x['clock'].endswith('write_plus_close_seconds'))}))
