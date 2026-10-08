Three isolated native optimizations were tested on only their frozen scenarios. Complete-container percentages and component diagnostics are separate; no production adoption occurred.

Subsequent integration: H1 and H2 were applied to `codex/develop` at the user's request without additional runs. See the [integration note](integration.md); the tables below remain the original independent experiment results.

Percentages below mean reduction in elapsed time: `100 * (1 - candidate_median / baseline_median)`. Positive is faster; negative is slower. They are not percentages of throughput increase.

Each scenario has one excluded warmup per side and five fixed AB/BA pairs. Every sample is retained. Runs use Docker start-to-finish wall time, four CPUs, 16GiB memory and swap cap, network none, pinned Python 3.11.17 / Arrow 15.0.2, and mandatory native execution. All campaigns ran sequentially under a shared lock.

These are local measurements on an ARM64 Mac running emulated Linux amd64, not official timing hardware. No scenario outside the assigned subset was timed.

| Hypothesis | Scenario | Baseline, s | Candidate, s | Time reduction | Faster pairs |
|---|---|---:|---:|---:|---:|
| [h01-trace-stream](h01-trace-stream/README.md) | `t3-mr-deep-book-state-size` | 0.5077 | 0.4783 | +5.79% | 5/5 |
| [h01-trace-stream](h01-trace-stream/README.md) | `t3-mp05-cancel-churn-newest` | 0.4833 | 0.4634 | +4.11% | 3/5 |
| [h01-trace-stream](h01-trace-stream/README.md) | `t3-gb-horizon-240s` | 0.7565 | 0.7299 | +3.52% | 5/5 |
| [h01-trace-stream](h01-trace-stream/README.md) | `t3-gb-mega-throughput` | 1.3116 | 1.2140 | +7.44% | 5/5 |
| [h02-parquet-parallel](h02-parquet-parallel/README.md) | `t3-gb-mega-throughput` | 1.6455 | 1.4099 | +14.32% | 4/5 |
| [h02-parquet-parallel](h02-parquet-parallel/README.md) | `t3-gb-pop-horizon-scale` | 0.9302 | 0.8828 | +5.09% | 4/5 |
| [h02-parquet-parallel](h02-parquet-parallel/README.md) | `t3-gb-horizon-240s` | 0.9203 | 0.9165 | +0.41% | 3/5 |
| [h02-parquet-parallel](h02-parquet-parallel/README.md) | `t3-mr-deep-book-state-size` | 0.6639 | 0.6114 | +7.91% | 4/5 |
| [h03-protocol-fusion](h03-protocol-fusion/README.md) | `t3-gb-highfreq-40hz-60s` | 0.8836 | 0.8387 | +5.08% | 4/5 |
| [h03-protocol-fusion](h03-protocol-fusion/README.md) | `t3-gb-pop-horizon-scale` | 1.0686 | 1.0759 | -0.68% | 1/5 |
| [h03-protocol-fusion](h03-protocol-fusion/README.md) | `t3-mp07-heavy-flow-oldest` | 0.3528 | 0.3501 | +0.78% | 4/5 |
| [h03-protocol-fusion](h03-protocol-fusion/README.md) | `t3-coarse-tick-ties` | 0.3969 | 0.3802 | +4.19% | 3/5 |

None of the tested changes accelerated a complete scenario by 2x. The per-scenario results above are the outcome of this campaign.

The component table uses different, explicitly bounded workloads for each hypothesis. Its percentages do not imply the same reduction in complete-container wall time.

| Hypothesis / timed component | Scenario | Time reduction | Speed factor |
|---|---|---:|---:|
| H1 capture + finalization | `t3-mr-deep-book-state-size` | +34.91% | 1.536x |
| H1 capture + finalization | `t3-mp05-cancel-churn-newest` | +37.50% | 1.600x |
| H1 capture + finalization | `t3-gb-horizon-240s` | +60.31% | 2.519x |
| H1 capture + finalization | `t3-gb-mega-throughput` | +66.23% | 2.961x |
| H2 overlapping memory encoders | `t3-gb-mega-throughput` | +8.20% | 1.089x |
| H2 overlapping memory encoders | `t3-gb-pop-horizon-scale` | +0.35% | 1.003x |
| H2 overlapping memory encoders | `t3-gb-horizon-240s` | +6.91% | 1.074x |
| H2 overlapping memory encoders | `t3-mr-deep-book-state-size` | +7.74% | 1.084x |
| H3 engine excluding finalization/writer | `t3-gb-highfreq-40hz-60s` | -9.39% | 0.914x |
| H3 engine excluding finalization/writer | `t3-gb-pop-horizon-scale` | -7.86% | 0.927x |
| H3 engine excluding finalization/writer | `t3-mp07-heavy-flow-oldest` | -8.41% | 0.922x |
| H3 engine excluding finalization/writer | `t3-coarse-tick-ties` | -9.69% | 0.912x |

Component measurements use narrower boundaries and do not replace the table above. See each hypothesis report for all samples, boundaries, component percentages and structural counters.

Both journals passed exact byte/schema/ordered-value checks and the unchanged shared gates. Assigned correctness-only cases, host checks, Linux ASan/UBSan and isolated boundary/error tests are retained in the individual archives. [Independent audit](independent-audit.json) recomputes percentages, checks output hashes, scenario scope, unchanged sources and nonoverlapping timing launches.

Implementations remain isolated in these branches; the main production code was not changed:

- `codex/exp-20261008-component-h01-trace-stream`; final commit `3e2136a2d06c49ae836df241b247da67d2170b33`; worktree `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-component-radical/worktrees/h01-trace-stream`; chat `01a11b9c-a0af-7130-bb63-7e68b61a2609`.
- `codex/exp-20261008-component-h02-parquet-parallel`; final commit `afad1a32ea816e1c1b35bca242acdaa305fdc3ce`; worktree `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-component-radical/worktrees/h02-parquet-parallel`; chat `01a11b9c-a4b4-7bb3-b3c5-53e5cde2d489`.
- `codex/exp-20261008-component-h03-protocol-fusion`; final commit `cc7a4833ef4f8fa4ab1c345f06e589de70d4887f`; worktree `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-component-radical/worktrees/h03-protocol-fusion`; chat `01a11b9c-a7d8-7270-8279-b9a0af98c57f`.

The cached baseline image was built at `286ae974`; its production sources were independently verified identical to the comparison checkout `33027d74`. The runner legacy `baseline_image_source_commit` field records the comparison checkout; the precise image origin is preserved in the frozen plan, baseline audit and summary.json here.

Reproduction and provenance: [frozen plan](plan.json), [baseline audit](baseline-audit.json), [corpus preflight](corpus-preflight.json), [primary runner](run_focused.py). Full raw evidence is preserved below each hypothesis directory; large closed journal payloads are hardlinked to save disk space. Text reports and tools are copied independently.
