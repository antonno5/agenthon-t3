The selected simulator combines compact lifecycle output, parallel Parquet encoding,
the H1 physical encoding policy and the H2 standalone executable. Publication audits
the selected sources against the previously checked pinned environment. Fresh market
simulation checks for this combined build are skipped by user instruction; earlier 71/71 results belong
to the prior solution and are preserved as historical evidence.

# Agenthon T3 — team 523

Source: Track3 `codex/develop` at `e7225f883226a7f25da2457c0950660ca5c2771d`.
Image: `ghcr.io/antonno5/agenthon-t3`, Linux amd64, tag `sha-<publication commit>`.
The Python base digest and package pins are retained from the validated publication.
The Docker recipe builds both the native extension and standalone single-scenario
command. Batch retains its Python adapter. The selected source manifest is in
`provenance/selected-build-input.json`; original environment expectations remain
unchanged in `provenance/expected-runtime.json`.

Actions verifies source hashes, native API, the ELF launcher, package versions,
Docker config and offline help for both verbs, then publishes the immutable image.
It runs no market scenarios. Build-time synthetic C++ tests are omitted for this
publication to preserve the previous request not to run Docker tests.
This audit does not prove semantic equality or readiness under platform limits.
The original reports are preserved under `provenance/historical/` and must not be
presented as coverage of this new combination.

The individual H1/H2 experiments and integration host checks are recorded in
`provenance/evidence/`. The former measured the hypotheses independently;
their speedups cannot be added to claim a combined improvement.

Team Key stays outside Git and the Docker context. ZIPs, claims, logs, `.venv` and
`out/` are ignored. A new submission must point to the new immutable registry
digest and contain a newly generated team proof. Preparation does not upload
anything to CodaBench.
