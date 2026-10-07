# Order snapshot experiment

## Executive summary

Orders are copied before market updates and message deliveries so that later changes cannot rewrite earlier snapshots. Exact events and message traces passed on six representative units, fourteen installed runtime checks passed, and the parent executed a fresh 65/65 regression. Do not adopt: the preregistered full-container performance criterion failed. All evidence remains local and non-rankable.

The parent independently reconstructed all 52 installed Python source files and checked every paired event/message file for byte, schema and ordered-value equality. Container starts and deaths showed no overlapping runs. Its `manager-audit.json` recomputed the medians from Docker State; warmup and profile runs are excluded.

| Unit | Baseline seconds | Candidate seconds | Time reduction | Ranges overlap |
|---|---:|---:|---:|---|
| t3-s001-price-time-priority | 1.517524 | 1.698294 | -11.91% | False |
| t3-cancelmodify-lifecycle | 9.622411 | 9.873582 | -2.61% | True |
| t3-mp01-stp-newest-baseline | 4.440639 | 4.621157 | -4.07% | True |
| t3-mp02-stp-oldest-baseline | 4.426207 | 4.488563 | -1.41% | True |
| t3-mr-cancel-replace-churn | 17.193348 | 16.919898 | +1.59% | True |
| t3-mp07-heavy-flow-oldest | 6.302813 | 5.057676 | +19.76% | False |

Adoption requires at least 5% lower median container lifetime on both primary units (cancel/replace churn and heavy-flow STP oldest), and no unit more than 5% slower. All raw AB/BA/AB pairs and ranges are retained in `result.json` and `evidence/manager-validation.json`. With three pairs and overlapping observed ranges, these local measurements do not establish official timing or statistical significance.

Heavy-flow STP oldest improved by 19.76% with separated observed ranges, while primary churn improved only 1.59% with overlapping ranges. S001 slowed by 11.91%, also with separated observed ranges. The positive heavy-flow result is workload-specific evidence; both the every-primary threshold and regression guardrail fail.

Actual Python 3.11 container component diagnostics are in `evidence/container-component-benchmark.json`. They separate field copying from the PTC redundant-copy ablation and retain all seven samples. Component changes do not substitute for the full-container criterion. The container source paths resolve through host files and exact hashes in `evidence/container-source-mappings.json`, including root `baseline-image-source/abides_markets/{orders,order_book}.py` for `/opt/order-copy-baseline/`.

## Scope and correctness

The independent branch starts at `0af6939d8815b9e39376e5c6f7fef3538cec06f1`.
It changes only `orders.py` and the PTC copy callsite/import in `order_book.py`, copied into the
installed ABIDES package by an overlay on `hotpaths-base:20261006`. It includes
the shared Python reducer and no book indexes or other new hypothesis.

Upstream already uses specialized constructor-based `__deepcopy__`, rather than
generic Python object traversal. Its non-tag fields are assigned directly; only
`tag` is deep-copied. The fast path uses exact `LimitOrder` or `MarketOrder`, the
unchanged ordered core-field key tuple, a non-None order ID, and an exact immutable tag type. It
allocates with `object.__new__` and copies the field dictionary. Mutable non-tag
core fields retain exactly upstream's assignment aliases. Neither constructors,
new order IDs nor RNG run in this path.

Unknown attributes, key order, mutable tags, atomic subclasses and order
subclasses retain the original constructor method body as fallback. This does
not fix upstream's existing limitations: custom attributes/subtypes are dropped,
tag copies do not share the outer deepcopy memo, and a tag referencing its order
can raise `RecursionError`. Cycles wholly inside a tag still work. Tests explicitly
check these limits, shared aliases, memo prefill, repeated graph references,
mutable tags, slots, extension fields and immutable execution snapshots.

Price-to-comply entry normally copies once in `handle_limit_order`, then twice
in `enter_order`. Only a fast-path-eligible order skips the first copy. The hidden
and visible halves still own independent order dictionaries and link through
`ptc_other_half` metadata. Acceptance still refers to the original incoming order,
as upstream does. A mutable or custom tag keeps all three copies; the test counts
its hooks and verifies no snapshot side effects are removed.

## Evidence and manager commands

`build-plan.json` declares absolute Dockerfile/context paths, six representative
units, two primary timing units and the exact container runtime check argv.
The manager owns Docker builds and every container launch. The two runtime
commands execute installed candidate files, whose hashes must match
`overlay-sha256.json`; saved baseline files must match `evidence/source-hashes.json`.
Both test and benchmark outputs identify actual source paths and SHA-256 hashes.

`checks.py` uses standard-library unittest; no runtime dependency is added.
`benchmark.py` retains seven raw samples per operation, separating copyfields
from the redundant PTC copy ablation. The PTC baseline book deliberately uses
candidate order classes to isolate that one removed copy. These component
measurements cannot establish simulator speedup.

Host-only evidence is in `evidence/host-tests.log` and
`evidence/host-component-benchmark.json`, using Python 3.13 ARM64 rather than the
container's Python 3.11/Rosetta. `rejected-atomic-scan-host-benchmark.json` retains
the first prototype that checked every field's immutable type: this redundant
scan was slower than the original constructors and was rejected. The upstream
assignment semantics justify checking only the copied tag.

Preliminary adoption requires at least 5% lower median container lifetime on both
primary units (cancel/replace churn and heavy-flow STP oldest), exact ordered
event and message files and unchanged developer gates, plus regression65 and no
more than 5% slowdown in any representative unit. Parent evidence retains
warmup, unprofiled AB/BA repeats and diagnostic profiles separately. Local
Mac/Rosetta measurements remain `rankable=false`.

## Completed parent evidence

The immutable original candidate is `sha256:90b476d68556c698e6c93bfa1d2e801e84a8d2ad9cb5ca9e00111bf1d1d05024`; measured candidate contract control is `sha256:d9247b2cca1f1213e2c94a9c6ed403e35e4c217024c8fd28df25ec27a77b80db`. Original baseline is `sha256:7097baadcc6b889cdc539aa8e2afbafbb5a1da7724428c93b6d334b4528a3767`; measured baseline contract control is `sha256:443d01e90bf00ff92f77d71bf672fc2a032b7df401647ac694267e8107da5d40`. Both control images apply the same serial batch wrapper that removes only prohibited root `profile.json`; all selected timing units are single simulations. Regression65 ran the original candidate, not reused evidence. `evidence/manager-validation.json` binds commands, runtime checks, source audits, Docker event audit, differential summary and regression report by SHA-256. All original raw outputs remain at `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/order-copy`.
