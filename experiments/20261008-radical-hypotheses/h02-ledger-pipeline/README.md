Executive summary: the bounded message pipeline preserved both journals exactly and shortened median full-container time in this fixed local series: mega-throughput +9.47%, pop-horizon-scale +3.38%, horizon-240s +7.78%, and the small price-time control +3.11%. All 48 runs passed correctness and native provenance. The macOS ARM host emulates Linux amd64; these results are rankable:false and no production adoption is proposed.

The primary result uses Docker `FinishedAt − StartedAt` for the entire container, including startup, core simulation/trace finalization, final Parquet drain/write and hashing. Positive improvement is `100 * (1 − median(candidate) / median(baseline))`. The measured implementation commit is `e4ac43f39c57c98ba6766f3b306b65b6bc89e891`; native source hashes matched the installed build manifest and stayed unchanged throughout the series.

| Timing unit | Baseline median (s) | Candidate median (s) | Full-run improvement | Candidate faster pairs |
|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | 1.829212074 | 1.655958820 | +9.47% | 3/5 |
| t3-gb-pop-horizon-scale | 1.021858975 | 0.987284436 | +3.38% | 3/5 |
| t3-gb-horizon-240s | 1.062136359 | 0.979516922 | +7.78% | 4/5 |
| t3-s001-price-time-priority | 0.307128042 | 0.297572764 | +3.11% | 3/5 |

Exactly one series ran: one excluded warm-up per side for each unit, followed by five pairs ordered AB, BA, AB, BA, AB. Every sample and outlier is retained. There were 48 accepted container runs (8 warm-ups + 40 timed samples), no profile-only launches, no extra repeats and no implementation changes after observing results. All 64 repeat/cross-side comparison records, each covering both journals, were byte/schema/ordered-value equal, and unchanged shared developer gates/native-path assertions passed. The two correctness-only units passed phase 2a separately.

The optional `MessageSink` leaves `t3::run(params)` and `_t3engine.run(cfg)` buffered and compatible. `run_write` installs the sink and passes complete 65,536-row blocks to one writer thread. The producer waits when both worker buffers are occupied. Each callback finishes consuming its non-owning Arrow views before its buffer is cleared and reused. Errors wake a blocked producer; cancellation, normal completion and stack unwinding join the worker before destroying the writer or temporary path. `Result.n_messages` counts all delivered rows, including blocks already handed off.

`WriteRecordBatch` appends aligned blocks inside a buffered row group. Explicit boundaries at 1,048,576 rows reproduce the old `WriteTable` row groups. The writer retains the existing Snappy compression, dictionary encoding, V1 data pages, Parquet 2.6 format, metadata/schema/footer and writer properties. Block size is a multiple of the pinned 1,024-row write batch, and divides the row group exactly. Each final short block occurs at the same final 1,024-row remainder as the full-table writer. There is no change to RNG, queue ordering, matching, trace extraction, dictionary representation, compression or SHA code.

Encoding and compression overlap simulation after each full 64 Ki block. Parquet buffers encoded pages until a row group closes; units below 1 Mi therefore overlap encoding/compression, with file flush and footer work at completion. Mega-throughput also closes its first full row group while simulation continues. The 664-message small control has no full block and measures pipeline setup/tail overhead. The column-buffer bound excludes Parquet's own buffered row group and the unchanged lifecycle trace.

Ledger output uses a unique sibling staging file and is renamed after both writes succeed. Empty lifecycle traces return `None`, discard staging and preserve existing output files. The default adapter and Python fallback remain unchanged. The diagnostic `simulation_wall_clock_sec` includes producer backpressure and the unchanged trace extraction; existing `profile.json` phases distinguish core work, final writing/draining, hashing and adapter overhead. Container elapsed time remains the primary measure.

