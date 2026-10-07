"""Apply both patches, test the applied code and measure it without Docker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any
import urllib.request
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KERNEL_SHA = "cd0fdd3800ba7b49da0c82d7343f09942c617b6b4b01df37e1babb964f55239e"
PIN = "f9cbe51342b7dedd9587e4e069040d68a5c6477f"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def upstream(supplied: Path | None) -> tuple[Path, str]:
    cache = HERE / ".cache/kernel.py"
    if supplied:
        origin = supplied.resolve()
    elif cache.exists():
        origin = cache
    else:
        pointer = ROOT / "out/experiments/latest-kernel_message_ledger.json"
        origin = Path("/nonexistent")
        if pointer.exists():
            prior = Path(json.loads(pointer.read_text())["summary"]).parent
            origin = prior / "kernel-source/abides-core/abides_core/kernel.py"
        if not origin.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            url = f"https://raw.githubusercontent.com/jpmorganchase/abides-jpmc-public/{PIN}/abides-core/abides_core/kernel.py"
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read()
            if hashlib.sha256(content).hexdigest() != KERNEL_SHA:
                raise ValueError("downloaded upstream Kernel differs from the pin")
            cache.write_bytes(content)
            return cache, url
    if sha(origin) != KERNEL_SHA:
        raise ValueError(f"upstream Kernel SHA-256 differs from the pin: {origin}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if origin.resolve() != cache.resolve():
        shutil.copy2(origin, cache)
    return cache, str(origin)


def command(
    args: list[str], log: Path, *, cwd: Path = ROOT, env: dict[str, str] | None = None
) -> float:
    started = time.perf_counter()
    with log.open("a") as output:
        output.write(json.dumps(args) + "\n")
        output.flush()
        subprocess.run(
            args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True
        )
    return time.perf_counter() - started


def apply(directory: Path, source: Path) -> dict[str, Any]:
    snapshot = directory / "snapshot"
    application: dict[str, Any] = {"upstream_sha256": sha(source), "variants": {}}
    for variant, patch_name in (
        ("before", "legacy_kernel_message_ledger.patch"),
        ("after", "kernel_message_ledger.patch"),
    ):
        target = directory / "applied" / variant
        kernel = target / "abides-core/abides_core/kernel.py"
        adapter = target / "baselines/abides_fork/trace.py"
        kernel.parent.mkdir(parents=True)
        adapter.parent.mkdir(parents=True)
        shutil.copy2(source, kernel)
        shutil.copy2(snapshot / "baselines/abides_fork/trace.py", adapter)
        environment = {**os.environ, "GIT_CEILING_DIRECTORIES": str(directory)}
        log = directory / f"apply-{variant}.log"
        patch_file = snapshot / "experiments/kernel_message_ledger" / patch_name
        base_command = ["git", "apply"]
        command(
            base_command + ["--check", str(patch_file)],
            log,
            cwd=target,
            env=environment,
        )
        command(base_command + [str(patch_file)], log, cwd=target, env=environment)
        adapter_patch = snapshot / "experiments/kernel_message_ledger/adapter.patch"
        # Reconstruct the previous adapter, then actually apply the improvement to after.
        command(
            base_command + ["--reverse", str(adapter_patch)],
            log,
            cwd=target,
            env=environment,
        )
        if variant == "after":
            command(
                base_command + ["--check", str(adapter_patch)],
                log,
                cwd=target,
                env=environment,
            )
            command(
                base_command + [str(adapter_patch)], log, cwd=target, env=environment
            )
            if sha(adapter) != sha(snapshot / "baselines/abides_fork/trace.py"):
                raise ValueError(
                    "applied adapter differs from the baseline source snapshot"
                )
        if sha(kernel) == KERNEL_SHA:
            raise ValueError("kernel patch was not applied")
        application["variants"][variant] = {
            "kernel": str(kernel),
            "kernel_sha256": sha(kernel),
            "adapter": str(adapter),
            "adapter_sha256": sha(adapter),
            "kernel_patch_sha256": sha(patch_file),
            "adapter_patch_sha256": sha(adapter_patch),
        }
    application["baseline_kernel_patch_matches"] = sha(
        snapshot / "experiments/kernel_message_ledger/kernel_message_ledger.patch"
    ) == sha(ROOT / "baselines/patches/kernel_message_ledger.patch")
    application["baseline_adapter_matches"] = sha(
        Path(application["variants"]["after"]["adapter"])
    ) == sha(ROOT / "baselines/abides_fork/trace.py")
    dump(directory / "application.json", application)
    return application


def decision(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "verdict": "не делаем",
        "scope": "extraction component and Python heap",
    }
    if metadata["status"] != "complete":
        result["reason"] = "Эксперимент не завершён успешно; решение не принимаем."
        return result
    test = metadata["tests"]
    micro = metadata["microbenchmark"]
    if (
        not test["passed"]
        or test["skipped"]
        or test["failures"]
        or test["errors"]
        or not micro["parquet_bytes_equal"]
    ):
        result["reason"] = "Тесты не пройдены полностью либо Parquet различается."
        return result
    before, after = (
        micro["median_extract_sec"]["before"],
        micro["median_extract_sec"]["after"],
    )
    mb, ma = (
        micro["peak_python_heap_bytes"]["before"],
        micro["peak_python_heap_bytes"]["after"],
    )
    time_gain, memory_gain = 1 - after / before, 1 - ma / mb
    policy = metadata["policy"]["acceptance"]
    keep = (
        time_gain >= policy["extract_time_reduction_min"]
        and memory_gain >= policy["python_heap_reduction_min"]
    )
    result.update(
        verdict="делаем" if keep else "не делаем",
        time_reduction=time_gain,
        memory_reduction=memory_gain,
        policy=policy,
        reason=f"Сборка таблицы: снижение времени {time_gain:.1%}; пик Python heap: снижение {memory_gain:.1%}. Порог каждого — 10%; все целевые тесты пройдены, Parquet совпал. Решение относится к компоненту; ускорение всей симуляции не доказано.",
    )
    return result


def report(directory: Path, metadata: dict[str, Any]) -> None:
    verdict = decision(metadata)
    dump(directory / "metadata.json", metadata)
    dump(directory / "decision.json", verdict)
    dump(directory / "summary.json", {"metadata": metadata, "decision": verdict})
    text = [
        "# Применение и проверка kernel message ledger",
        "",
        "## Executive summary",
        "",
        "The experiment applies the old and new kernel patches to separate copies of pinned",
        "ABIDES, tests the applied code, and measures table extraction and Python heap.",
        "Docker is not used. The decision covers this component, not full simulation speed.",
        "",
        "## Изменение и применение",
        "",
        metadata["description"],
        "",
        f"Статус: `{metadata['status']}`. Код применения и SHA-256: [application.json](application.json).",
        "После применения код находится в `applied/before/` и `applied/after/`; именно after-адаптер",
        "и оба применённых Kernel использованы в тестах. Пакет ABIDES в системе не устанавливается.",
        "",
        f"**Вердикт: {verdict['verdict']}.** {verdict['reason']}",
        "",
    ]
    if metadata.get("tests"):
        t = metadata["tests"]
        text += [
            "## Целевые тесты",
            "",
            f"Пройдено: **{t['passed']}**, пропущено: {t['skipped']}, failures: {t['failures']}, errors: {t['errors']}.",
            "Лог: [tests.log](tests.log); машинный результат: [tests.xml](tests.xml).",
            "",
        ]
    if metadata.get("microbenchmark"):
        m = metadata["microbenchmark"]
        a, b = m["median_extract_sec"]["before"], m["median_extract_sec"]["after"]
        ma, mb = (
            m["peak_python_heap_bytes"]["before"],
            m["peak_python_heap_bytes"]["after"],
        )
        text += [
            "## Замеры компонента",
            "",
            f"{m['delivered_rows']} доставок; один разогрев и {m['repeats']} повтора каждого варианта.",
            "",
            "| Метрика | Before | After |",
            "|---|---:|---:|",
            f"| Сборка таблицы, с | {a:.6f} | {b:.6f} |",
            f"| Пик Python heap, MiB | {ma/2**20:.2f} | {mb/2**20:.2f} |",
            "",
            f"Ускорение компонента: {a/b:.2f}x. Parquet совпал: {m['parquet_bytes_equal']}.",
            "Время включает только extract_message_trace. Создание входа и Parquet исключены.",
            "Память включает создание входных структур и таблицы; измерена отдельным tracemalloc прогоном, это не RSS.",
            f"Окружение: Python {m['python']}, пакеты {m['packages']}; локальная .venv, без Docker.",
            "",
        ]
        (directory / "summary.csv").write_text(
            "variant,extract_sec,peak_python_heap_bytes\n"
            + f"before,{a},{ma}\nafter,{b},{mb}\n"
        )
    text += ["## Время этапов эксперимента", "", "| Этап | Секунды |", "|---|---:|"]
    text += [f"| {k} | {v:.4f} |" for k, v in metadata.get("phase_seconds", {}).items()]
    text += [
        "",
        "Код, патчи, зависимости и команды сохранены в snapshot/, metadata.json и логах.",
        "Тесты исполняют методы реального pinned Kernel с тестовыми агентами и сообщениями.",
        "Полный запуск ABIDES, CLI контейнера и official Final этим режимом не проверяются.",
    ]
    if metadata.get("reason"):
        text += ["", "Ошибка: " + metadata["reason"]]
    (directory / "REPORT.ru.md").write_text("\n".join(text) + "\n")
    (directory / "CHANGE.ru.md").write_text(
        "# Изменение и вердикт\n\n## Executive summary\n\nThis records the local component decision.\n\n"
        + metadata["description"]
        + "\n\n**"
        + verdict["verdict"]
        + ".** "
        + verdict["reason"]
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-source", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--context", default="colima-agenthon", help="used only in --mode container"
    )
    args = parser.parse_args(argv)
    if args.repeats < 3:
        parser.error("at least three measured repeats required")
    directory = (
        HERE
        / "runs"
        / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    )
    directory.mkdir(parents=True)
    metadata: dict[str, Any] = {
        "status": "running",
        "mode": "local",
        "rankable": False,
        "arguments": vars(args),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": "Компактные записи окончательных доставок вместо списка отправлений, таблицы seq и сортировки; фиксированная причинность и отдельные получатели рассылки.",
        "policy": json.loads((HERE / "experiment.json").read_text()),
        "host": platform.platform(),
        "phase_seconds": {},
        "source_sha256": {},
        "python": sys.version,
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("pytest", "pandas", "numpy", "pyarrow")
        },
    }
    print(f"EXPERIMENT={directory}", flush=True)
    try:
        metadata["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        (directory / "changes.patch").write_bytes(
            subprocess.check_output(
                [
                    "git",
                    "diff",
                    "HEAD",
                    "--",
                    "baselines/patches/kernel_message_ledger.patch",
                    "baselines/abides_fork/trace.py",
                ],
                cwd=ROOT,
            )
        )
        start = time.perf_counter()
        source, origin = upstream(args.kernel_source)
        metadata["upstream"] = {"pin": PIN, "sha256": KERNEL_SHA, "origin": origin}
        paths = [p for p in HERE.iterdir() if p.is_file() and p.name != "latest.json"]
        paths += [
            ROOT / "baselines/abides_fork/trace.py",
            ROOT / "baselines/patches/kernel_message_ledger.patch",
            ROOT / "tests/test_delivery_ledger.py",
            ROOT / "tests/integration/test_delivery_ledger_kernel.py",
        ]
        for p in paths:
            relative = p.relative_to(ROOT)
            target = directory / "snapshot" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            metadata["source_sha256"][str(relative)] = sha(p)
        pointer = HERE / "latest.json"
        if pointer.exists():
            previous = Path(json.loads(pointer.read_text())["summary"])
            prior = json.loads(previous.read_text())["metadata"]
            old, current = prior["source_sha256"], metadata["source_sha256"]
            metadata["previous"] = str(previous)
            dump(
                directory / "source_changes.json",
                {
                    "previous": str(previous),
                    "added": sorted(current.keys() - old.keys()),
                    "removed": sorted(old.keys() - current.keys()),
                    "changed": sorted(
                        k for k in current.keys() & old.keys() if current[k] != old[k]
                    ),
                },
            )
        original = directory / "upstream/kernel.py"
        original.parent.mkdir(parents=True)
        shutil.copy2(source, original)
        metadata["phase_seconds"]["preparation"] = time.perf_counter() - start
        start = time.perf_counter()
        application = apply(directory, original)
        if (
            not application["baseline_kernel_patch_matches"]
            or not application["baseline_adapter_matches"]
        ):
            raise ValueError(
                "experiment patches and baseline source diverge; sync them before measuring"
            )
        metadata["application"] = application
        metadata["phase_seconds"]["apply_patches"] = time.perf_counter() - start
        before, after = (
            application["variants"]["before"],
            application["variants"]["after"],
        )
        environment = {
            **os.environ,
            "QFB2_ABIDES_KERNEL_SOURCE": str(original),
            "QFB2_LEDGER_KERNEL_LEGACY": before["kernel"],
            "QFB2_LEDGER_KERNEL_OPTIMIZED": after["kernel"],
            "QFB2_LEDGER_ADAPTER": after["adapter"],
        }
        tests = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_delivery_ledger.py",
            "tests/integration/test_delivery_ledger_kernel.py",
            "-o",
            "addopts=",
            "--junitxml",
            str(directory / "tests.xml"),
            "-q",
        ]
        metadata["phase_seconds"]["targeted_tests"] = command(
            tests, directory / "tests.log", env=environment
        )
        xml = ET.parse(directory / "tests.xml")
        suites = list(xml.getroot().iter("testsuite"))
        totals = {
            k: sum(int(s.attrib.get(k, 0)) for s in suites)
            for k in ("tests", "skipped", "failures", "errors")
        }
        metadata["tests"] = {
            **totals,
            "passed": totals["tests"]
            - totals["skipped"]
            - totals["failures"]
            - totals["errors"],
            "command": tests,
        }
        if not metadata["tests"]["passed"] or any(
            totals[k] for k in ("skipped", "failures", "errors")
        ):
            raise ValueError("targeted tests were skipped or failed")
        micro = [
            sys.executable,
            str(
                directory
                / "snapshot/experiments/kernel_message_ledger/microbenchmark.py"
            ),
            "--out",
            str(directory / "microbenchmark"),
            "--repeats",
            str(args.repeats),
            "--rows",
            str(metadata["policy"]["rows"]),
            "--before-adapter",
            before["adapter"],
            "--after-adapter",
            after["adapter"],
        ]
        metadata["phase_seconds"]["microbenchmark"] = command(
            micro, directory / "microbenchmark.log"
        )
        metadata["microbenchmark"] = json.loads(
            (directory / "microbenchmark/result.json").read_text()
        )
        for variant in application["variants"].values():
            if (
                sha(Path(variant["kernel"])) != variant["kernel_sha256"]
                or sha(Path(variant["adapter"])) != variant["adapter_sha256"]
            ):
                raise ValueError("applied code changed during tests/measurement")
        metadata["status"] = "complete"
    except KeyboardInterrupt:
        metadata.update(status="interrupted", reason="Stopped by user")
    except Exception as exc:
        metadata.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
    finally:
        report(directory, metadata)
    if metadata["status"] == "complete":
        dump(
            HERE / "latest.json",
            {
                "report": str(directory / "REPORT.ru.md"),
                "summary": str(directory / "summary.json"),
            },
        )
    print(f"REPORT={directory / 'REPORT.ru.md'}", flush=True)
    return 0 if metadata["status"] == "complete" else 1
