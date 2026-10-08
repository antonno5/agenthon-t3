Executive summary: All four assigned public units passed pinned native correctness. Median complete Docker time improved 14.89% for cancelmodify and 2.06% for price-time-priority, and regressed 1.17% for deep-book and 9.41% for partial-fill/cancel-race. All five pairs and outliers are retained; this is local, non-rankable evidence.

# h02: time groups

Only `baselines/native/engine.cpp` changes production behavior. Four kernel lifecycle logging sites append compact rows and retain the original log owner and append sequence. Extraction sorts each timestamp group by `(order_id, log_owner, log_sequence)`, reproducing the former stable sort of concatenated agent logs. A timestamp map regroups rare nonmonotonic lifecycle input, permitted by negative latency, before the same group sorts.

The last-execution classification pass, quote extraction/deduplication/merge, intermediate `all` vector, column emission, matching state and message ledger retain their existing behavior. No h01 change is adopted. Ordinary chronological input uses `O(N + sum(k_t log(k_t)))` work; one giant timestamp group still needs a full-sized sort, and tie provenance increases temporary-row storage.

## Complete Docker measurements

Each row compares the median of five complete container lifetimes. Negative change means less time; positive change means more time. Every baseline is a fresh run. No outliers are discarded.

| Assigned public unit | Baseline median (s) | Candidate median (s) | Time change | Faster pairs | Outcome |
|---|---:|---:|---:|---:|---|
| t3-mr-deep-book-state-size | 0.567585 | 0.574227 | +1.17% | 2/5 | correct-but-slower |
| t3-cancelmodify-lifecycle | 0.469391 | 0.399513 | -14.89% | 5/5 | correct-but-faster |
| t3-s012-partial-fill-cancel-race | 0.421060 | 0.460693 | +9.41% | 1/5 | correct-but-slower |
| t3-s001-price-time-priority | 0.267087 | 0.261584 | -2.06% | 4/5 | correct-but-faster |

All forty timed samples, twenty pair changes, configuration/core/write/hash samples and their medians are archived in `result.json`. The complete-container outcome is mixed. In particular, correctness passing does not turn the slower deep-book or partial-fill runs into wins.

## Secondary phase diagnostics

Native core here includes simulation and trace finalization. It is not a matcher-only or isolated sort measurement; serialization, hashing and startup variation also affect the primary result.

| Assigned public unit | Core baseline median (s) | Core candidate median (s) | Core time change |
|---|---:|---:|---:|
| t3-mr-deep-book-state-size | 0.134793 | 0.127363 | -5.51% |
| t3-cancelmodify-lifecycle | 0.059994 | 0.053859 | -10.23% |
| t3-s012-partial-fill-cancel-race | 0.062811 | 0.062741 | -0.11% |
| t3-s001-price-time-priority | 0.003694 | 0.003801 | +2.87% |

These local phase differences cannot attribute the full Docker change to grouped sorting. For example, partial-fill core medians are nearly identical while its complete container median regresses. Price-time-priority has a slightly slower core median despite a shorter full container median. No aggregate or uniform speedup is claimed.

## Correctness and provenance

- Host checks: focused submitted/accepted/executed/cancelled ties, final partial-fill labels, absent fill-price fallback, different log owner/emitted agent ids, quote last-row deduplication and merge, empty inputs, and 512 histories totaling 1,024,000 rows. A further 144 complete native simulations across twelve seeds, four latency models and three STP modes match unchanged source in every trace and message-ledger array. All four assigned-unit manifests and shared public-firewall checks pass.
- Pinned standalone checks repeat those assertions inside the Linux amd64 builder and assert Python 3.11.17 / Arrow 15.0.2. Eight separate pre-timing outputs across the four assigned public units pass native provenance, shared developer gates, reference equality, declared digest checks and four baseline/candidate exact comparisons.
- The timed schedule retains 48 accepted outputs: eight excluded warmups and forty timed samples. All 64 comparisons require exact bytes, schema and ordered values for both journals. The shared developer scorer and differential checker are imported, never copied; every retained output passes the developer gates. Actual engine is native for every output; fallback is rejected.
- Two recipe failures occurred before timing: Dockerfile `FROM` resolved a bare image ID as a remote tag, then diagnostics tried to call a function imported locally inside the shared runner. Only diagnostic tooling changed. Failed attempt logs and READY metadata remain retained; native sources and the implementation commit never changed.

Frozen implementation commit: `f828ef6b307b6e6f651e33b2a03beadf8fb77b5e`. Source base: `ebb266470bee09a426df85d0b2c342b4854b7082`. The immutable production image was built from source commit `7a5abca889c1fdd77e01edfa9f85762becc1f17b`; this distinction is retained in the report.

Baseline image: `sha256:e7f01b18f284f8ff9a5e0fb5591a80dfdaa9e051f76e7076e07ae82293aedd89`. Candidate image: `sha256:27ac770384b308a0f61f2ae8c29dcf90d37457b6d372470c9597645f42cbf828`. Full source SHA256 maps and runtime versions are archived in the report. Sources remained unchanged through timing.

## Archived execution recipe

The measured run used the common campaign `Dockerfile`, `run_focused.py` and `docker_slot.py`. `phase2.py` builds and checks the candidate, imports shared staging/validation helpers for separate correctness outputs, then invokes the common measurement runner unchanged. It asserts that the local baseline build tag resolves exactly to the immutable baseline ID. Measurements use only immutable IDs.

The recipe ran under one exclusive campaign slot, with Linux amd64, context `colima-agenthon`, 4 CPUs, 16g memory and memory-swap, network none, one excluded warmup per side and five pairs in AB/BA/AB/BA/AB order. Primary time is `Docker State FinishedAt - StartedAt`; configuration, simulation plus trace finalization, Parquet writing and hashing are secondary diagnostics. Source Python paths containing spaces are quoted.

The successful slot returned and no Docker operation followed its release. Raw Parquet and logs remain ignored under `out/h02-time-groups/phase2-attempt03`; compact `host_checks.json`, `pinned_correctness.json`, `result.json` and this report are committed. Earlier attempts remain under `phase2` and `phase2-attempt02`. This archived recipe is not authorization for another run.

These are local developer results on a Mac ARM64 host running emulated Linux amd64 containers. They are not official timing evidence (`rankable: false`). Historical Python measurements are motivation only. No performance scope expansion, full71 regression, source tuning after timing, selective rerun, merge, cherry-pick, push or production adoption occurred.
