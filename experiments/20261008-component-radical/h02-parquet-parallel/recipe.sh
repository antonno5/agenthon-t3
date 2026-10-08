#!/usr/bin/env bash
# Executive summary: run the prepared checks and diagnostics only after coordinator dispatch.
set -euo pipefail
: "${H02_PHASE2_AUTHORIZED:?Coordinator must explicitly authorize the phase-2 Docker slot}"
if [[ "$H02_PHASE2_AUTHORIZED" != yes ]]; then exit 2; fi
worktree=$(git rev-parse --show-toplevel)
report="$worktree/experiments/20261008-component-radical/h02-parquet-parallel"
campaign='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-component-radical'
corpus='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/units'
builder='sha256:902a221eca63fc3781587c30114edd3d33e16d057049b30a23b552a0e4bc0d57'
builder_tag='track3-ledger-arena-builder:286ae97'
baseline='sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c'
baseline_tag='track3-ledger-arena:286ae97'
docker=(docker --context colima-agenthon)
caps=(--platform=linux/amd64 --network=none --cpus=4 --memory=16g --memory-swap=16g)
step=${1:?Select build, isolated, controls, timing, diagnostic-build or diagnostics}
image='track3-component-h02-parquet-parallel:phase2'
commit=$(git rev-parse HEAD)
mkdir -p "$report/evidence"
case "$step" in
  build)
    [[ "$("${docker[@]}" image inspect --format '{{.Id}}' "$builder_tag")" == "$builder" ]]
    [[ "$("${docker[@]}" image inspect --format '{{.Id}}' "$baseline_tag")" == "$baseline" ]]
    context="$report/evidence/build-context"
    mkdir -p "$context/baselines"
    cp -R "$worktree/baselines/native" "$context/baselines/"
    cp "$worktree/baselines/build_native.py" "$context/baselines/"
    "${docker[@]}" build --platform=linux/amd64 --network=none -f "$campaign/Dockerfile" \
      --build-arg "BASE_IMAGE=$baseline_tag" \
      --build-arg "BUILDER_IMAGE=$builder_tag" -t "$image" "$context"
    [[ "$("${docker[@]}" image inspect --format '{{.Id}}' "$builder_tag")" == "$builder" ]]
    [[ "$("${docker[@]}" image inspect --format '{{.Id}}' "$baseline_tag")" == "$baseline" ]]
    ;;
  isolated)
    mkdir -p "$report/evidence/pinned"
    "${docker[@]}" run --rm "${caps[@]}" --entrypoint python \
      -v "$worktree:/worktree:ro" -v "$corpus:/corpus:ro" -v "$report/evidence/pinned:/checks" "$builder" \
      /worktree/experiments/20261008-component-radical/h02-parquet-parallel/tests/check.py --corpus /corpus --out /checks
    ;;
  controls|timing)
    image=$("${docker[@]}" image inspect --format '{{.Id}}' "$image")
    extra=()
    if [[ "$step" == controls ]]; then extra=(--controls-only); fi
    '/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' \
      "$campaign/run_focused.py" --slug h02-parquet-parallel --candidate-image "$image" \
      --candidate-commit "$commit" --out "$report/evidence/$step" "${extra[@]}"
    ;;
  diagnostic-build|diagnostics)
    if [[ "$step" == diagnostic-build ]]; then args=(--build-only); else args=(--mode all); fi
    mkdir -p "$report/evidence/$step"
    "${docker[@]}" run --rm "${caps[@]}" --entrypoint python \
      -v "$worktree:/worktree:ro" -v "$corpus:/corpus:ro" -v "$campaign/plan.json:/plan.json:ro" \
      -v "$report/evidence/controls:/controls:ro" -v "$report/evidence/$step:/diagnostics" "$builder" \
      /worktree/experiments/20261008-component-radical/h02-parquet-parallel/diagnostics/run.py \
      --out /diagnostics/run --plan /plan.json --corpus /corpus --journals-root /controls "${args[@]}"
    ;;
  *) exit 2 ;;
esac
