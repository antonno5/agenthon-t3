"""Executive summary: independently audit completed trials and collect their reports.

Only experiment reports are copied to the production checkout. Implementations
stay in their isolated branches; every reported percentage is recomputed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess

AREA = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    plan = read(AREA / "plan.json")
    destination = Path(plan["report_directory"])
    rows, audits, intervals = [], [], []
    for exp in plan["experiments"]:
        done = read(AREA / ("DONE-" + exp["slug"] + ".json"))
        ready = read(AREA / ("READY-" + exp["slug"] + ".json"))
        controls_path = Path(ready["controls_path"])
        controls = read(controls_path / "summary.json")
        assert controls["complete"] and controls["accepted"]
        expected_controls = set(exp["units"] + exp["correctness_only_units"])
        assert {r["unit"] for r in controls["runs"]} == expected_controls
        assert len(controls["runs"]) == len(expected_controls) * 2
        assert all(r["accepted"] and all(v == "native" for v in r["actual_native"].values()) for r in controls["runs"])
        for comparison in controls["comparisons"]:
            assert all(comparison[k] for k in ["byte_equal", "schema_equal", "semantic_exact_equal"])
            for file in comparison["files"]:
                assert sha(Path(file["left"])) == file["left_sha256"] == file["right_sha256"] == sha(Path(file["right"]))
        report = Path(exp["worktree"]) / "expirements/20261008-radical-hypotheses" / exp["slug"]
        result = read(report / "result.json")
        assert result["complete"] and result["accepted"], (exp["slug"], "incomplete or incorrect")
        assert result["assigned_units"] == exp["units"]
        assert result["base_commit"] == plan["base_commit"]
        assert result["source_unchanged_during_measurement"]
        assert result["images"]["baseline"]["digest"] == plan["baseline_image"]
        source = Path(result["evidence_directory"])
        summary = read(source / "summary.json")
        assert sha(source / "summary.json") == result["summary_sha256"]
        assert summary["complete"] and summary["accepted"]
        assert len(summary["runs"]) == len(exp["units"]) * 12
        journal_count = 0
        for run in summary["runs"]:
            assert run["accepted"] and all(v == "native" for v in run["actual_native"].values())
            assert run["state"]["Status"] == "exited" and not run["state"]["Running"]
            assert run["kind"] in {"timing", "warmup"}
            start, end = run["state"]["StartedAt"], run["state"]["FinishedAt"]
            intervals.append((start, end, exp["slug"], run["unit"], run["kind"]))
            kept = source / "runs" / run["unit"] / f'{run["kind"]}-{run["index"]:02d}' / run["side"] / "retained"
            for events in kept.rglob("events.json"):
                ev = read(events)
                assert ev["engine"] == "native"
                for filename, key in [("trace.parquet", "trace_sha256"), ("message_trace.parquet", "message_trace_sha256")]:
                    assert sha(events.with_name(filename)) == ev[key]
                    journal_count += 1
        for row in result["results"]:
            runs = {side: sorted((r for r in summary["runs"] if r["unit"] == row["unit"] and r["side"] == side and r["kind"] == "timing"), key=lambda r: r["index"]) for side in ["baseline", "candidate"]}
            assert all(len(v) == 5 for v in runs.values())
            samples = {side: [r["container_sec"] for r in v] for side, v in runs.items()}
            assert samples == row["container_seconds_samples"]
            medians = {side: statistics.median(v) for side, v in samples.items()}
            assert medians == row["median_container_seconds"]
            percent = 100 * (1 - medians["candidate"] / medians["baseline"])
            assert abs(percent - row["time_reduction_pct"]) < 1e-9
            rows.append({"slug": exp["slug"], "title": exp["title"], "unit": row["unit"], "baseline_seconds": medians["baseline"], "candidate_seconds": medians["candidate"], "time_reduction_pct": percent, "candidate_faster_pairs": row["candidate_faster_pairs"]})
        target = destination / exp["slug"]
        target.mkdir(exist_ok=True)
        for path in sorted(report.iterdir()):
            if path.is_file() and path.suffix in {".md", ".json"}:
                shutil.copy2(path, target / path.name)
        shutil.copy2(AREA / ("READY-" + exp["slug"] + ".json"), target / "readiness-snapshot.json")
        shutil.copy2(AREA / ("DONE-" + exp["slug"] + ".json"), target / "completion-snapshot.json")
        audits.append({"slug": exp["slug"], "journal_digests_independently_rechecked": journal_count, "runs": len(summary["runs"]), "correctness_control_runs": len(controls["runs"]), "controls_summary_sha256": sha(controls_path / "summary.json"), "summary_sha256": result["summary_sha256"], "implementation_commit": result["candidate_implementation_commit"], "completion": done})
    intervals.sort()
    clock_anomalies = []
    for left, right in zip(intervals, intervals[1:]):
        if left[1] > right[0]:
            assert left[2] == right[2], ("cross-experiment timestamps overlap", left, right)
            clock_anomalies.append({"previous": left, "next": right, "cause": "unknown; Docker wall-clock intervals disagree with sequential launches and idle-slot checks"})
    comparison = {"executive_summary": "Four isolated radical optimization experiments. Positive percentages mean less complete-container time; negative percentages mean longer runs. All timings are local and non-rankable.", "complete": True, "accepted": True, "rankable": False, "adopted": False, "base_commit": plan["base_commit"], "baseline_image": plan["baseline_image"], "policy": plan["policy"], "results": rows}
    dump(destination / "comparison.json", comparison)
    dump(destination / "orchestration-audit.json", {"complete": True, "accepted": True, "audits": audits, "container_intervals_checked": len(intervals), "no_cross_experiment_timestamp_overlap": True, "all_container_timestamps_nonoverlapping": not clock_anomalies, "clock_anomalies": clock_anomalies, "serial_execution": "shared exclusive lock; synchronous runner with docker ps idle checks before each launch", "timing_caveat": "One apparent 18.671528 ms overlap in H04 s001 candidate timing 2/3. Cause not established; original samples retained."})
    shutil.copy2(AREA / "plan.json", destination / "plan.json")
    for name in ["scope-audit.json", "run_focused.py", "archive_results.py", "docker_slot.py"]:
        shutil.copy2(AREA / name, destination / name)
    for name in ["build-record.json", "runtime.json", "corpus-preflight.json"]:
        shutil.copy2(AREA / "base" / name, destination / ("baseline-" + name))
    text = [comparison["executive_summary"], "", "Знак: **+ — ускорение, − — замедление**. Формула: `100 × (1 − median(candidate) / median(baseline))`. Каждый сценарий: один прогрев каждой стороны и пять новых AB/BA-пар; прогревы исключены, все выбросы сохранены. Основная метрика — полное время Docker-контейнера.", "", "| Гипотеза | Сценарий | База, мс | Вариант, мс | Ускорение / замедление | Быстрее в парах |", "|---|---|---:|---:|---:|---:|"]
    for row in rows:
        text.append(f'| [{row["title"]}]({row["slug"]}/README.md) | `{row["unit"]}` | {row["baseline_seconds"] * 1000:.3f} | {row["candidate_seconds"] * 1000:.3f} | **{row["time_reduction_pct"]:+.2f}%** | {row["candidate_faster_pairs"]}/5 |')
    text += ["", "Ускорения в разы на выбранных сценариях не получено. Максимальный выигрыш полного времени — **19,07% (1,24×)** у H04 cancel churn. H02 дал положительный результат во всех четырёх выбранных сценариях (+3,11…+9,47%); H01, H03 и H04 имеют регрессии. Это основание для проверки H02 и профильного H04 на целевом Linux-хосте, но не подтверждение устойчивого универсального выигрыша.", "", "Аномалия часов: Docker timestamps двух последовательных H04 s001 candidate runs (timing 2/3) формально пересекаются на 18,671528 мс. Запуски выполнялись синхронно под exclusive lock, runner проверял пустой docker ps перед каждым запуском и завершённый state после. Причина несогласованности не установлена; исходные samples сохранены. Результат короткого H04 контроля следует интерпретировать осторожно. Точные timestamps записаны в orchestration-audit.json."]
    text += ["", "Каждая реализация находится в отдельной ветке и worktree; в этом checkout собраны только отчёты. Автоматической интеграции в production нет. Полный public corpus не запускался: наборы измерений и дополнительные проверки корректности перечислены в `plan.json`.", "", "Среда: Mac ARM64, Colima linux/amd64, четыре CPU, 16 GiB memory+swap, network none; `rankable:false`. Небольшие изменения в пределах нескольких процентов не устанавливают устойчивого эффекта и требуют проверки на целевом Linux-хосте.", "", "Полные samples, фазы и пути сырых доказательств сохранены в индивидуальных `result.json`. `comparison.json` содержит сводку; `orchestration-audit.json` — независимую проверку медиан, журналов и отсутствия пересечения контейнеров.", "", "| Гипотеза | Ветка | Чат |", "|---|---|---|"]
    for exp in plan["experiments"]:
        text.append(f'| {exp["title"]} | `{exp["branch"]}` | `{exp["thread_id"]}` |')
    (destination / "README.md").write_text("\n".join(text) + "\n")
    print(json.dumps({"report": str(destination), "results": rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
