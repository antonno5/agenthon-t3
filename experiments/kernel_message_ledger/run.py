#!/usr/bin/env python3
"""Reproduce the isolated kernel-ledger comparison and keep all evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts import run_component_experiment as common  # noqa: E402

DESCRIPTION = (
    "Компактный журнал добавляет строки при окончательной доставке вместо списка "
    "отправлений и отдельной таблицы seq. Метаданные отправки сохраняются до доставки; "
    "рассылка учитывает каждого получателя, недоставленные сообщения исключаются."
)
UNIT = "t3-s001-price-time-priority"


def logged(command: list[str], path: Path, env: dict[str, str] | None = None) -> None:
    with path.open("w") as log:
        subprocess.run(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True
        )


def prepare_builds(directory: Path) -> dict[str, str]:
    manifests = {}
    for variant in ("before", "after"):
        context = directory / "build-context" / variant
        shutil.copytree(
            ROOT / "baselines",
            context,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        if variant == "before":
            shutil.copy2(
                HERE / "legacy_kernel_message_ledger.patch",
                context / "patches/kernel_message_ledger.patch",
            )
        manifests[variant] = {
            str(p.relative_to(context)): common.sha(p)
            for p in sorted(context.rglob("*"))
            if p.is_file()
        }
    before, after = manifests["before"], manifests["after"]
    differences = sorted(
        k for k in before.keys() | after.keys() if before.get(k) != after.get(k)
    )
    if differences != ["patches/kernel_message_ledger.patch"]:
        raise ValueError(f"comparison does not isolate the ledger patch: {differences}")
    common.dump(
        directory / "build-inputs.json",
        {"differences": differences, "sha256": manifests},
    )
    return {
        variant: str(directory / "build-context" / variant) for variant in manifests
    }


def source_for_kernel_tests(directory: Path, docker: list[str], image: str) -> Path:
    source = directory / "kernel-source/abides-core/abides_core/kernel.py"
    source.parent.mkdir(parents=True)
    container = common.command_output(
        docker + ["create", "--platform", "linux/amd64", image]
    )
    try:
        subprocess.run(
            docker
            + [
                "cp",
                f"{container}:/usr/local/lib/python3.11/site-packages/abides_core/kernel.py",
                str(source),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        subprocess.run(
            docker + ["rm", "-f", container], check=True, capture_output=True
        )
    subprocess.run(
        [
            "git",
            "apply",
            "--reverse",
            str(directory / "build-context/after/patches/kernel_message_ledger.patch"),
        ],
        cwd=directory / "kernel-source",
        # Treat this extracted tree independently of the enclosing repository;
        # otherwise git can silently ignore paths outside its working prefix.
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(directory)},
        check=True,
        capture_output=True,
    )
    expected = "cd0fdd3800ba7b49da0c82d7343f09942c617b6b4b01df37e1babb964f55239e"
    if common.sha(source) != expected:
        raise ValueError("reconstructed upstream kernel differs from the published pin")
    return source


def write_report(
    directory: Path, metadata: dict[str, Any], records: list[dict[str, Any]]
) -> None:
    rows = common.aggregates(records)
    # Apply the existing decision rule, keeping the event collector fixed in both images.
    decision_rows = [
        {**r, "mode": "legacy" if r["mode"] == "before" else "buffered"} for r in rows
    ]
    decision = common.decide({**metadata, "previous": None}, decision_rows, records)
    decision["basis"] = "legacy_kernel_vs_delivery_kernel"
    decision["scope"] = "one public unit; local non-rankable container timing"
    common.dump(directory / "decision.json", decision)
    micro = metadata.get("microbenchmark")
    common.dump(
        directory / "summary.json",
        {
            "metadata": metadata,
            "decision": decision,
            "aggregates": rows,
            "runs": records,
            "microbenchmark": micro,
        },
    )
    keys = [
        "unit",
        "mode",
        "kind",
        "repeats",
        "container_sec",
        "adapter_sec",
        "container_other_sec",
        "n_events",
        "n_messages",
        "all_gates_pass",
        "all_reference_bytes_equal",
        "stable_repeats",
    ]
    components = sorted({name for row in rows for name in row["components"]})
    with (directory / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys + components)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{k: row[k] for k in keys}, **row["components"]})
    note = (
        "# Изменение kernel message ledger\n\n## Executive summary\n\n"
        "This experiment compares the old send ledger with compact delivery rows. "
        "The decision applies to the measured local workload.\n\n"
        + metadata["description"]
        + "\n\n**Вердикт: "
        + decision["verdict"]
        + ".** "
        + decision["reason"]
        + "\n"
    )
    (directory / "CHANGE.ru.md").write_text(note)
    text = [
        "# Эксперимент kernel message ledger",
        "",
        "## Executive summary",
        "",
        "Only the kernel ledger patch changes between the two images. Both use the same",
        "typed event collector. Extraction and memory are measured separately on synthetic",
        "deliveries; full component timings and correctness use one small public unit.",
        "",
        "## Изменение и вердикт",
        "",
        metadata["description"],
        "",
        f"**Вердикт: {decision['verdict']}.** {decision['reason']}",
        "",
        f"Статус: `{metadata['status']}`. Контекст: `{metadata['context']}`.",
        "",
        "## Контейнер и проверки трасс",
        "",
        "Разогревы исключены. Подробные профили собираются отдельно от замеров скорости.",
        "",
        "| Вариант | Тип | Повторы | Контейнер, с | Адаптер, с | Вне адаптера, с | События | Сообщения | Gates | Байты эталона |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        text.append(
            f"| {row['mode']} | {row['kind']} | {row['repeats']} | {row['container_sec']:.6f} | {row['adapter_sec']:.6f} | {row['container_other_sec']:.6f} | {row['n_events']} | {row['n_messages']} | {row['all_gates_pass']} | {row['all_reference_bytes_equal']} |"
        )
    timings = {r["mode"]: r for r in rows if r["kind"] == "timing"}
    if {"before", "after"} <= timings.keys():
        before, after = (
            timings["before"]["container_sec"],
            timings["after"]["container_sec"],
        )
        text += [
            "",
            f"Медианы контейнера: {before:.6f} → {after:.6f} с ({1-after/before:+.1%} снижения).",
        ]
    if micro:
        a, b = (
            micro["median_extract_sec"]["before"],
            micro["median_extract_sec"]["after"],
        )
        ma, mb = (
            micro["peak_python_heap_bytes"]["before"],
            micro["peak_python_heap_bytes"]["after"],
        )
        text += [
            "",
            "## Синтетический компонент",
            "",
            f"{micro['delivered_rows']:,} доставок, {micro['repeats']} измеряемых повторов и один разогрев; {micro['undelivered_before']} недоставленных отправлений в before.",
            "",
            "| Метрика | Before | After | Отношение before/after |",
            "|---|---:|---:|---:|",
            f"| Сборка таблицы, с | {a:.6f} | {b:.6f} | {a/b:.3f}x |",
            f"| Пик Python heap, MiB | {ma / 2**20:.2f} | {mb / 2**20:.2f} | {ma/mb:.3f}x |",
            "",
            f"Parquet побайтово совпал: **{micro['parquet_bytes_equal']}**. Nullable int64 строятся без float64.",
            "",
            "Скорость: только extract_message_trace, без создания fixture и записи Parquet.",
            "Память: tracemalloc при создании входных структур и сборке таблицы; это не RSS.",
            "Профиль памяти отдельный: tracemalloc выключен в замерах скорости.",
        ]
    profiles = {r["mode"]: r for r in rows if r["kind"] == "profile"}
    if profiles:
        text += [
            "",
            "## Компоненты диагностических запусков",
            "",
            "Вложенные времена вычтены из родителей; таймеры добавляют расходы.",
            "",
            "| Компонент | Before, с | After, с |",
            "|---|---:|---:|",
        ]
        names = sorted({k for r in profiles.values() for k in r["components"]})
        for name in names:
            a = profiles.get("before", {}).get("components", {}).get(name, 0.0)
            b = profiles.get("after", {}).get("components", {}).get(name, 0.0)
            text.append(f"| {name} | {a:.6f} | {b:.6f} |")
    text += [
        "",
        "## Проверки и воспроизводимость",
        "",
        f"Согласованная make unit проверка: `{metadata.get('quick_check', 'not run')}`.",
        f"Целевые тесты адаптера и реального pinned Kernel: `{metadata.get('targeted_tests', 'not run')}`.",
        "",
        "Проверены порядок доставки, равное время, requeue, wakeup, каждый получатель рассылки,",
        "MessageBatch, causal_parent, мутация payload, недоставленные сообщения, pause/resume и граница stop_time.",
        "",
        "build-inputs.json доказывает, что образы отличаются только kernel_message_ledger.patch.",
        "metadata.json фиксирует исходники, commit, image ID и окружение; build-context/ хранит оба входа сборки.",
        "changes.patch — diff рабочей копии относительно HEAD. runs.jsonl и runs/ хранят результаты каждого запуска.",
        "",
        "Это локальные замеры linux/amd64 через эмуляцию на ARM, не официальное время Final.",
        "Маленький unit не доказывает выигрыш на больших сценариях. Ускорение синтетического компонента",
        "не означает такое же ускорение всего контейнера. Все публичные задания и весь pytest suite не запускались.",
    ]
    previous = metadata.get("previous")
    if previous:
        old = json.loads(Path(previous).read_text())
        old_rows = {(r["mode"], r["kind"]): r for r in old["aggregates"]}
        text += [
            "",
            "## Предыдущий эксперимент",
            "",
            f"Источник: `{previous}`.",
            "",
            "Окружение и параметры следует сверить в metadata.json; эта таблица не меняет вердикт before/after.",
            "",
            "| Вариант | Тип | Было, с | Сейчас, с |",
            "|---|---|---:|---:|",
        ]
        for row in rows:
            old_row = old_rows.get((row["mode"], row["kind"]))
            if old_row:
                text.append(
                    f"| {row['mode']} | {row['kind']} | {old_row['container_sec']:.6f} | {row['container_sec']:.6f} |"
                )
    (directory / "REPORT.ru.md").write_text("\n".join(text) + "\n")


def container_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", default="colima-agenthon")
    parser.add_argument("--image", default="my-simulator:local")
    parser.add_argument("--before-image", default="kernel-message-ledger-before:local")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--description", default=DESCRIPTION)
    parser.add_argument("--verdict", choices=("auto", "yes", "no"), default="auto")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    if args.repeats < 3:
        parser.error("at least three measured repeats required")
    if args.verdict != "auto" and not args.reason:
        parser.error("explicit verdict requires --reason")
    if args.image == args.before_image:
        parser.error("before and after image tags must differ")
    docker = ["docker", "--context", args.context]
    history = ROOT / "out/experiments"
    directory = (
        history
        / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-kernel_message_ledger-{uuid.uuid4().hex[:6]}"
    )
    directory.mkdir(parents=True)
    pointer = history / "latest-kernel_message_ledger.json"
    previous = json.loads(pointer.read_text())["summary"] if pointer.exists() else None
    metadata: dict[str, Any] = {
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "context": args.context,
        "host": platform.platform(),
        "unit": UNIT,
        "description": args.description,
        "arguments": vars(args),
        "previous": previous,
        "commit": common.command_output(["git", "rev-parse", "HEAD"]),
        "git_status": common.command_output(["git", "status", "--short"]),
        "docker_info": json.loads(
            common.command_output(docker + ["info", "--format", "{{json .}}"])
        ),
        "checker_packages": {
            p: importlib.metadata.version(p)
            for p in ("qfbench2-common", "pandas", "numpy", "pyarrow")
        },
        "source_sha256": common.capture_sources(directory / "snapshot"),
    }
    # Snapshot this experiment as well as the shared runner and simulator.
    for source in sorted(HERE.iterdir()):
        if source.is_file():
            relative = source.relative_to(ROOT)
            target = directory / "snapshot" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            metadata["source_sha256"][str(relative)] = common.sha(source)
    (directory / "changes.patch").write_text(
        common.command_output(
            [
                "git",
                "diff",
                "HEAD",
                "--",
                "baselines",
                "experiments",
                "scripts",
                "tests",
                "Makefile",
            ]
        )
        + "\n"
    )
    if previous:
        old = json.loads(Path(previous).read_text())["metadata"]["source_sha256"]
        current = metadata["source_sha256"]
        common.dump(
            directory / "source_changes.json",
            {
                "previous": previous,
                "added": sorted(current.keys() - old.keys()),
                "removed": sorted(old.keys() - current.keys()),
                "changed": sorted(
                    k for k in current.keys() & old.keys() if current[k] != old[k]
                ),
            },
        )
    # Do not persist unrelated Docker daemon configuration or registry data.
    metadata["docker_info"] = {
        k: metadata["docker_info"].get(k)
        for k in (
            "Name",
            "Architecture",
            "NCPU",
            "MemTotal",
            "ServerVersion",
            "KernelVersion",
        )
    }
    records: list[dict[str, Any]] = []
    common.dump(directory / "metadata.json", metadata)
    print(f"EXPERIMENT={directory}", flush=True)
    try:
        contexts = prepare_builds(directory)
        metadata["images"] = {}
        for variant, image in (("before", args.before_image), ("after", args.image)):
            print(f"BUILD {variant} {image}", flush=True)
            logged(
                docker
                + [
                    "build",
                    "--platform",
                    "linux/amd64",
                    "-t",
                    image,
                    contexts[variant],
                ],
                directory / f"build-{variant}.log",
            )
            metadata["images"][variant] = {
                "tag": image,
                "id": common.command_output(
                    docker + ["image", "inspect", "--format", "{{.Id}}", image]
                ),
            }
        kernel_source = source_for_kernel_tests(directory, docker, args.image)
        environment = {**os.environ, "QFB2_ABIDES_KERNEL_SOURCE": str(kernel_source)}
        tests = [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "pytest",
            "tests/test_delivery_ledger.py",
            "tests/integration/test_delivery_ledger_kernel.py",
            "-o",
            "addopts=",
            "-q",
        ]
        logged(tests, directory / "targeted-tests.log", environment)
        match = re.search(
            r"(\d+) passed", (directory / "targeted-tests.log").read_text()
        )
        metadata["targeted_tests"] = {
            "passed": int(match.group(1)) if match else None,
            "command": tests,
            "kernel_sha256": common.sha(kernel_source),
        }
        micro_name = f"t3-ledger-micro-{uuid.uuid4().hex[:8]}"
        try:
            logged(
                docker
                + [
                    "run",
                    "--name",
                    micro_name,
                    "--platform",
                    "linux/amd64",
                    "--network",
                    "none",
                    "--cpus",
                    "4",
                    "--memory",
                    "16g",
                    "-v",
                    f"{directory / 'snapshot/experiments/kernel_message_ledger'}:/experiment:ro",
                    "-v",
                    f"{directory}:/output",
                    args.image,
                    "python",
                    "/experiment/microbenchmark.py",
                    "--out",
                    "/output/microbenchmark",
                ],
                directory / "microbenchmark.log",
            )
        finally:
            subprocess.run(
                docker + ["rm", "-f", micro_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        metadata["microbenchmark"] = json.loads(
            (directory / "microbenchmark/result.json").read_text()
        )
        if not metadata["microbenchmark"]["parquet_bytes_equal"]:
            raise ValueError("microbenchmark Parquet differs")
        for index in range(args.repeats + 1):
            variants = ("before", "after") if index % 2 == 0 else ("after", "before")
            for variant in variants:
                image = args.before_image if variant == "before" else args.image
                options = argparse.Namespace(image=image, timeout=None)
                record = common.run_once(
                    options,
                    directory / variant,
                    docker,
                    ROOT / "units" / UNIT,
                    "buffered",
                    index,
                    False,
                    index == 0,
                )
                record.update(mode=variant, output=f"{variant}/{record['output']}")
                records.append(record)
                with (directory / "runs.jsonl").open("a") as log:
                    log.write(json.dumps(record) + "\n")
                write_report(directory, metadata, records)
                print(
                    f"RUN {variant} timing {index} sec={record.get('container_sec')} pass={record.get('check', {}).get('admissible')}",
                    flush=True,
                )
        for variant in ("before", "after"):
            options = argparse.Namespace(
                image=args.before_image if variant == "before" else args.image,
                timeout=None,
            )
            record = common.run_once(
                options,
                directory / variant,
                docker,
                ROOT / "units" / UNIT,
                "buffered",
                0,
                True,
                False,
            )
            record.update(mode=variant, output=f"{variant}/{record['output']}")
            records.append(record)
            with (directory / "runs.jsonl").open("a") as log:
                log.write(json.dumps(record) + "\n")
            write_report(directory, metadata, records)
        quick = [
            "make",
            "unit",
            f"UNIT={UNIT}",
            f"IMAGE={args.image}",
            "RESULTS=out/quick-check",
        ]
        logged(
            quick,
            directory / "quick-check.log",
            {**os.environ, "DOCKER_CONTEXT": args.context},
        )
        metadata["quick_check"] = {"passed": True, "command": quick}
        failed = any(
            r.get("error")
            or not r.get("check", {}).get("admissible")
            or not r.get("check", {}).get("reference_bytes_equal")
            for r in records
        )
        metadata["status"] = "failed" if failed else "complete"
    except KeyboardInterrupt:
        metadata.update(
            status="interrupted",
            reason="Stopped by user; active simulation containers removed",
        )
    except Exception as exc:
        metadata.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
    finally:
        common.dump(directory / "metadata.json", metadata)
        write_report(directory, metadata, records)
    if metadata["status"] == "complete":
        common.dump(pointer, {"summary": str(directory / "summary.json")})
    print(f"REPORT={directory / 'REPORT.ru.md'}", flush=True)
    return 0 if metadata["status"] == "complete" else 1


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=("local", "container"), default="local")
    mode, remaining = parser.parse_known_args()
    if mode.mode == "container":
        return container_main(remaining)
    from local import main as local_main

    return int(local_main(remaining))


if __name__ == "__main__":
    raise SystemExit(main())
