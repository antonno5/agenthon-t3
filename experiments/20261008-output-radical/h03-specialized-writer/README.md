Executive summary: the fixed-schema writer passed pinned correctness and all selected developer gates. Complete-container median time reductions were mega-throughput -3.59%, pop-horizon-scale +23.66%, deep-book-state-size +19.15%, and price-time-priority -14.15%. Two improvements and two regressions show a workload-dependent result. Exactly five paired runs per scenario and every outlier were retained. These local ARM-host/emulated-amd64 measurements are non-rankable; no production adoption occurred.

# H03 — специализированный writer

Общая база: `ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5`.
Изолированная ветка: `codex/exp-20261008-output-h03-specialized-writer`.
Изменены только `baselines/native/pqwrite.cpp` и комментарий контракта в
`pqwrite.hpp`. Simulation, RNG, matching, запуск процесса, module.cpp,
MessagePipeline и параметры сценариев не изменены.

## Что делает реализация

Writer открывает низкоуровневый `ParquetFileWriter` с двумя фиксированными
схемами: 7 полей lifecycle trace и 10 полей message ledger. Нет подготовки
числовых Arrow Array/ArrayData, Table, RecordBatch или Slice и нет общего
обхода Arrow-колонок перед каждой записью. Числовые векторы передаются напрямую
в `Int32Writer`/`Int64Writer`. Для nullable int64 собираются definition levels
и компактные значения в stack-буферах размером 1024. Последовательность `seq`
создаётся такими же ограниченными блоками, без полного временного вектора.

Три словаря — 6 trace типов, 2 стороны и 13 ledger типов — строятся один раз
на процесс. Целочисленные коды преобразуются в int32 индексы без копирования
строк, поиска строк или вставки каждого имени в словарь. Узкий интерфейс
`ColumnWriter::WriteArrow` получает DictionaryArray: небольшие Arrow-обёртки
индексов и заранее подготовленный словарь остаются только здесь. Это не
полностью независимый от Arrow writer: Arrow также сохраняет схемы через IPC.
Строковые поля публичной схемы остаются обычными `string`, не dictionary type.
Схема полей, nullable, порядок и pandas/ARROW:schema metadata сохраняются.

Словарь передаётся целиком в начале row group, включая неиспользованные имена.
Поэтому порядок dictionary entries, стартовая ширина индексов, страницы,
статистика и физические байты могут отличаться от baseline. Snappy, Parquet 2.6,
V1 pages, statistics и границы row group 1,048,576 строк сохраняются.
В отличие от старого опыта с ByteArray для каждой строки, h03 исключает
повторный строковый hashing в dictionary encoder.

Один process-wide pool содержит ровно два encoding worker. В каждом buffered
row group разные колонки кодируются параллельно; trace writer и message dispatcher
используют тот же pool. Все задачи join-ятся до освобождения входного блока,
включая случай ошибки одного worker. Вложенного ожидания внутри pool нет.
MessagePipeline по-прежнему имеет producer и максимум два queued/writing буфера.
Дополнительные индексы/definition levels enum-колонки ограничены 64K строками;
числовые scratch-буферы ограничены 1024 строками. Callback завершает запись
до повторного использования буфера producer.

Перед записью проверяются длины всех векторов и допустимость enum-кодов.
Сохраняются проверки block offset, размера, последнего partial block,
записи после close и повторного close. Пустой файл имеет корректную фиксированную
схему и ноль row groups; module.cpp по-прежнему обрабатывает пустые lifecycle
симуляции до вызова writer.

## Проверки и воспроизводимость

`run_checks.py` извлекает настоящий baseline writer из frozen Git commit и
компилирует baseline и candidate с одним C++ fixture. Сравнение использует
PyArrow для точной схемы с metadata и всех ordered decoded values обоих журналов.
Дополнительно сравниваются table/stream варианты ledger. Это проверка writer,
не копия scoring gates. Проверяются 0, 1, 1023/1024/1025, 65535/65536/65537,
1048575/1048576/1048577 и 2098689 строк, позднее появление имён, all-null/no-null/mixed
nullable поля, отрицательные и крайние int32/int64 значения, ошибки длины,
enum и block boundary. Fixtures одновременно пишут trace и ledger через реальный
bounded pipeline. Отдельный существующий `pipeline_test.cpp` проверяет
backpressure, cancellation и передачу write/close ошибок.

