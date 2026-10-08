"""Executive summary: preserve completed experiment reports in the simulator repository.

Copy reviewable sources, reports and all evidence without adopting candidate code.
Closed Parquet evidence uses plain-file APFS clones to avoid disk duplication.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
from run_focused import clone_plain_file

AREA = Path(__file__).resolve().parent
plan = json.loads((AREA / "plan.json").read_text())
target = Path(plan["report_directory"])
target.mkdir(parents=True, exist_ok=True)

def copy_file(src, dst):
    src, dst = Path(src), Path(dst)
    if src.suffix == ".parquet":
        if dst.exists():
            dst.unlink()
        return clone_plain_file(src, dst)
    return shutil.copy2(src, dst)

archived = []
for exp in plan["experiments"]:
    source = Path(exp["experiment_directory"])
    result = source / "result.json"
    if not result.exists():
        raise RuntimeError(f"Final result absent: {exp['slug']}")
    parsed = json.loads(result.read_text())
    destination = target / exp["slug"]
    shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=copy_file,
                    ignore=shutil.ignore_patterns("__pycache__", "*.dedup-link"))
    patch = subprocess.check_output(["git", "diff", plan["base_commit"],
        parsed["candidate_implementation_commit"], "--", "baselines", ".gitignore"],
        cwd=exp["worktree"])
    (destination / "implementation.patch").write_bytes(patch)
    archived.append({"slug": exp["slug"], "candidate_commit": parsed["candidate_implementation_commit"],
        "branch": exp["branch"], "worktree": exp["worktree"], "thread_id": exp["thread_id"],
        "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
        "implementation_patch_sha256": hashlib.sha256(patch).hexdigest(),
        "archived_directory": str(destination)})

for filename in ["plan.json", "run_focused.py", "docker_slot.py", "audit_baseline.py",
        "audit_results.py", "archive_results.py", "render_report.py", "manager-audit.json", "measurement-harness-freeze.json",
        "Baseline.Dockerfile", "baseline-audit.json", "corpus-preflight.json",
        "checker-policy-audit.json", "corpus-storage-dedup.json", "corpus-storage-restored.json",
        "corpus-restoration-audit.json"]:
    if (AREA / filename).exists():
        shutil.copy2(AREA / filename, target / filename)
for pattern in ["READY-*.json", "PREFLIGHT-*.json", "DONE-*.json", "baseline-*-build.log"]:
    for source in AREA.glob(pattern):
        shutil.copy2(source, target / source.name)
for directory in ["baseline-evidence", "checker-evidence"]:
    if (AREA / directory).exists():
        shutil.copytree(AREA / directory, target / directory, dirs_exist_ok=True, copy_function=copy_file)
(target / "archive.json").write_text(json.dumps({"executive_summary": "All four isolated experiments and their evidence are archived; production sources are unchanged.",
    "adopted": False, "experiments": archived}, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"archived": [x["slug"] for x in archived], "directory": str(target)}))
