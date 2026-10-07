# Optional SciPy cold import

Executive summary: every public scenario already specifies its message latency
model. The simulator nevertheless imports SciPy's distance routines before the
process can run; those routines serve only the alternative line-distance latency
model. This experiment loads those routines when that alternative actually needs
them. It preserves the same arithmetic, random draws and explicit utility exports.
The candidate passes all selected exact-output checks and all 65 public regressions. The two declared primary workloads have 20.23% and 10.69% lower median full-container lifetime; every selected median slowdown is below 5%. The preregistered local criterion passes. This is local Mac/Rosetta evidence, `rankable=false`, and requires Linux confirmation. Three noisy pairs do not establish a general simulator gain.

The branch starts from `0af6939d8815b9e39376e5c6f7fef3538cec06f1`.
The exact installed utility source comes from the manager's immutable snapshot;
`source-binding.json` binds both files by SHA256. `install.py` refuses a different
baseline file. `lazy-distance.patch` is the complete human-reviewable change and
`utils.py` is its resulting runtime file. The image inherits the immutable pinned
adapter and dependencies from `hotpaths-base:20261006`; it changes only this one
upstream utility module. The applicable `AGENTS.md` was read; its referenced
`../../AGENTS.md` is absent.

## Scope and checks

`scipy.spatial.distance` was imported at utility-module scope, despite being used
only by `generate_uniform_random_pairwise_dist_on_line`. The import now resides
inside that function. Module-level `pdist` and `squareform` remain available via
lazy `__getattr__`, with the original SciPy function identities. An explicit `__all__` matches the exact pinned baseline wildcard exports; `from abides_markets.utils import *` requests those optional functions and legitimately loads SciPy. This changes no
scenario configuration, agent registration, counters, RNG seeding/draws, order
processing, log levels, trace schema, dependencies or submission CLI.

The source inventory covers 95 scenario JSON configurations in the frozen 71-unit
snapshot, including batch subs: all have a scenario-specific latency model. An
absent latency configuration remains supported and will load the same SciPy
routines during configuration. NumPy, pandas, the actual simulation imports and
initialization remain mandatory; their costs have not been moved behind the
adapter clock to manufacture a smaller startup residual.

Four host tests verify the source binding, no eager SciPy load and exact fallback
distances plus RandomState progress over three seeds and four cardinalities,
including empty/singleton inputs. They also compare actual wildcard imports with the immutable baseline and verify preserved exports and unknown
attribute errors. The host checker is Python 3.13 with newer packages; these are
only diagnostic checks. `runtime_check.py` repeats the semantic checks using the
actual pinned Python 3.11 candidate image and proves the real adapter import has
not loaded SciPy. Its JSON records versions and the installed source SHA.

## Manager reproduction

Docker belongs exclusively to the manager; this agent runs no Docker commands.
`build-plan.json` contains absolute paths, image name, units, primary units, runtime
checks and the exact import/init probe command. Build from this worktree:

```sh
docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE=hotpaths-base:20261006 \
  -f experiments/startup/Dockerfile -t hotpaths-startup:20261006 .
docker --context colima-agenthon run --rm --network none --cpus 4 \
  --memory 16g --memory-swap 16g hotpaths-startup:20261006 \
  python /opt/startup-experiment/runtime_check.py
```

The full differential campaign must use frozen images and the frozen public-unit
snapshot, one warmup pair, three AB/BA/AB unprofiled pairs and a separate component
profile pair on these five units:

- `t3-s001-price-time-priority` and `t3-s012-partial-fill-cancel-race` (primary)
- `t3-as05-oracle-variant` and `t3-momentum-mix-priority`
- `t3-gbatch-homog-4`

Require complete exact ordered traces, schemas and SHA equality for both event and
message traces, all unchanged developer gates, C3 retention, digest audits and
all per-repeat stability checks. The manager also runs regression65. A practical
startup improvement requires at least 5% median full-container run reduction on
the short primary units with correctness passing. Container, host-launch and
adapter clocks remain separate. Do not interpret container lifetime minus adapter
elapsed as isolated startup: it also contains other entrypoint/shutdown work.
No acceleration claim follows from `--help`, which is not the target measured here.

Run the separate diagnostic import/init producer from `build-plan.json` after the
Docker slot is acquired. `run_probes.py` freezes image IDs, retains the commands and
raw stdout/stderr and the actual loaded SciPy modules and utility source SHA. It checks the Docker slot is idle before each launch and invokes a fresh Python process for every sample. Each mode
gets a warmup pair, three AB/BA/AB pairs, and a separate `python -X importtime` pair;
raw importtime stderr is retained and excluded from unprofiled medians. Import
mode times the actual `abides_fork.simulate` module; initialize mode additionally
resets counters and builds s001's real seeded configuration. No process/import
prewarming or subprocess reuse hides full cold costs. Probe clocks are diagnostic;
`host_launch_sec` includes Docker launch overhead and does not isolate startup.
Every run uses four CPUs, 16 GiB memory/swap and network none. This local
Mac/Rosetta experiment remains `rankable=false`.

Host reproduction (does not run Docker):