| Timing unit | Reference ledger rows | Reason | Full-run improvement |
|---|---:|---|---|
| t3-gb-mega-throughput | 1,420,862 | sustained producer/writer overlap; crosses the original 1 Mi rowgroup | +9.47% |
| t3-gb-pop-horizon-scale | 892,129 | many blocks below one rowgroup; population and horizon pressure | +3.38% |
| t3-gb-horizon-240s | 692,641 | long horizon, compressed pages before final rowgroup flush | +7.78% |
| t3-s001-price-time-priority | 664 | small compatibility and thread/setup overhead control | +3.11% |

Correctness-only controls are `t3-s012-partial-fill-cancel-race` (178,236 messages; partial fills, cancel races, multiple buffers, nullable fields) and `t3-gbatch-hetero-mix` (five different markets; fresh writer state, independent offsets and correct native provenance). These choices are fixed in [policy.json](policy.json). No all-public or regression65 run is authorized for this experiment.

Host evidence is in [evidence/host-summary.json](evidence/host-summary.json) and [evidence/corpus-checks.json](evidence/corpus-checks.json). Large binaries, original/candidate host snapshots, generated Parquet pairs and logs remain under the ignored `evidence/` directory. `tests/run_host.py` reads the shared host environment; it does not install dependencies. It imports the repository differential checker instead of copying it. Both native buffer digests match on s001 and s012; lifecycle Parquet bytes match. Empty, tiny, simulation-error, message-writer-error and trace-writer-error checks pass. Generic pipeline checks cover backpressure, ownership, queued producer failure, close failure, cancellation and reuse, with ASan/UBSan and TSan checks. Synthetic Parquet checks cover 1, 1,023, 1,024, 65,535, 65,536, 65,537, 1 Mi−1, 1 Mi, 1 Mi+1, and 2 Mi+1,537 rows.

The host uses ARM/Python 3.13/Arrow 25.0.1. On its default page limits, the s012 ledger and large synthetic ledgers are schema/value-equal but byte-different. A full-rowgroup prototype was byte-identical; partial-block investigation found Arrow 25's 20,000-row page cap shifts checks when a 64 Ki input block ends. A test-only repeated probe lifts that cap to 1 Mi in both sides; all real and synthetic pairs then match bytes. This host investigation was supporting evidence about the batching mechanism; pinned proof is now recorded below. Production sources do not contain this test-only property override or the host numpy-log stub. Arrow 15 performs 1,024-row checks without the newer page-row cap; source references: [Arrow 15 column writer](https://raw.githubusercontent.com/apache/arrow/apache-arrow-15.0.2/cpp/src/parquet/column_writer.cc), [Arrow 25 column writer](https://raw.githubusercontent.com/apache/arrow/apache-arrow-25.0.0/cpp/src/parquet/column_writer.cc), [Arrow 15 buffered writer](https://raw.githubusercontent.com/apache/arrow/apache-arrow-15.0.2/cpp/src/parquet/arrow/writer.cc).

[Dockerfile](Dockerfile) follows the coordinator's pinned-base overlay recipe and additionally preserves the baseline extension for local binding tests. Its builder runs synthetic checks with the unchanged Python 3.11/Arrow 15.0.2 and compiler flags `-fno-fast-math -ffp-contract=off`; a byte mismatch fails the build before any timing. The runtime differs only by the candidate extension and dormant test artifacts. `tests/run_pinned.py` imports the unchanged repository checker and compares both bindings/journals; the coordinator runner adds selected corpus correctness, shared developer gates, strict native provenance and paired timing.

All phase-2 build, probe and measurement subprocesses used the campaign `docker_slot.py` and the explicit `colima-agenthon` context, linux/amd64, four CPUs, 16 GiB memory and swap, and no runtime network. The fixed schedule is one excluded warm-up per side, then five AB/BA pairs, retaining every sample and outlier. Improvement is `100 * (1 − median(candidate) / median(baseline))`: positive means faster and negative means slower. Failed correctness suppresses speed claims. [recipe.py](recipe.py) is a phase-2 recipe, and has not been executed in phase 1. The baseline and candidate identities below were fixed for the complete measurement. [result.json](result.json) is an exact copy of the standard runner result from the raw evidence directory.