На host: Python 3.13.3, Arrow 25.0.1, macOS ARM64, C++20. У baseline Arrow25
отклоняет собственные пустые UTF8 views; в этом одном diagnostic случае пустая
схема сравнивается с zero-row slice реального непустого baseline файла.
Для production обязательна отдельная проверка pinned Arrow 15.0.2/C++17.
Host результаты не заменяют её.

```sh
PY='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
"$PY" experiments/20261008-output-radical/h03-specialized-writer/run_checks.py \
  --out experiments/20261008-output-radical/h03-specialized-writer/evidence/host-final
"$PY" experiments/20261008-output-radical/h03-specialized-writer/run_checks.py --sanitize \
  --out experiments/20261008-output-radical/h03-specialized-writer/evidence/host-sanitized
```

Изначальные неудачи сохранены: attempt01 — неверное неверсированное имя dylib;
attempt02 — попытка проверить void-результат metadata.Append; attempt03 — ENOSPC
после успешной записи 1Mi строк. Исправлены build helper, вызов Append и retention
host fixtures. Attempt04 прошёл до добавления extreme-value fixture и явных
include. Полные логи сохранены под `evidence/`, хеши удалённых временных файлов —
в `discarded-fixture-hashes.json`. Успешные синтетические Parquet удаляются после
сравнения каждого граничного случая; summary сохраняет их собственные SHA256.
Это снижает пиковое место на диске. Реальные scenario outputs не удаляются.

## Frozen phase 2 policy

Timing units: `t3-gb-mega-throughput`, `t3-gb-pop-horizon-scale`,
`t3-mr-deep-book-state-size`, `t3-s001-price-time-priority`.
Correctness only: `t3-s012-partial-fill-cancel-race`, `t3-gbatch-hetero-mix`.
Остальные units, all-public и regression65 не запускаются.

Каждый Docker build/check/run выполняется под общим exclusive `docker_slot.py`.
Контекст colima-agenthon, linux/amd64, 4 CPUs, memory=16g, memory-swap=16g,
network none. Dockerfile наследует frozen baseline runtime и cached builder;
при build передаются immutable image IDs из `BASELINE_READY.json` через
BASE_IMAGE/BUILDER_IMAGE. Собирается только extension из этой ветки, runtime
получает только новый `_t3engine*.so`. Startup не меняется.

До timing: pinned probe с `--prepared --require-pinned`, frozen source/image
identities, все selected controls через общий `run_focused.py --controls-only`.
Каждый market обязан подтвердить actual native. Проверяются обе схемы с metadata,
ordered values, собственные file digests и неизменённые shared developer gates.
Требуется semantic exact; равенство физических bytes не требуется.

Для каждого timing unit: один excluded warmup на сторону и ровно 5 пар
AB, BA, AB, BA, AB, каждый control свежий. Все samples/outliers сохраняются,
повторная серия или tuning после просмотра performance запрещены.
Primary clock — Docker FinishedAt minus StartedAt; процент:
`100*(1-median(candidate)/median(baseline))`, плюс означает ускорение.
Adapter phase times, file sizes, row-group/encoding diagnostics и hashes —
вторичные показатели; они не заменяют complete container clock.
Результаты локальные `rankable:false`; ветка не merge/push/adopt.

## Готовность фазы 1

Финальные обычный и ASan/UBSan прогоны прошли: по 42 сравнения файлов,
все schemas/metadata/ordered values exact. Проверка существующего pipeline и
`git diff --check` прошли. [host-checks.json](host-checks.json) содержит compact
результаты и хеши исходных логов; [host-final.json](host-final.json) и
[host-sanitized.json](host-sanitized.json) сохраняют digests каждого fixture.
Синтетические бинарники и проверенные временные Parquet удалены; логи, исходники
baseline fixture, summary и recipe сохранены. Docker build, scenario controls
и timing в фазе 1 не запускались.

## Завершённая фаза 2: pinned validation и controls

