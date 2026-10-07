# Python order-book layers

## Executive summary

The existing Python book is split into five modules so that its storage, matching
and queries can be measured and changed independently. Trading rules and list
storage stay the same. The public OrderBook and PriceLevel imports still work.
This is a structural refactor. Functional checks passed; local timing did not
demonstrate a speedup and retained slower STP medians in both schedules.

This report describes frozen stage-1 images. The subsequent [stage-3 refactor](../python-book-stage3/README.md)
intentionally changes mutation bodies; its evidence is recorded separately.

## Structure

The build installs `baselines/matching/` as `abides_markets.matching`:

| Module | Responsibility |
| --- | --- |
| `state.py` | `OrderBookState`: initialize the original public attributes. |
| `price_level.py` | Original `PriceLevel`, with visible and hidden list queues. |
| `matcher.py` | `Matching`: limit/market handling and one execution, including STP and callbacks. |
| `queries.py` | `BookQueries`: L1/L2/L3, history exports, snapshots and formatting. |
| `facade.py` | `OrderBook`: combine the layers and retain lifecycle methods and snapshot recording. |

The facade inherits the state, matching and query methods. There is one book
object and one set of public fields; no delegate objects, forwarding properties,
command DTOs or output buffers are introduced. Calls continue through `self`, so
subclass overrides and existing profiler wrappers continue to participate.
Matching still calls the owning agent at the original points, and snapshots are
still taken between fills. History aliases, order copies and unusual edge cases
are preserved rather than corrected during this extraction.

`baselines/matching_compat/` supplies the original `abides_markets.order_book`
and `abides_markets.price_level` modules. Both old imports and new imports return
the same classes. Canonical class module names are retained for pickle/deepcopy;
the logger name stays `abides_markets.order_book`. Original module exports remain
available. Method implementation modules and the inheritance tree necessarily
change; external code depending on those internals must account for the refactor.

## Build boundary and provenance

`baselines/install_matching.py` runs after the seven existing patches and before
packaging ABIDES in the standard Dockerfile and local install recipe. It requires
the SHA-256 of both exact patched source files. It verifies signatures and bodies
of all 24 OrderBook methods through AST comparison, verifies the complete
PriceLevel class, and compiles every overlay module before replacing files.
A changed source, missing/duplicated/changed method or invalid Python is refused.
Installation requires a fresh baseline, preventing accidental repeated overlays.

Source pin: `f9cbe51342b7dedd9587e4e069040d68a5c6477f`. The extracted code retains
the upstream BSD 3-Clause notice in `baselines/matching/LICENSE.abides`; Docker
also ships it at `/opt/licenses/abides-matching-LICENSE`.

## Validation method

Repository installer tests are hermetic and verify refusal before mutation. Real
engine tests in `test_runtime.py` run in the Python 3.11 candidate container with
read-only pytest tooling and the independently reconstructed original source.
They check imports, pickle/deepcopy, subclass dispatch, direct public list
assignment, visible/hidden priority and callback snapshots between partial fills.
Nine seeded streams compare both implementations after each of 300 operations:
add, market, cancel, modify, partial cancel and replace, including duplicate IDs,
PTC links, quiet calls, wrong-price cancellation and all three STP settings.
Messages, global message-counter progress, callback order, state, history,
snapshots and PTC reference topology are compared. Original exceptions are
compared too; an equally failing operation is not reported as successful trading.
The 43 pinned upstream order-book tests run alongside these checks.

The control and candidate standard Docker builds use frozen contexts with equal
adapters and the seven existing patches. Preexisting batch adapter edits are
identical in both; they are not part of this refactor. The manifest records the
base commit, dirty status and every build-context file hash. Exact dual-trace
checks and real developer gates use the unchanged differential runner; public
regression uses the unchanged standard harness. Timing runs are sequential,
separate from diagnostics, and local/non-rankable (Mac ARM64, linux/amd64 Rosetta).

## Validation results

The repository suite passed **383 tests** (one existing filesystem skip, 38
integration tests deselected, two subtests passed). The real Python 3.11 engine
suite passed **56 tests**: 43 upstream tests and 13 custom tests, including
2,700 operation-by-operation comparisons. All 71 public corpus units passed
schema/track/split/canary/manifest/firewall validation. The standard public
regression passed **65/65 scenarios**; that harness checks traces and does not
check all message journals.

Both unchanged differential schedules passed every developer gate and exact
byte/schema/ordered comparisons of both `trace.parquet` and
`message_trace.parquet` on price/time priority, STP-newest, STP-oldest and the
homogeneous four-simulation batch (including batch subunits). The first schedule
contains 40 container runs: warmups, three measured pairs per unit and separate
profiles. The fixed confirmation contains 48 runs: warmups and five measured
pairs per unit, without diagnostic profiles. No code changed between schedules.
Installed-source auditing found only the six new modules and two compatibility
modules changed; every other engine and adapter Python source was identical.