Phase 2a passed with baseline `sha256:51fcf856e5c5ee4b33a6f43e059bf23035eeba44e2cb2b96692851696179e4c6` and candidate `sha256:c579f0db37f6e22491b5a191b335b3d87633d49e550c228dbe2e47fe90078bef`. The baseline tag was checked against its immutable ID before and after the build. The first failed attempt used a local image ID in `FROM`, which BuildKit treated as a registry reference; its command, exit and logs remain in `evidence/phase2a-attempt01/`. The verified-tag build in `evidence/phase2a-attempt02/` succeeded. No simulation source correction was needed.

The actual runtime is Python 3.11.17, NumPy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and SciPy 1.17.1. The installed candidate extension digest is `43a05ef5cf718e544b48af1b029a1c6853af60a2753d54409f602bd88f23d19a`; it matches the build manifest. Every compiled native-source digest matches this worktree, the preserved baseline extension matches the baseline image, and Python fallback source/numeric library digests are unchanged. Full audit data and synthetic page/rowgroup results are in `evidence/phase2a-runtime-audit/`.

All 20 pinned synthetic comparisons match bytes, schemas and values, including nulls, page/buffer boundaries, partial tails and multiple rowgroups. The pinned binding run in `evidence/phase2a-pinned-local/` passes native buffer/count equality, both journals on s001/s012, zero/tiny empty-output preservation and simulation/message-writer/trace-writer exceptions. Builder queue tests cover bounded reuse, backpressure, callback/close errors, blocked producer wakeup, abort and join.

The unchanged focused checker in `evidence/phase2a-focused-controls/summary.json` accepted all six selected units, all 12 container runs and all 20 market executions as actual native. Both journals for all ten market pairs are exactly byte/schema/ordered-value equal (20 file pairs), and shared developer gates pass. These were correctness runs, not the fixed paired timing schedule; their elapsed times are not used for a speed claim. All build/probe/check subprocesses held the shared serial slot; runtime probes used the fixed platform/resource/network limits. [phase2-readiness.json](phase2-readiness.json) links and hashes the complete evidence. The separately authorized fixed timing is now complete. `recipe.py` defaults to untimed controls and requires `--timing` for the authorized schedule.

All full-container samples below are seconds from the Docker clock, in pair index order. The warm-up column is excluded from the medians; P1/P3/P5 launch baseline then candidate, while P2/P4 launch candidate then baseline.

| Unit | Side | Excluded warm-up | P1 AB | P2 BA | P3 AB | P4 BA | P5 AB |
|---|---|---:|---:|---:|---:|---:|---:|
| t3-gb-mega-throughput | baseline | 1.705871184 | 2.350950066 | 2.124853708 | 1.612060963 | 1.714091465 | 1.829212074 |
| t3-gb-mega-throughput | candidate | 2.852089380 | 1.839867994 | 1.553429243 | 1.624545458 | 1.655958820 | 1.863865846 |
| t3-gb-pop-horizon-scale | baseline | 1.692781125 | 1.021858975 | 1.007945056 | 0.969253679 | 1.088736143 | 1.054058705 |
| t3-gb-pop-horizon-scale | candidate | 1.085017410 | 0.935924196 | 0.908825887 | 0.987284436 | 1.007911378 | 1.102441237 |
| t3-gb-horizon-240s | baseline | 0.856167787 | 0.991466635 | 1.062136359 | 1.134571565 | 0.943514839 | 1.074942197 |
| t3-gb-horizon-240s | candidate | 0.912988136 | 0.979516922 | 0.944281412 | 0.883697318 | 1.098203075 | 1.002076901 |
| t3-s001-price-time-priority | baseline | 0.377831735 | 0.307128042 | 0.275662948 | 0.282977020 | 0.335203396 | 0.319104920 |
| t3-s001-price-time-priority | candidate | 0.368174496 | 0.279702709 | 0.283874509 | 0.297572764 | 0.322502891 | 0.309690157 |

