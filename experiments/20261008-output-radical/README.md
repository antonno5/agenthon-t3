Executive summary: Four changes were implemented separately and tested against the same frozen C++ simulator. The tables show complete container time for every selected workload. All correctness checks passed; results are local, and no candidate was merged into production.

Каждая гипотеза имеет отдельную ветку, worktree и чат. Baseline: `ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5`. На гипотезу: четыре заранее выбранных сценария, один прогрев каждой стороны и пять пар AB/BA. Всего 160 timed samples и 32 warmup; дополнительно 56 финальных correctness-контейнеров до измерений.

Процент в таблицах — **сокращение полного времени**: `100 × (1 − median(candidate) / median(baseline))`. Плюс означает быстрее, минус — замедление. Множитель скорости — `median(baseline) / median(candidate)`; это другая величина. Например, сокращение времени на 50% соответствует 2× скорости.

Основная метрика берётся из Docker StartedAt/FinishedAt. Лимиты: 4 CPU, 16 GiB RAM и swap cap 16 GiB, network=none. Сборки, серии измерений и существенная обработка данных выполнялись последовательно через общий lock. Все пары и выбросы сохранены; повторного подбора параметров по результатам не было.

| Гипотеза | Диапазон сокращения времени на назначенных сценариях | Отчёт |
|---|---:|---|
| 1. Дешёвое кодирование Parquet | -9.04% … +23.06% | [h01-parquet-encoding](h01-parquet-encoding/README.md) |
| 2. Standalone native executable | +10.15% … +46.95% | [h02-native-executable](h02-native-executable/README.md) |
| 3. Специализированный Parquet writer | -14.15% … +23.66% | [h03-specialized-writer](h03-specialized-writer/README.md) |
| 4. Конвейер lifecycle trace | +1.18% … +36.35% | [h04-lifecycle-pipeline](h04-lifecycle-pipeline/README.md) |

Диапазоны описывают разные кейсы; они не являются средним ускорением и не служат сравнительным рейтингом гипотез.

По согласованности пар приоритетны H02 для коротких запусков (44.17–46.95% сокращения времени, примерно 1.8–1.9× скорости; 5/5, 5/5 и 4/5 пар) и H01 для mega/pop (8.25% и 20.32%, по 5/5 пар). H03 не подтвердил устойчивый выигрыш: положительные результаты лишь в 3/5 пар, а s001 медленнее во всех пяти. H04 перспективен на deep-book (4/5), но в остальных трёх случаях быстрее только 2/5. Кратного ускорения всех крупных сценариев эти четыре реализации не дали.

| Гипотеза | Сценарий | Baseline, ms | Candidate, ms | Сокращение времени | Скорость, × | Быстрее в парах |
|---|---|---:|---:|---:|---:|---:|
| H01 | `t3-gb-mega-throughput` | 1373.32 | 1259.95 | +8.25% | 1.090 | 5/5 |
| H01 | `t3-gb-pop-horizon-scale` | 1110.08 | 884.52 | +20.32% | 1.255 | 5/5 |
| H01 | `t3-mr-deep-book-state-size` | 619.16 | 476.38 | +23.06% | 1.300 | 3/5 |
| H01 | `t3-s001-price-time-priority` | 337.76 | 368.28 | -9.04% | 0.917 | 2/5 |
| H02 | `t3-s001-price-time-priority` | 420.83 | 233.07 | +44.62% | 1.806 | 5/5 |
| H02 | `t3-eq-deterministic-baseline` | 393.51 | 219.68 | +44.17% | 1.791 | 5/5 |
| H02 | `t3-multilevel-crossing` | 541.64 | 287.36 | +46.95% | 1.885 | 4/5 |
| H02 | `t3-gb-mega-throughput` | 1682.51 | 1511.68 | +10.15% | 1.113 | 3/5 |
| H03 | `t3-gb-mega-throughput` | 1567.74 | 1624.09 | -3.59% | 0.965 | 3/5 |
| H03 | `t3-gb-pop-horizon-scale` | 1362.45 | 1040.06 | +23.66% | 1.310 | 3/5 |
| H03 | `t3-mr-deep-book-state-size` | 880.32 | 711.78 | +19.15% | 1.237 | 3/5 |
| H03 | `t3-s001-price-time-priority` | 331.89 | 378.86 | -14.15% | 0.876 | 0/5 |
| H04 | `t3-gb-mega-throughput` | 1728.61 | 1708.20 | +1.18% | 1.012 | 2/5 |
| H04 | `t3-gb-horizon-240s` | 998.87 | 943.13 | +5.58% | 1.059 | 2/5 |
| H04 | `t3-mr-deep-book-state-size` | 1184.25 | 753.81 | +36.35% | 1.571 | 4/5 |
| H04 | `t3-mp05-cancel-churn-newest` | 712.18 | 625.83 | +12.13% | 1.138 | 2/5 |

При оценке устойчивости смотрите на число выигранных пар вместе с медианой. Выигрыш только в 3/5 пар не подтверждает устойчивый эффект, даже при заметном медианном проценте.