Local median full-container times (positive change means slower candidate):

| Scenario | Initial control / candidate, s | Change | Confirmation control / candidate, s | Change |
| --- | ---: | ---: | ---: | ---: |
| Price/time priority | 1.234 / 1.244 | +0.81% | 1.291 / 1.289 | -0.20% |
| STP cancel newest | 3.948 / 4.451 | +12.73% | 4.488 / 5.055 | +12.64% |
| STP cancel oldest | 3.968 / 4.094 | +3.19% | 3.905 / 4.247 | +8.75% |
| Batch, four simulations | 2.559 / 2.743 | +7.18% | 3.670 / 2.992 | -18.49% |

**No speedup is demonstrated.** STP medians are slower in both schedules;
other results vary substantially between schedules. This local Rosetta setup
and the small sample do not establish a causal or statistically significant
overhead. The risk remains open; the extraction is accepted for structure and
tested compatibility, not for improved latency. A next optimization should
measure the matching hot path separately before changing storage or dispatch.

Machine-readable results, raw timing samples, source/image identities and
artifact digests are in [`result.json`](result.json). Frozen contexts, manifests,
logs, traces and full summaries remain in `out/python-book-layers/` (ignored
local evidence). No sealed or official rankable evaluation was used.

## Reproduce

Use the standard `baselines/Dockerfile` for the layered image. The original control
context is retained at `out/python-book-layers/control-context`; its only code
differences from the candidate context are the layer installation and modules.
Image IDs, context hashes and dirty-source provenance are in the source manifest
and differential summary. Use new output directories for reruns.

For runtime tests, prepare an independent pinned checkout with the seven patches
but without `install_matching.py`. Mount its `abides_markets` directory as
`/control-source` and its sibling `tests` as `/upstream/tests`. Read-only pure
Python pytest tooling is mounted as `/tooling` (pytest, _pytest, pluggy,
iniconfig, packaging, pygments and the `py.py` shim); it must support Python 3.11.
Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`PYTHONPATH=/tooling:/upstream:/runtime_tests`, and
`BOOK_LAYERS_CONTROL_SOURCE=/control-source`. Mount this experiment directory as
`/runtime_tests` and run:

```sh
python -m pytest /upstream/tests/orderbook /runtime_tests/test_runtime.py /runtime_tests/test_price_vector.py /runtime_tests/test_price_offset.py -q -o addopts=
```

The repository checks and actual differential command are:

```sh
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
PYTHONPATH=. .venv/bin/python scripts/run_differential_experiment.py run \
  --baseline-image python-book-layers-control:20261006 \
  --candidate-image python-book-layers:20261006 \
  --baseline-commit '<base-source-revision>' \
  --candidate-commit '<candidate-revision-and-working-tree-manifest>' \
  --units t3-s001-price-time-priority t3-mp01-stp-newest-baseline \
    t3-mp02-stp-oldest-baseline t3-gbatch-homog-4 \
  --repeats 3 --out out/python-book-layers-new/differential
```

All Docker commands must use the `colima-agenthon` context and run sequentially.
The unchanged standard regression harness uses a local Docker executable shim
that prefixes every invocation, including timeout cleanup, with
`--context colima-agenthon`; it does not change the user's global Docker context.

## Numeric price-vector integration

On 7 October 2026 the user selected the measured best-price fast path and
maintained numeric keys for `codex/develop`. That integration was byte-identical
to the candidate in `../price-vector/`; its 133 order-book checks and exact
journals on three selected units are reused. The additional vector checks are
retained in `test_price_vector.py`. No scenario is rerun solely for integration.
The earlier stage-1 results above remain historical and are not a timing claim
for subsequent implementations. The price-vector report retains the mixed
performance results, including slower cancel churn.

## Price-key offset integration

The user then selected the measured offset implementation for `codex/develop`.
The current `baselines/matching/state.py` is byte-identical to
`../price-offset/state.py`. Its 146 order-book checks, 18 selected simulator runs,
33 exact journal/stability comparisons and 210 synthetic domain comparisons are
reused. `test_price_vector.py` checks the active key slice and
`test_price_offset.py` retains the compaction, reuse and memory-bound checks.
Fresh installation is checked through the guarded standard installer; no
simulation or timing run is repeated solely for integration. See the
[offset report](../price-offset/README.md) and
[integration record](../price-offset/integration.json). The observed historical
time reductions do not establish a repeatable gain from the offset alone.