Reported adapter phase medians below are secondary diagnostics in seconds. Core includes the simulation and unchanged lifecycle-trace finalization. Candidate core can include bounded-queue waits and concurrent writer work while the producer proceeds; Parquet tail covers the remaining lifecycle write, message drain/rowgroup/footer close and native writer setup/cleanup. Configuration and hashing retain their original code paths. These independently computed phase medians do not add up exactly to the median Docker time; full-container startup and other costs also remain outside them.

| Unit | Side | Configuration | Core + trace finalize | Parquet tail | Hashing |
|---|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | baseline | 0.003858687 | 0.661415644 | 0.697153316 | 0.148159348 |
| t3-gb-mega-throughput | candidate | 0.003707746 | 0.838548897 | 0.383279457 | 0.158919961 |
| t3-gb-pop-horizon-scale | baseline | 0.002699400 | 0.289294380 | 0.414791733 | 0.097261307 |
| t3-gb-pop-horizon-scale | candidate | 0.002324842 | 0.361577153 | 0.286218007 | 0.094659894 |
| t3-gb-horizon-240s | baseline | 0.002851301 | 0.288794221 | 0.352919152 | 0.082143955 |
| t3-gb-horizon-240s | candidate | 0.002828455 | 0.281559882 | 0.265564048 | 0.086321409 |
| t3-s001-price-time-priority | baseline | 0.002249559 | 0.003691532 | 0.072396916 | 0.003123320 |
| t3-s001-price-time-priority | candidate | 0.002337049 | 0.005016020 | 0.054565836 | 0.002639408 |

On mega-throughput, median core/finalization rose from 0.661416 s to 0.838549 s while the residual Parquet tail fell from 0.697153 s to 0.383279 s. Population-scale shows the same balance: core 0.289294→0.361577 s and tail 0.414792→0.286218 s. This is consistent with moving ledger encoding/compression into the simulation interval, with queue backpressure and shared-resource costs, while reducing work left at the end. The profiles do not measure producer blocked time, worker CPU time or contention separately, so they cannot assign those core increases to one cause.

Horizon-240s reduced the tail from 0.352919 s to 0.265564 s with broadly similar core medians (0.288794→0.281560 s). Both population-scale and horizon-240s stay below one 1 Mi rowgroup, so their overlap is encoding/compression; buffered file output/footer work finishes in the tail. Mega-throughput crosses a rowgroup and also flushes the first completed rowgroup while simulation continues. The 664-message price-time control produces no mid-loop full block; its +3.11% result reflects the end-of-run/thread/startup path and local variation, and does not isolate the benefit of continuous large-block overlap.

Pairwise wins were 3/5 for mega, population-scale and price-time, and 4/5 for horizon. Baseline mega samples ranged from 1.612061 s to 2.350950 s; candidate samples ranged from 1.553429 s to 1.863866 s. Those slower early samples remain included. Five local pairs per scenario establish the reported medians for this series; they do not establish performance on official timing hardware or unmeasured scenarios. The observed shorter tail supports this hypothesis locally, with rankable:false and adopted:false.

<details>
<summary>All five reported phase samples, in pair index order</summary>

**t3-gb-mega-throughput — baseline**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002486514, 0.003858687, 0.003982032, 0.004926853, 0.003759414 |
| simulation_and_trace_finalize | 0.762404389, 0.743136137, 0.558756329, 0.558878267, 0.661415644 |
| parquet_write | 1.005970501, 0.771191826, 0.598302668, 0.697153316, 0.631576543 |
| hashing | 0.243773567, 0.195384107, 0.145360537, 0.146927925, 0.148159348 |