**H01. Дешёвое кодирование Parquet.** mega и pop проверяют большие журналы; deep-book — другую структуру нагрузки; s001 — накладные расходы на коротком запуске. Контроли: cancel-race и heterogeneous batch.

Ветка: `codex/exp-20261008-output-h01-parquet-encoding`. Измеренный commit: `fc1fff3ac35152577a4fb4cabd5197dd596325d3`. Worktree: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-output-radical/worktrees/h01-parquet-encoding`. Chat: `01a11bdf-cd99-7c02-b920-439c2b3f9ae5`.

[Итоговый JSON](h01-parquet-encoding/result.json), [изменения кода](h01-parquet-encoding/implementation.patch), [подробный отчёт](h01-parquet-encoding/README.md).

**H02. Standalone native executable.** s001, deterministic-baseline и multilevel-crossing проверяют фиксированную стоимость запуска; mega показывает её амортизацию на большой нагрузке. Контроли: cancel-race, latency-tail и heterogeneous batch. Batch сохраняет исходный Python launcher.

Ветка: `codex/exp-20261008-output-h02-native-executable`. Измеренный commit: `a91b789ef63f7bb0a70e7a734e5657a999b90c10`. Worktree: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-output-radical/worktrees/h02-native-executable`. Chat: `01a11bdf-d1a7-7410-9fd1-4faa7d3ac27c`.

[Итоговый JSON](h02-native-executable/result.json), [изменения кода](h02-native-executable/implementation.patch), [подробный отчёт](h02-native-executable/README.md).

**H03. Специализированный Parquet writer.** Те же четыре сценария, что у H01: проверка стоимости writer на больших журналах и коротком запуске. Контроли: cancel-race и heterogeneous batch.

Ветка: `codex/exp-20261008-output-h03-specialized-writer`. Измеренный commit: `aa1d514e1aeb219f9d5633462b4bdbe616b63eea`. Worktree: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-output-radical/worktrees/h03-specialized-writer`. Chat: `01a11bdf-d64e-7f42-80fe-a9ce585e9b9f`.

[Итоговый JSON](h03-specialized-writer/result.json), [изменения кода](h03-specialized-writer/implementation.patch), [подробный отчёт](h03-specialized-writer/README.md).

**H04. Конвейер lifecycle trace.** mega, horizon-240s, deep-book и cancel-churn-newest проверяют перекрытие записи с симуляцией. Контроли: cancel-race, partial-fill atomicity, coarse-tick ties, s001 и heterogeneous batch. Прототип заранее кодирует шесть неизменяемых колонок первого row group до 1 Mi строк; msg_type завершает после Sim.

Ветка: `codex/exp-20261008-output-h04-lifecycle-pipeline`. Измеренный commit: `3cb8784279483ce8ba7206d937ee2fddd109f786`. Worktree: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-08-output-radical/worktrees/h04-lifecycle-pipeline`. Chat: `01a11bdf-d993-7830-b9af-23de3240d67d`.

[Итоговый JSON](h04-lifecycle-pipeline/result.json), [изменения кода](h04-lifecycle-pipeline/implementation.patch), [подробный отчёт](h04-lifecycle-pipeline/README.md).

H01/H03 сохраняют полную схему с metadata, null, все значения и порядок обоих журналов; физические байты Parquet могут отличаться. H02/H04 дополнительно совпадают по байтам. Собственные SHA-256 привязаны к каждому реальному файлу. Shared scorer, cards, tolerances и исходный differential checker не изменялись. Native execution проверен в каждом market.

[Manager audit](manager-audit.json) независимо проверяет frozen source hashes, все 160 timed samples, AB/BA-порядок, формулы и SHA-256 сохранённых журналов. [Baseline audit](baseline-audit.json) связывает исходный образ с frozen sources и pinned runtime. [План](plan.json) содержит выбранные сценарии и политику до замеров.

Ограничение: это Mac ARM с Linux/amd64 emulation, `rankable: false`. Между сериями меняется абсолютное время baseline; выводы относятся к свежим парам внутри каждой серии. Эти цифры нельзя переносить на официальный x86 timing instance без повторной проверки. Native core clocks включают backpressure и trace finalization, поэтому не являются изолированным временем matcher.

В частности, baseline deep-book в H04 колебался от 0.682 до 1.489 с; остаток Docker-времени вне измеряемого адаптера — от 0.302 до 0.896 с. Поэтому медианный выигрыш 36.35% требует осторожной интерпретации. Вторичные clocks показывают уменьшение median parquet_write с 0.245 до 0.150 с при близком simulation_and_trace_finalize (0.265 против 0.259 с), но эти фазы являются отдельными диагностическими метриками, и их медианы нельзя складывать для точной атрибуции общего процента.

Все исходные результаты и логи, включая неудачные предварительные попытки, сохранены. Во время подготовки тестов заполнение диска потребовало удаления воспроизводимых synthetic fixtures после сохранения hashes/outcomes. Ошибочная hardlink-дедупликация corpus была полностью отменена до timing: файлы восстановлены как отдельные APFS clones, manifest/firewall заново прошли без обхода проверок. Измеренные outputs также остаются обычными файлами с отдельными inode.

Production baselines не менялись: реализации остались в отдельных экспериментальных ветках.
