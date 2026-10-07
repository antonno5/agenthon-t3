# Best-price path and maintained numeric price vector

## Executive summary

Results are mixed: historical median container-time changes are t3-mp02-stp-oldest-baseline: -14.5%, t3-mr-deep-book-state-size: -18.4%, t3-mp05-cancel-churn-newest: +11.8%. Negative means less time. Only the new candidate was run; separate measurement schedules prevent a causal speedup claim. The user selected the measured implementation for codex/develop.

The candidate passed 133 order-book checks, all 18 selected simulator runs,
33 exact journal/stability comparisons and 210 synthetic domain comparisons.
The measured implementation was adopted in codex/develop at the user's request.
The existing submission archive still refers to the previous bisect image.

## Implementation

Only the installed `matching/state.py` differs from the measured bisect image.
A private numeric key vector stores ascending asks and negated bids. Search
returns position zero immediately when the target is at or ahead of the best
price; otherwise `bisect_left` reads integers without a Python key callback.
Normal insert/delete/pop operations update the vector with the level list.
Public reorderings and price edits rebuild once before reuse; unsupported
levels and plain replacement lists retain the original traversal.
Pickle/deepcopy reconstruction detects incomplete list restoration before
incremental updates. FIFO queues, matching rules and callbacks are unchanged.

The Docker overlay inherits the measured bisect runtime, checks the original
module SHA-256 before replacing it, verifies the replacement and precompiles
its bytecode. Installed-source auditing verifies that only that module changed.

## Measurement scope

Only the candidate is run. Baseline times come from the prior frozen
bisect/hybrid comparison. Each selected public unit has one excluded warmup
and five measured candidate repetitions. The unchanged synthetic benchmark
runs seven candidate repetitions, at six depths and five operation workloads,
with 200 excluded warmup operations and 2,000 measured operations per case.
Existing-level cases retain levels; new-level churn creates and deletes one
level per operation. These exercise different mutation intensities.

All containers use colima-agenthon, linux/amd64, four CPUs, 16 GiB and no
network, sequentially. No baseline timing container or full corpus regression
is launched. Only the targeted order-book suite and three public units run.

## Full simulator results

Medians in seconds. Positive reduction means less time. These are historical
estimates, not paired causal speedups. Every sample, mean and range is in
`result.json`.

| Unit | Container: bisect | Container: vector | Reduction | Simulation: bisect | Simulation: vector | Reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| STP oldest | 4.616 | 3.947 | +14.5% | 2.830 | 2.529 | +10.6% |
| Deep-book state size | 23.608 | 19.270 | +18.4% | 20.313 | 17.080 | +15.9% |
| Cancel churn | 10.253 | 11.466 | -11.8% | 8.320 | 9.392 | -12.9% |

## Synthetic operation results

Medians in microseconds per operation. Initialization and warmup are
excluded; mutation and key-vector maintenance are timed. Operation timings
are not full simulator speedups.

| Levels | Operation | Bisect, µs | Vector, µs | Reduction |
| ---: | --- | ---: | ---: | ---: |
| 1 | lookup | 1.430 | 1.251 | +12.5% |
| 1 | add_existing | 1.973 | 1.828 | +7.3% |
| 1 | cancel_existing | 2.961 | 2.801 | +5.4% |
| 1 | modify_existing | 4.454 | 4.314 | +3.1% |
| 1 | new_level_churn | 7.167 | 7.223 | -0.8% |
| 4 | lookup | 2.157 | 1.628 | +24.5% |
| 4 | add_existing | 2.208 | 1.717 | +22.2% |
| 4 | cancel_existing | 3.221 | 2.901 | +9.9% |
| 4 | modify_existing | 5.007 | 4.671 | +6.7% |
| 4 | new_level_churn | 9.017 | 7.998 | +11.3% |
| 16 | lookup | 2.571 | 1.770 | +31.1% |
| 16 | add_existing | 2.638 | 1.819 | +31.0% |
| 16 | cancel_existing | 3.633 | 2.795 | +23.1% |
| 16 | modify_existing | 5.526 | 4.874 | +11.8% |
| 16 | new_level_churn | 10.806 | 8.123 | +24.8% |
| 64 | lookup | 3.072 | 1.823 | +40.7% |
| 64 | add_existing | 3.320 | 1.831 | +44.9% |
| 64 | cancel_existing | 4.161 | 2.876 | +30.9% |
| 64 | modify_existing | 6.009 | 4.700 | +21.8% |
| 64 | new_level_churn | 10.986 | 8.207 | +25.3% |
| 256 | lookup | 3.546 | 1.863 | +47.5% |
| 256 | add_existing | 3.858 | 2.102 | +45.5% |
| 256 | cancel_existing | 4.731 | 2.945 | +37.7% |
| 256 | modify_existing | 7.071 | 4.944 | +30.1% |
| 256 | new_level_churn | 12.929 | 8.410 | +34.9% |
| 1024 | lookup | 4.492 | 2.072 | +53.9% |
| 1024 | add_existing | 4.715 | 2.244 | +52.4% |
| 1024 | cancel_existing | 5.586 | 3.133 | +43.9% |
| 1024 | modify_existing | 8.042 | 5.290 | +34.2% |
| 1024 | new_level_churn | 14.985 | 9.174 | +38.8% |

## Reproduction and limitations

Build with `docker --context colima-agenthon build --platform=linux/amd64
--network=none -t python-book-price-vector:20261007 experiments/price-vector`.
Run the candidate-only coordinator with `.venv/bin/python
experiments/price-vector/run_experiment.py --out out/price-vector-new`.
It requires a fresh output directory and checks source/evidence hashes.
Regenerate this report using `.venv/bin/python experiments/price-vector/summarize.py`.
Pass `--out out/price-vector-new` when summarizing a new local run.

The first runtime attempt caught one deepcopy key duplication error. The
fix was tested before any timings; the failed source and log are retained
under `out/price-vector-20261007/attempt-1/`. Final results use only the fixed
candidate image.

Separate schedules, local VM/emulation and prior VM recovery prevent a
statistical or causal performance claim. Stored key vectors consume extra
memory and require a second list shift on new-level changes. Arbitrary
explicit base-list mutation and writes through vars(level) retain the
existing compatibility limits. No submission is rebuilt or published.
