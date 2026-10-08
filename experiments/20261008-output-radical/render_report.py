"""Executive summary: present all scenario results without averaging unlike workloads."""
from pathlib import Path
import json

AREA = Path(__file__).resolve().parent
plan = json.loads((AREA / "plan.json").read_text())
audit = json.loads((AREA / "manager-audit.json").read_text())
assert audit["accepted"]
target = Path(plan["report_directory"])

names = ["Дешёвое кодирование Parquet", "Standalone native executable",
         "Специализированный Parquet writer", "Конвейер lifecycle trace"]
selection = [
    "mega и pop проверяют большие журналы; deep-book — другую структуру нагрузки; s001 — накладные расходы на коротком запуске. Контроли: cancel-race и heterogeneous batch.",
    "s001, deterministic-baseline и multilevel-crossing проверяют фиксированную стоимость запуска; mega показывает её амортизацию на большой нагрузке. Контроли: cancel-race, latency-tail и heterogeneous batch. Batch сохраняет исходный Python launcher.",
    "Те же четыре сценария, что у H01: проверка стоимости writer на больших журналах и коротком запуске. Контроли: cancel-race и heterogeneous batch.",
    "mega, horizon-240s, deep-book и cancel-churn-newest проверяют перекрытие записи с симуляцией. Контроли: cancel-race, partial-fill atomicity, coarse-tick ties, s001 и heterogeneous batch. Прототип заранее кодирует шесть неизменяемых колонок первого row group до 1 Mi строк; msg_type завершает после Sim.",
]
lines = [
    "Executive summary: Four changes were implemented separately and tested against the same frozen C++ simulator. The tables show complete container time for every selected workload. All correctness checks passed; results are local, and no candidate was merged into production.",
    "",
    "Каждая гипотеза имеет отдельную ветку, worktree и чат. Baseline: `" + plan["base_commit"] + "`. На гипотезу: четыре заранее выбранных сценария, один прогрев каждой стороны и пять пар AB/BA. Всего 160 timed samples и 32 warmup; дополнительно 56 финальных correctness-контейнеров до измерений.",
    "",
    "Процент в таблицах — **сокращение полного времени**: `100 × (1 − median(candidate) / median(baseline))`. Плюс означает быстрее, минус — замедление. Множитель скорости — `median(baseline) / median(candidate)`; это другая величина. Например, сокращение времени на 50% соответствует 2× скорости.",
    "",
    "Основная метрика берётся из Docker StartedAt/FinishedAt. Лимиты: 4 CPU, 16 GiB RAM и swap cap 16 GiB, network=none. Сборки, серии измерений и существенная обработка данных выполнялись последовательно через общий lock. Все пары и выбросы сохранены; повторного подбора параметров по результатам не было.",
    "",
    "| Гипотеза | Диапазон сокращения времени на назначенных сценариях | Отчёт |",
    "|---|---:|---|",
]
summary = []
for number, (exp, checked) in enumerate(zip(plan["experiments"], audit["experiments"]), 1):
    values = [x["time_reduction_pct"] for x in checked["results"]]
    lines.append(f"| {number}. {names[number-1]} | {min(values):+.2f}% … {max(values):+.2f}% | [{exp['slug']}]({exp['slug']}/README.md) |")
    summary.append({"slug": exp["slug"], "min_time_reduction_pct": min(values),
        "max_time_reduction_pct": max(values), "results": checked["results"]})
lines += ["", "Диапазоны описывают разные кейсы; они не являются средним ускорением и не служат сравнительным рейтингом гипотез.", "",
    "По согласованности пар приоритетны H02 для коротких запусков (44.17–46.95% сокращения времени, примерно 1.8–1.9× скорости; 5/5, 5/5 и 4/5 пар) и H01 для mega/pop (8.25% и 20.32%, по 5/5 пар). H03 не подтвердил устойчивый выигрыш: положительные результаты лишь в 3/5 пар, а s001 медленнее во всех пяти. H04 перспективен на deep-book (4/5), но в остальных трёх случаях быстрее только 2/5. Кратного ускорения всех крупных сценариев эти четыре реализации не дали.", "",
    "| Гипотеза | Сценарий | Baseline, ms | Candidate, ms | Сокращение времени | Скорость, × | Быстрее в парах |",
    "|---|---|---:|---:|---:|---:|---:|"]
