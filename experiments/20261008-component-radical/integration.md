Executive summary: H1 compact lifecycle traces and H2 parallel Parquet encoding were applied together to `codex/develop` at the user's request on 2026-10-08. No new builds, correctness runs or performance measurements were performed during integration. The archived measurements describe each optimization separately against the original baseline.

Reports were committed in `de43f92`. H1 was applied in `7cf6b27`; H2 is applied by the commit containing this note.

| Optimization | Source branch / final experiment commit | Applied production files |
|---|---|---|
| H1 compact trace | `codex/exp-20261008-component-h01-trace-stream` / `3e2136a2d06c49ae836df241b247da67d2170b33` | `baselines/native/engine.cpp`, `baselines/native/trace_stream.hpp` |
| H2 parallel Parquet | `codex/exp-20261008-component-h02-parquet-parallel` / `afad1a32ea816e1c1b35bca242acdaa305fdc3ce` | `baselines/native/pqwrite.cpp` |

The applied files are copied unchanged from their experiment branches. The changes affect distinct files and keep the existing `TraceColumns` interface. Integration verification consists only of Git source comparisons and whitespace checks.

The experiment reports, source fingerprints and `adopted: false` fields remain historical snapshots of the measurement campaign before the integration decision. Combined correctness and speed have not been measured; individual percentages should not be added to predict the combined gain.
