Executive summary: develop now combines the previously tested Parquet encoding
policy (H1) with the standalone native single-scenario executable (H2). Local
mapping and synthetic journal checks passed. No Docker build, Docker test run or
timing series was performed for this integration, as requested. The combined
speedup and complete-container behavior remain unmeasured.

## Applied changes

Base: `e743dc8` on `codex/develop`.

- H1 writer sources are byte-identical to measured revision `fc1fff3`: Snappy,
  dictionary only for `msg_type` and `side`, no column statistics. Decoded schemas,
  metadata, values, order and row-group boundaries stay exact; physical hashes change.
- H2 front-end, mapping, EVP SHA256, build script and vendored JSON sources are
  byte-identical to measured revision `a91b789`. The main Dockerfile builds the
  executable and makes `simulate` point to it, retaining the native extension,
  Python fallback adapter and `simulate-batch`. The JSON redistribution license
  is copied into the final image.
- Engine behavior, RNG, floating-point build flags, shared scoring, cards and
  public corpus are unchanged. The engine header and native adapter documentation
  now describe decoded equality instead of physical Parquet byte equality.

Original results: [H1](../20261008-output-radical/h01-parquet-encoding/README.md),
[H2](../20261008-output-radical/h02-native-executable/README.md).
Those separate measurements do not establish the combined speedup.

## Verification

[checks.json](checks.json) records the host checks; [check_host.py](check_host.py)
reuses the original experiment probes without altering their historical evidence.

- 70 differential mapping checks with identical host libm dispatch, including
  numeric defaults, rounding, seed limits, unsupported inputs and fallback cases.
- 14 synthetic writer comparisons against the frozen pre-H1 writer, including
  page/block boundaries, nullable fields, streaming/table agreement and error
  behavior. Full schemas with metadata and all ordered values match. Snappy,
  dictionary selection, absent statistics and row-group sizes are checked.
- C++ front-end syntax against host Arrow headers; Python syntax, seven existing
  verb-dispatch checks and Git whitespace checks.
- Source hashes confirm the adopted H1/H2 implementation files match the measured
  revisions exactly. Temporary binaries and fixtures are removed after checking.

Host: macOS ARM, Python 3.13, Arrow 25.0.1. Writer and mapping checks are preliminary
host validation, not a fresh pinned Arrow15/x86 runtime check. There was no link or
execution of the production executable, Docker build, complete-container gate run,
public regression run or performance measurement. Prior pinned experiment evidence
remains linked above. No new performance percentage is claimed.

Reproduce the Docker-free checks from the repository root:

```sh
.venv/bin/python experiments/20261008-output-integration/check_host.py
```