Production исходники не менялись после коммита
`aa1d514e1aeb219f9d5633462b4bdbe616b63eea`. Образ candidate:
`sha256:ee247fdabbdac307c51d983be703cce5d6b79a3149aa6979dc346040c78571f9`.
Baseline: `sha256:e96d4ea0b819cdf88eb9dde55a6a61d59eefd2247df88139ab0cda03ca0ba1d2`.
Проверенный builder:
`sha256:00d25683712788d34fe00e1a38a952338fa9301d4715bc4b88f91290ca645c5b`.
Build context содержал только native sources и build_native.py; каждый файл
сверен с исходниками этой ветки. Хеши baseline tags проверены до и после build.
Хеш установленного extension совпал с builder output. Runtime audit подтвердил
одинаковые Python 3.11.17, Arrow 15.0.2, numpy 1.26.4, pandas 1.5.3 и scipy 1.17.1.

Обычный и ASan/UBSan pinned C++17 прогоны прошли по 42 точных сравнения.
Для sanitizer использовано `ASAN_OPTIONS=detect_leaks=0`; AddressSanitizer и
UndefinedBehaviorSanitizer включены, LeakSanitizer не запускался.
Затем 12 fresh untimed controls прошли шесть selected units: 20 пар файлов,
20 подтверждённых native market executions, обе полные схемы с metadata,
ordered values, собственные digest declarations и shared developer gates.

Первый controls-attempt остановился до запуска сценариев: coordinator storage
hardlinking нарушил plain-file правила неизменённых manifest/firewall gates.
После восстановления отдельных APFS clones со single-link inode свежий
controls-attempt прошёл. Этот сбой и логи сохранены под `evidence/phase2-attempt01/`;
успешные controls — под `evidence/phase2-controls-attempt02/`.
Checker/scorer не менялись и не обходились. Shared runner теперь сохраняет
проверенные одинаковые outputs как APFS clones, сохраняя plain-file contract.

## Единственная timing-серия

Все 48 запусков приняты: 8 excluded warmups и 40 timed samples. Для каждого
сценария — baseline/candidate warmup и ровно пять пар AB, BA, AB, BA, AB.
Проверены все собственные hashes, developer gates и actual-native provenance;
все межсторонние schema/metadata/ordered-value сравнения прошли.
Source fingerprint остался неизменным. Повторных замеров, tuning и удаления
outliers не было. Вся серия держала общий Docker exclusive lock.

Primary clock: Docker FinishedAt minus StartedAt. Процент:
`100*(1-median(candidate)/median(baseline))`; плюс — ускорение, минус — замедление.
Медианы в таблице округлены до 6 знаков; JSON сохраняет полную точность.

| Unit | Baseline median (s) | Candidate median (s) | Полный прогон (%) | Быстрее в парах |
| --- | ---: | ---: | ---: | ---: |
| t3-gb-mega-throughput | 1.567736 | 1.624086 | -3.59 | 3/5 |
| t3-gb-pop-horizon-scale | 1.362450 | 1.040056 | +23.66 | 3/5 |
| t3-mr-deep-book-state-size | 0.880315 | 0.711775 | +19.15 | 3/5 |
| t3-s001-price-time-priority | 0.331893 | 0.378856 | -14.15 | 0/5 |

### Все primary-clock samples

| Unit | Side | Samples в порядке pair index (s) |
| --- | --- | --- |
| t3-gb-mega-throughput | baseline | 1.427739129, 1.897824724, 1.707164338, 1.486815530, 1.567736316 |
| t3-gb-mega-throughput | candidate | 1.624086217, 1.658700743, 1.538814399, 1.754595431, 1.227936915 |
| t3-gb-pop-horizon-scale | baseline | 1.568122084, 0.773230823, 1.555025420, 0.987325476, 1.362449645 |
| t3-gb-pop-horizon-scale | candidate | 1.625165960, 1.267665309, 1.040056377, 0.902043415, 0.839774616 |
| t3-mr-deep-book-state-size | baseline | 0.986891137, 0.571321679, 0.945881456, 0.880315342, 0.566180147 |
| t3-mr-deep-book-state-size | candidate | 0.693958189, 0.711775180, 0.672939543, 0.789513599, 1.017591469 |
| t3-s001-price-time-priority | baseline | 0.306434908, 0.331892843, 0.337544499, 0.354838380, 0.291527348 |
| t3-s001-price-time-priority | candidate | 0.366030513, 0.394645936, 0.458773995, 0.378855781, 0.324827978 |

### Исключённые warmups