**t3-gb-mega-throughput — candidate**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.003529522, 0.003480152, 0.004318853, 0.004157446, 0.003707746 |
| simulation_and_trace_finalize | 0.862726587, 0.744903032, 0.838548897, 0.778474118, 0.897920120 |
| parquet_write | 0.418092470, 0.341833268, 0.388864179, 0.369383403, 0.383279457 |
| hashing | 0.159130720, 0.146353303, 0.154022980, 0.158919961, 0.186925166 |

**t3-gb-pop-horizon-scale — baseline**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.003574575, 0.002699400, 0.002383691, 0.002299712, 0.003437243 |
| simulation_and_trace_finalize | 0.263206665, 0.295121850, 0.289294380, 0.336536314, 0.275062075 |
| parquet_write | 0.414791733, 0.359462060, 0.348123972, 0.450800805, 0.415071749 |
| hashing | 0.097261307, 0.090368891, 0.084611134, 0.114507280, 0.105213368 |

**t3-gb-pop-horizon-scale — candidate**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002324842, 0.002302900, 0.002251693, 0.003170736, 0.002559543 |
| simulation_and_trace_finalize | 0.361577153, 0.319756002, 0.348970483, 0.363680070, 0.378261043 |
| parquet_write | 0.271923397, 0.262786120, 0.286218007, 0.302358914, 0.314346685 |
| hashing | 0.111123690, 0.092816953, 0.094659894, 0.091452997, 0.108138760 |

**t3-gb-horizon-240s — baseline**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002818620, 0.004867685, 0.002491575, 0.003942144, 0.002851301 |
| simulation_and_trace_finalize | 0.250806130, 0.345355279, 0.303656617, 0.243702566, 0.288794221 |
| parquet_write | 0.386919571, 0.330650468, 0.446709928, 0.341578286, 0.352919152 |
| hashing | 0.102385029, 0.071807152, 0.092677157, 0.082143955, 0.078204733 |

**t3-gb-horizon-240s — candidate**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002828455, 0.002320160, 0.003431264, 0.005249117, 0.002634120 |
| simulation_and_trace_finalize | 0.369807679, 0.281559882, 0.267636036, 0.401091896, 0.273099549 |
| parquet_write | 0.235211553, 0.298112949, 0.264541740, 0.265564048, 0.343866408 |
| hashing | 0.072440193, 0.086321409, 0.085948937, 0.086847081, 0.096402536 |

**t3-s001-price-time-priority — baseline**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002249559, 0.002362793, 0.002167651, 0.002705521, 0.002127295 |
| simulation_and_trace_finalize | 0.003948616, 0.003854574, 0.003442065, 0.003691532, 0.003553103 |
| parquet_write | 0.071169098, 0.056159877, 0.073164022, 0.082916539, 0.072396916 |
| hashing | 0.004028880, 0.002284251, 0.002518701, 0.003654328, 0.003123320 |

**t3-s001-price-time-priority — candidate**

| Phase | Five samples (s) |
|---|---|
| configuration | 0.002240140, 0.002205122, 0.002337049, 0.002971472, 0.004313938 |
| simulation_and_trace_finalize | 0.004683739, 0.005016020, 0.004937240, 0.007517441, 0.006950729 |
| parquet_write | 0.048353210, 0.052914313, 0.063785402, 0.095184719, 0.054565836 |
| hashing | 0.002182875, 0.002999650, 0.002347288, 0.002639408, 0.002814073 |

</details>

The standard result is [result.json](result.json), copied byte-for-byte from `evidence/phase2b-timing/result.json`. Raw run records, Docker state, profiles, complete retained journals, comparisons and the original summary remain under `evidence/phase2b-timing/`. [evidence/phase2b-summary.json](evidence/phase2b-summary.json) hashes the raw result and summary and verifies the fixed schedule, resource limits, native provenance and unchanged native sources. The actual command and complete launcher log are `evidence/phase2b-timing-command.json` and `evidence/phase2b-timing.log`. Large evidence stays ignored and local, preserving every accepted sample and the earlier failed build attempt. No merge, push or production adoption was performed.
