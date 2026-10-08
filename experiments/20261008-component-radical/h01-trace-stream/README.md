Executive summary: Pinned correctness passes for all 13 assigned markets. Streamed trace capture plus finalization is 1.54–2.96x as fast across the four component diagnostics. Complete-container median time changes range from -7.44% to -3.52%. Every fixed pair and outlier is retained; these local results are non-rankable and the implementation remains isolated.

Only `baselines/native/engine.cpp` and the new `trace_stream.hpp` change production behavior. Trader snapshot logs and the raw quote log are removed. Output-sized lifecycle fields accumulate for one timestamp, ordered by `(order_id, original_log_owner, append_ordinal)`, then append directly to the final columns. Quotes precede order rows at the same timestamp. The normal path has no global stable sort, row reconstruction, quote merge or final execution hash-map pass.

Quote folding retains first appearance order and the last recorded value per side within a timestamp. Absent/reappearing sides keep their first slot. Equal values at different timestamps remain separate rows. A dense execution-index vector demotes the previous retained execution and marks the newest ORDER_FILLED, preserving the reference’s unusual meaning even when quantity remains or an order is later cancelled. Negative-latency configurations use guarded deferred compact sorting. One giant timestamp group still requires a large sort; execution-index memory grows with the largest executed id, including gaps. Final output columns remain resident.

The complete-container comparison uses Docker FinishedAt minus StartedAt, with one excluded warmup per side and five AB/BA/AB/BA/AB pairs per unit. Negative time change means a shorter run. No sample was discarded or repeated after inspection.

| Assigned scenario | Base median (s) | Candidate median (s) | Time change | Faster pairs |
|---|---:|---:|---:|---:|
| t3-mr-deep-book-state-size | 0.507680 | 0.478296 | -5.79% | 5/5 |
| t3-mp05-cancel-churn-newest | 0.483324 | 0.463443 | -4.11% | 3/5 |
| t3-gb-horizon-240s | 0.756516 | 0.729851 | -3.52% | 5/5 |
| t3-gb-mega-throughput | 1.311560 | 1.214002 | -7.44% | 5/5 |

The component diagnostic replays identical real logs captured by the original native engine from those same four scenarios. It times original snapshot capture plus the actual Sim::extract against every candidate append, online quote fold, timestamp sort/flush, indexed execution update and final column emission. Initial simulation, chronological replay preparation, baseline agent scaffold initialization and equality checks are excluded. Baseline extract-only samples are secondary and are never compared with candidate finish-only time. Candidate auxiliary-buffer destruction is included by its local replay function, while baseline logger destruction follows the clock; this makes the candidate boundary slightly conservative. One excluded warmup per side and five fixed pairs per unit are retained separately from full-run medians. A separate untimed pass collects counters; production and timed candidate replay contain no per-row diagnostic counters.

| Assigned scenario | Base component median (s) | Candidate component median (s) | Speedup | Time reduction |
|---|---:|---:|---:|---:|
| t3-mr-deep-book-state-size | 0.009093 | 0.005919 | 1.54x | +34.91% |
| t3-mp05-cancel-churn-newest | 0.006814 | 0.004259 | 1.60x | +37.50% |
| t3-gb-horizon-240s | 0.031536 | 0.012517 | 2.52x | +60.31% |
| t3-gb-mega-throughput | 0.075532 | 0.025510 | 2.96x | +66.23% |

The 3x component aspiration is evaluated against those measured capture-plus-finalization boundaries. It is not reached on any assigned scenario; the strongest measured ratio is 2.96x. Complete-container changes also include simulation, serialization, hashing and startup costs, so component ratios are not end-to-end speedups.

| Assigned scenario | Captured records | Baseline snapshot rows | Candidate peak pending rows | Dense execution slots | Dense capacity bytes |
|---|---:|---:|---:|---:|---:|
| t3-mr-deep-book-state-size | 321300 | 192783 | 32 | 62691 | 771712 |
| t3-mp05-cancel-churn-newest | 240831 | 144526 | 12 | 46169 | 513840 |
| t3-gb-horizon-240s | 556327 | 371677 | 8 | 109083 | 1018976 |
| t3-gb-mega-throughput | 1182524 | 757945 | 12 | 224207 | 1893376 |

Candidate retains zero full order snapshot rows. Pending rows contain the output fields plus owner/ordinal provenance; actual row size, quote-log bytes and raw maximum timestamp-group counts are retained in `component-result.json`. These counters describe retained trace structures rather than total process peak memory.

Host and pinned standalone checks compare all seven lifecycle and twelve message columns against actual base source in optimized and ASan/UBSan modes, across the 13 market configurations in the nine selected units. Each mode covers 2,687,372 lifecycle and 2,944,093 message rows. Isolated checks cover stable owner/ordinal ties, partial-fill/cancellation semantics, missing fill prices, quote first/last appearance, absent/reappearing sides, cross-time duplicates, empty input, reversed time, the deferred path, sparse ids, a 4,096-row timestamp group and 64 generated histories totaling 131,072 records. Host leak detection is disabled because macOS does not support it; Linux checks enable leak detection. The initial rejected host leak-detector option is recorded in `host-checks.json`.

Pinned output checks include 18 separate correctness containers covering 26 market outputs and nine baseline/candidate comparisons, followed by 48 campaign outputs (eight excluded warmups and forty timed samples). Both journals must match in bytes, schema and ordered values; every market passes the unchanged shared developer gates, digest checks and actual-native provenance. All nine assigned corpus manifests and shared public-firewall checks pass. Raw records, logs, profiles and retained Parquet outputs remain in ignored `evidence/`; the shared checker deduplicates only already validated closed outputs to save disk.

Frozen measured implementation commit: `c821fecb3f6f2f837e996ab162e907cf22fe17f7`. Base source: `33027d74553e9a318d66557fe0f7b7bed84cfa38`. Audited baseline image source commit: `286ae974641e4ad23e81288b5beee2d7d9da20c5`, whose native/build sources match the base. Native source hashes remained unchanged throughout the campaign. Later report/tool commits do not change the measured implementation.

Baseline image: `sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c`. Candidate image: `sha256:8bcfa684de326a8e1c31b3b00c13d26a903dbae3ce46fe3eeec8158785ccc3ab`. Cached compiler image: `sha256:902a221eca63fc3781587c30114edd3d33e16d057049b30a23b552a0e4bc0d57`. Local FROM tags were checked against the immutable IDs before and after build. Candidate runtime retains the complete baseline layer prefix; only the native extension is overlaid. Python 3.11.17, numpy 1.26.4, pandas 1.5.3, Arrow 15.0.2 and scipy 1.17.1 are unchanged. Native numeric build flags, mapper, scenarios, scorer and tolerances are unchanged.

The entire authorized checks/component/timing chain ran under one exclusive campaign `docker_slot.py` lock, following H3 correctness and preceding H2/H3 timings. Linux amd64, 4 CPUs, 16g memory plus equal memory-swap, and network none were fixed. These are local measurements on a Mac ARM64 host with emulated Linux amd64 containers, not official hardware. No full-corpus simulation, selective rerun, post-measurement tuning, merge, push, main-checkout edit or production adoption occurred.

`result.json` retains full-container samples, pairs, phase diagnostics, component samples, structural counts, pinned controls, runtime/image/source audit and artifact digests. `phase2_chain.py` preserves stage logs and completion state. `recipe.json`, `phase2.py` and the frozen `plan-snapshot.json` define the reproducible stages. Existing component/timing outputs are guarded against accidental reruns; this archived recipe is not a new authorization to repeat them.