```sh
PYTHONDONTWRITEBYTECODE=1 \
  '/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
  experiments/startup/test_startup.py
```

`result.json` binds the completed manager campaign and all retained evidence by SHA256. The selected-unit checks plus regression65 do not constitute all71 admission; the other five batch units were not checked for this candidate.


## Completed local evidence

Implementation commit: `a4c207b9bb4fe9e59055ca4075a8220862e792e1`. The manager reconstructed the committed patch against the immutable source and compared all **52 installed Python files byte for byte**. Only `abides_markets/utils/__init__.py` changed. Both lazy explicit exports and the exact 25 baseline wildcard names remain supported. The runtime check also verifies that ordinary adapter import and the no-latency path leave SciPy unloaded, while a genuinely cold fallback after seeding preserves exact distances and both global and latency RNG progress. Four host tests and the pinned-runtime check pass.

The differential campaign has **50 accepted launches**, **25 baseline/candidate pairs**, **65 pair/stability comparisons** and **80 independently audited output-file comparisons**, all matching bytes, schemas and original row/field values in both trace files. Every launch passes the unchanged actual developer gates, C3 retention and digest declarations; a fresh manager output-only gate recheck passes. The raw candidate separately passes regression65 with **65 passed, zero failed, zero errors**. Docker event start/death records independently confirm sequential launches.

| Image role | Immutable image ID |
| --- | --- |
| original_base | `sha256:7097baadcc6b889cdc539aa8e2afbafbb5a1da7724428c93b6d334b4528a3767` |
| raw_candidate | `sha256:63d8b523e6e8d789c404a6c103937d3b7f6cbbbb42b605304f73ddd685c28b44` |
| baseline_control | `sha256:443d01e90bf00ff92f77d71bf672fc2a032b7df401647ac694267e8107da5d40` |
| candidate_control | `sha256:bf8bb95b8f74edd7c82d9ab33408252d38069d733d64d1dea4dd99d9d98f0ac9` |

The full-run comparison uses identical contract wrappers on both sides. Each removes only the forbidden batch-root `profile.json` after successful serial batch execution. The original unwrapped baseline rejection is retained as a contract probe. The simulation, dependencies, scorer and sanitation rules are unchanged. The import/init diagnostics compare the raw base and raw candidate images.

Full Docker State lifetime in seconds, with warmup and profile excluded:

| Unit | Baseline median [min, max] | Candidate median [min, max] | Median reduction | Ranges overlap |
| --- | --- | --- | --- | --- |
| t3-s001-price-time-priority | 1.496511 [1.493027, 1.583657] | 1.193773 [1.166254, 1.268728] | +20.23% | no |
| t3-s012-partial-fill-cancel-race | 10.826948 [10.349197, 14.088473] | 9.669050 [9.566426, 11.381483] | +10.69% | yes |
| t3-as05-oracle-variant | 3.201064 [2.738104, 3.529229] | 2.837091 [2.590056, 3.010304] | +11.37% | yes |
| t3-momentum-mix-priority | 5.237972 [5.168407, 5.592074] | 5.074035 [4.996960, 5.894251] | +3.13% | yes |
| t3-gbatch-homog-4 | 3.720180 [3.147367, 4.636229] | 3.742308 [3.504584, 4.274754] | -0.59% | yes |

The exact raw three pairs and their individual directions are in `result.json` and the manager audit. All s001 and oracle pairs are faster. The third s012 pair is **5.12% slower**, the third momentum pair is **14.04% slower**, and two batch pairs regress (one by **35.82%**). Four of five ranges overlap. The preregistered decision uses medians: at least 5% reduction on every primary (s001 and s012), with at most 5% median slowdown anywhere. It passes, while the inconsistent pairs limit generalization. No extra repeats or favorable timing selection were added.

The independently audited diagnostics retain **20 fresh processes**: four warmups, twelve unprofiled samples and four separate raw importtime samples. Import-only median changes from 1.176358 to 0.940355 seconds; import in the initialization probe changes from 1.215942 to 0.864102 seconds. Configuration initialization changes from 0.011378 to 0.010765 seconds. The candidate leaves SciPy unloaded in all adapter-import and s001-initialization samples; the baseline loads it. These clocks are diagnostic and do not determine admission. `result.json` separately retains host-launch, adapter and mixed residual clocks. The container-minus-adapter residual is not isolated startup.

The as-built `.pyc` inventory records a valid inherited cache for the original utility and no utility cache in the candidate, whose installer deletes that file after replacing its source. Disposable processes include recompilation when needed. This records actual image state and does not attribute observed timings to cache differences or establish steady-state performance. Runtime identity is Python 3.11.17, NumPy 1.26.4, pandas 1.5.3, PyArrow 15.0.2 and SciPy 1.17.1.

The manager retains commands, outputs, failed contract evidence, Docker events, exact trace/gate reports, regression65, source reconstruction and raw importtime stderr under `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/startup`. `result.json` and `evidence/validated-campaign.json` provide explicit file SHA bindings. Final verdict: **`local_gain_supported_requires_linux_confirmation`**. No merge, push, deployment or official timing claim is made.