for number, checked in enumerate(audit["experiments"], 1):
    for row in checked["results"]:
        b, c = row["median_seconds"]["baseline"], row["median_seconds"]["candidate"]
        lines.append(f"| H{number:02d} | `{row['unit']}` | {b*1000:.2f} | {c*1000:.2f} | {row['time_reduction_pct']:+.2f}% | {b/c:.3f} | {row['faster_pairs']}/5 |")
lines += ["", "При оценке устойчивости смотрите на число выигранных пар вместе с медианой. Выигрыш только в 3/5 пар не подтверждает устойчивый эффект, даже при заметном медианном проценте.", ""]
for number, (exp, checked) in enumerate(zip(plan["experiments"], audit["experiments"]), 1):
    lines += [f"**H{number:02d}. {names[number-1]}.** {selection[number-1]}", "",
        f"Ветка: `{exp['branch']}`. Измеренный commit: `{checked['candidate_commit']}`. Worktree: `{exp['worktree']}`. Chat: `{exp['thread_id']}`.", "",
        f"[Итоговый JSON]({exp['slug']}/result.json), [изменения кода]({exp['slug']}/implementation.patch), [подробный отчёт]({exp['slug']}/README.md).", ""]
lines += [
    "H01/H03 сохраняют полную схему с metadata, null, все значения и порядок обоих журналов; физические байты Parquet могут отличаться. H02/H04 дополнительно совпадают по байтам. Собственные SHA-256 привязаны к каждому реальному файлу. Shared scorer, cards, tolerances и исходный differential checker не изменялись. Native execution проверен в каждом market.", "",
    "[Manager audit](manager-audit.json) независимо проверяет frozen source hashes, все 160 timed samples, AB/BA-порядок, формулы и SHA-256 сохранённых журналов. [Baseline audit](baseline-audit.json) связывает исходный образ с frozen sources и pinned runtime. [План](plan.json) содержит выбранные сценарии и политику до замеров.", "",
    "Ограничение: это Mac ARM с Linux/amd64 emulation, `rankable: false`. Между сериями меняется абсолютное время baseline; выводы относятся к свежим парам внутри каждой серии. Эти цифры нельзя переносить на официальный x86 timing instance без повторной проверки. Native core clocks включают backpressure и trace finalization, поэтому не являются изолированным временем matcher.", "",
    "В частности, baseline deep-book в H04 колебался от 0.682 до 1.489 с; остаток Docker-времени вне измеряемого адаптера — от 0.302 до 0.896 с. Поэтому медианный выигрыш 36.35% требует осторожной интерпретации. Вторичные clocks показывают уменьшение median parquet_write с 0.245 до 0.150 с при близком simulation_and_trace_finalize (0.265 против 0.259 с), но эти фазы являются отдельными диагностическими метриками, и их медианы нельзя складывать для точной атрибуции общего процента.", "",
    "Все исходные результаты и логи, включая неудачные предварительные попытки, сохранены. Во время подготовки тестов заполнение диска потребовало удаления воспроизводимых synthetic fixtures после сохранения hashes/outcomes. Ошибочная hardlink-дедупликация corpus была полностью отменена до timing: файлы восстановлены как отдельные APFS clones, manifest/firewall заново прошли без обхода проверок. Измеренные outputs также остаются обычными файлами с отдельными inode.", "",
    "Production baselines не менялись: реализации остались в отдельных экспериментальных ветках."
]
(target / "README.md").write_text("\n".join(lines) + "\n")
(target / "report-summary.json").write_text(json.dumps({"executive_summary": "Scenario-specific reductions in complete container time; no pooled ranking is implied.", "accepted": True, "rankable": False, "hypotheses": summary}, ensure_ascii=False, indent=2) + "\n")
print(str(target / "README.md"))
