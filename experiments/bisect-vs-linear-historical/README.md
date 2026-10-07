# Historical linear-search / bisect timing estimate

## Executive summary

Existing saved runs allow an approximate before/after comparison on five byte-identical scenarios. The linear-search base has one sample per scenario and bisect has five samples from a separate schedule. Results are mixed and cannot establish a causal overall speedup.

This is an estimate from existing evidence, not a new paired benchmark.
The old sample is a single observation, not an average of repeats.
No overall engine or startup speedup is established.

## Saved evidence and metric

The shared stage-3 image uses linear price search; the adopted image uses bisect.
Saved installed-source audits differ only in `matching/state.py` and
`matching/price_level.py`. Other audited engine and adapter Python files match.
The five retained scenario configs are byte-identical across the old regression,
current public units and the bisect timing inputs. Event/message counts and
trace digest declarations agree across all five bisect timing repetitions.

The metric is the adapter-reported simulation phase in seconds. It excludes
process startup, input/configuration and output writing. The old 65-scenario
regression has one execution per scenario; the bisect/hybrid comparison supplies
five measured bisect repetitions per retained scenario. Warmups are excluded.

## Approximate comparison

Positive time change means slower bisect. All old/new samples and artifact hashes
are retained in `result.json`.

| Scenario | Linear: one run, s | Bisect: mean of five, s | Time change | Bisect median, s | Bisect range, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Price-time priority | 0.062805 | 0.060417 | -3.80% | 0.059749 | 0.057930–0.063121 |
| STP newest | 3.200421 | 3.136094 | -2.01% | 2.885936 | 2.740550–4.231637 |
| STP oldest | 2.632839 | 2.957181 | +12.32% | 2.830096 | 2.576993–3.689906 |
| Deep-book state size | 19.992362 | 20.381540 | +1.95% | 20.313315 | 14.395369–24.355023 |
| Cancel churn | 9.555973 | 8.460581 | -11.46% | 8.320277 | 8.201070–9.137504 |

Cancel churn shows about 11.5% less mean simulation time; STP oldest shows about
12.3% more. Other mean changes are small. Deep-book bisect samples range from
14.4 to 24.4 seconds, demonstrating substantial local timing variation. Separate
schedules and only one old observation prevent attributing these changes to the
algorithm alone. There is no aggregate speedup claim.

Batch is omitted: the saved stage-3 regression ran single scenarios, not the
four-scenario batch. Its single runs cannot be substituted for a batch timing.
Full-container and process-startup comparisons are unavailable in this historical
dataset.

## Reproduction

Regenerate from saved local evidence with
`python3 out/bisect-vs-linear-20261007/historical_compare.py` after selecting a fresh
report output directory. The script verifies input bytes, event counts, digest
declarations and all measured sample values without launching any containers.

The newly started paired experiment was interrupted after the user requested
comparison of existing timings. Its incomplete results are kept separately in
`out/bisect-vs-linear-20261007/` and are excluded from this report.

Local VM/emulation results are non-rankable and do not establish official Final
performance or statistical significance.