| Unit | Baseline (s) | Candidate (s) |
| --- | ---: | ---: |
| t3-gb-mega-throughput | 1.285876826 | 1.405272157 |
| t3-gb-pop-horizon-scale | 1.258460863 | 1.384075211 |
| t3-mr-deep-book-state-size | 0.740003745 | 0.682296182 |
| t3-s001-price-time-priority | 0.474992763 | 0.385176441 |

### Вторичные phase diagnostics

Phases берутся из adapter profile и не заменяют primary clock. Core ниже —
`simulation_and_trace_finalize`: simulation и финализация trace вместе,
не matching-only. `parquet_write` — остаточная writer-фаза после simulation;
часть message encoding уже overlapped с simulation через pipeline.
Нельзя складывать фазы и приписывать весь выигрыш одному writer.

| Unit | Side | Core+finalize (s) | Parquet tail (s) | Hashing (s) |
| --- | --- | ---: | ---: | ---: |
| t3-gb-mega-throughput | baseline | 0.640566 | 0.338700 | 0.166284 |
| t3-gb-mega-throughput | candidate | 0.683303 | 0.240898 | 0.176903 |
| t3-gb-pop-horizon-scale | baseline | 0.367787 | 0.360904 | 0.101209 |
| t3-gb-pop-horizon-scale | candidate | 0.281892 | 0.259274 | 0.106820 |
| t3-mr-deep-book-state-size | baseline | 0.200307 | 0.198989 | 0.048340 |
| t3-mr-deep-book-state-size | candidate | 0.192731 | 0.152226 | 0.041225 |
| t3-s001-price-time-priority | baseline | 0.004659 | 0.068228 | 0.002520 |
| t3-s001-price-time-priority | candidate | 0.004455 | 0.123280 | 0.002661 |

На трёх крупных units median Parquet tail уменьшился. Для mega это не привело
к сокращению primary median: core+finalize и hashing выросли, полный прогон
замедлился на 3.59%, хотя candidate выиграл 3/5 отдельных пар. Для s001 candidate
проиграл все пять пар, median Parquet tail вырос. Для pop-horizon core+finalize
тоже уменьшился, поэтому полный выигрыш нельзя считать только ускорением writer.
Это наблюдения diagnostic фаз, а не доказательство причинности.

### Размер двух журналов

Значения — bytes каждого закрытого файла; во всех пяти samples каждой стороны
размеры идентичны. `diagnostics.json` сохраняет все size samples и phase samples.

| Unit | B trace | C trace | B ledger | C ledger | Δ total bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| t3-gb-mega-throughput | 11699814 | 11699643 | 33451495 | 33451833 | +167 |
| t3-gb-pop-horizon-scale | 7311104 | 7311103 | 20710062 | 20710283 | +220 |
| t3-mr-deep-book-state-size | 2330078 | 2331564 | 7669002 | 7668782 | +1266 |
| t3-s001-price-time-priority | 10242 | 10241 | 26925 | 26934 | +8 |

Физические bytes baseline/candidate различаются в обоих журналах на всех units;
это разрешённая цель h03. Изменение размеров мало относительно размера больших
файлов, и заметное ускорение за счёт меньшего объёма output не установлено.

### Evidence и ограничения

[result.json](result.json) — точная копия standard shared-runner result.
[samples.json](samples.json) сохраняет все 48 samples, Docker timestamps,
phases, digest и размер каждого файла. [diagnostics.json](diagnostics.json)
содержит все size/phase samples. [preflight.json](preflight.json),
[runtime-audits.json](runtime-audits.json), [pinned-normal.json](pinned-normal.json)
и [pinned-sanitized.json](pinned-sanitized.json) связывают validation с образом
и исходниками. [completion.json](completion.json) фиксирует summary/log/recipe
hashes и количество проверок. Полные raw/retained outputs, record/checker JSON,
container stdout/stderr и comparisons сохраняются в `evidence/phase2-timing/`.
Большое evidence игнорируется Git; reports и recipe закоммичены.

Контекст colima-agenthon, linux/amd64, 4 CPUs, memory=16g, memory-swap=16g,
network none. Host — macOS ARM64, amd64 выполняется через эмуляцию.
`rankable:false`: это не официальный fleet timing. Пять пар и четыре selected
units ограничивают обобщение. Реализация и inputs неизменны; положительный
процент на двух cases не доказывает универсального выигрыша. Никакого merge,
push, production adoption или дополнительного performance tuning не сделано.
