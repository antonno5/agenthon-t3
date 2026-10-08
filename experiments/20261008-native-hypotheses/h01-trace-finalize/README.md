Executive summary: this experiment removes two temporary structures used to finish a simulation trace. Quote updates keep their original ordering and their last value at each time, while order events retain the existing sorting and fill rules. Host and pinned native correctness checks passed. Median complete Docker time fell 11.14% for deep-book and 3.78% for partial-fill; cancel-churn rose 1.57%. All five paired samples remain archived and the candidate remains experimental.

Only `baselines/native/engine.cpp` changes in production sources. Quote deduplication now uses two positions for the current timestamp instead of a hash map. Its compact temporary quote vector stores `QuoteLog` rather than full order rows. The merge writes each row directly into the final seven `TraceColumns` arrays, removing `vector<Row> all`. `log_best`, simulation behavior, the existing `stable_sort`, last-execution classification, the message ledger, and the Parquet writer are unchanged.

An absent side emits nothing. If it returns in the same timestamp, its latest price and quantity replace the row at its first position. If it disappears for the rest of that timestamp, its last observed row remains. A new timestamp clears both positions. Quotes retain first-appearance order even when the ask appears before the bid, and precede orders with the same timestamp. Decreasing quote timestamps are rejected before merging.

Run host checks from this worktree:

```sh
python3 expirements/20261008-native-hypotheses/h01-trace-finalize/check_host.py
```

The checker extracts `Sim::extract()` from this checkout and from base commit `ebb266470bee09a426df85d0b2c342b4854b7082`; it compiles those actual methods with fixture state. It asserts the simulation prefix, including `log_best`, sorting and fill classification, is unchanged. Explicit fixtures cover side disappearance/reappearance, several updates at one timestamp, ask-first ordering, empty timestamps, quote/order ties, partial fills, empty inputs, order-only inputs, and ledger preservation. Another 2000 deterministic cases include a 100000-quote / 20000-order case. All trace and message columns are compared in optimized and AddressSanitizer/UBSan builds. The complete candidate `engine.cpp` also passes host C++17 syntax checking. Raw generated code, binaries and compiler output are under `out/h01-trace-finalize/host`, which is ignored by Git.

After an explicit Phase 2 grant, the recipe was executed under the campaign's exclusive Docker slot at the frozen measured commit. The recorded invocation was:

```sh
H01_DOCKER_GRANTED=1 \
  '/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-native-hypotheses/docker_slot.py' -- \
  bash expirements/20261008-native-hypotheses/h01-trace-finalize/docker_recipe.sh
```

The archived recipe expects the frozen measured checkout and a fresh evidence destination. This record is not an authorization for another run. The recipe reads the frozen implementation commit from `READY-h01-trace-finalize.json`, checks the checkout, verifies the production image ID, and builds through the shared campaign Dockerfile. Both images must import the native extension in Python 3.11.17 / Arrow 15.0.2. Measurements use immutable image IDs, Linux amd64, context `colima-agenthon`, 4 CPUs, 16 GiB memory and swap limit, and no runtime network. The shared `run_focused.py` imports the existing differential checker and developer scorer rather than copying either.

Only these assigned units are run:

- `t3-mr-deep-book-state-size`
- `t3-mp05-cancel-churn-newest`
- `t3-s012-partial-fill-cancel-race`

Each unit gets one excluded warmup per side and five fresh AB/BA pairs in order AB, BA, AB, BA, AB. Every output must declare actual native execution and matching file hashes, pass shared developer gates, and match both journals in bytes, schema and ordered values. Keep all samples and outliers. Primary timing is the complete Docker lifetime; core plus finalization, Parquet write and hashing are secondary diagnostics. Record correctness failure separately from a correct candidate that is slower. Store large evidence under `out/h01-trace-finalize/docker`; compact results and separate host/pinned correctness evidence are archived here. Do not tune this candidate after observing times.

These checks are local developer evidence and are not rankable. Host extraction tests cannot establish full simulation correctness, pinned-runtime Parquet equality or a full-container improvement. Historical Python experiments are motivation only; current native baseline runs are the control. No full71 run, production adoption, merge, cherry-pick or push is part of this experiment.

Measured results use the complete Docker clock. The candidate is correct on all assigned units, with mixed performance.

| Unit | Baseline median (s) | Candidate median (s) | Candidate time change | Faster pairs |
|---|---:|---:|---:|---:|
| [t3-mr-deep-book-state-size](../../../units/t3-mr-deep-book-state-size/scenario.json) | 0.651054 | 0.578534 | -11.14% | 4/5 |
| [t3-mp05-cancel-churn-newest](../../../units/t3-mp05-cancel-churn-newest/scenario.json) | 0.476838 | 0.484320 | +1.57% | 3/5 |
| [t3-s012-partial-fill-cancel-race](../../../units/t3-s012-partial-fill-cancel-race/scenario.json) | 0.459450 | 0.442077 | -3.78% | 3/5 |

The full [result.json](result.json) retains every primary and secondary sample. [host_checks.json](host_checks.json) records optimized and ASan/UBSan checks against actual base extraction; [pinned_correctness.json](pinned_correctness.json) records both runtime probes, 36 accepted outputs and all 48 exact pair/repeat comparisons. No failed Docker outputs occurred. One preflight failed before Docker because the interpreter path was unquoted; the fixed recipe commit was frozen before measurements and the failed log remains in `out/h01-trace-finalize/phase2-attempt01.log`. The original implementation is `0ca20940c509b23a4ecae062da7546f24fb49394`; the measured candidate commit is `5ed05198f536c4c3f8e1577312491a1c36c275ad`, which only adds the recipe quoting fix. Production source hashes did not change during measurement.

The secondary core-plus-finalization medians fell for all three units, while complete container medians show a slower cancel-churn result. These phase measurements do not convert that complete-container slowdown into a win. The candidate partial-fill sample of 0.675457859 seconds and every other outlier are retained. Container startup, writing and emulation contribute noise at these subsecond durations. No universal or official speedup is claimed.
