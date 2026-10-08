This experiment reduced complete container time by 8.25%, 20.32% and 23.06% on the three assigned large scenarios; the small price-time scenario slowed by 9.04%. Both decoded journals and their full schemas remain exact. The two largest outputs grew by about 5–6%, while the other outputs shrank. All fixed samples were retained. Results are local and non-rankable; no production adoption is made.

## Итог полного прогона

Замороженная измеренная реализация: `fc1fff3ac35152577a4fb4cabd5197dd596325d3` (writer реализация `21edc27231f4e0052d0bf19734cb09855e639f37`). Baseline source: `ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5`.

Единственная серия: 48 принятых запусков, включая 8 исключённых прогревов и 40 timing samples. Для каждого unit — один warmup каждой стороны и ровно пять пар AB/BA/AB/BA/AB. Все выбросы сохранены, повторов и tuning после просмотра скорости не было. Primary clock — Docker FinishedAt − StartedAt, включая полный процесс с startup, simulation, обоими файлами и hashing. Плюс означает ускорение: `100 × (1 − median(candidate) / median(baseline))`.

| Сценарий | Baseline, с | Candidate, с | Ускорение / замедление | Быстрее в парах |
|---|---:|---:|---:|---:|
| `t3-gb-mega-throughput` | 1.373318 | 1.259954 | **+8.25%** | 5/5 |
| `t3-gb-pop-horizon-scale` | 1.110080 | 0.884522 | **+20.32%** | 5/5 |
| `t3-mr-deep-book-state-size` | 0.619163 | 0.476379 | **+23.06%** | 3/5 |
| `t3-s001-price-time-priority` | 0.337758 | 0.368280 | **-9.04%** | 2/5 |

На mega и pop candidate быстрее во всех пяти парах. На deep-book — в трёх из пяти: большой размах samples сохраняется в отчёте и ограничивает уверенность в размере эффекта. На s001 быстрее лишь в двух парах; гипотеза не даёт общего ускорения для малых заданий. Это наблюдение выбранного набора, без переноса на остальные units.

## Размеры и hashes

Сумма `trace.parquet` + `message_trace.parquet` для полного запуска; положительный размерный процент означает больший файл.

| Сценарий | Baseline, bytes | Candidate, bytes | Изменение размера |
|---|---:|---:|---:|
| `t3-gb-mega-throughput` | 45,151,309 | 47,399,337 | +4.98% |
| `t3-gb-pop-horizon-scale` | 28,021,166 | 29,758,978 | +6.20% |
| `t3-mr-deep-book-state-size` | 9,999,080 | 9,030,059 | -9.69% |
| `t3-s001-price-time-priority` | 37,167 | 34,859 | -6.21% |

Physical bytes/hashes изменились для обоих journals во всех четырёх измеряемых units. Все decoded values и schemas с metadata остались точными. [output-size-hashes.json](output-size-hashes.json) хранит отдельные размеры, rows, row groups, каждый SHA-256 и его проверенные пути; hashes каждого собственного файла совпали с events и свежим control на всех прогревах и samples. Передача `side`/`msg_type` через dictionary и выключенная статистика проверены отдельными pinned writer fixtures. Числовые колонки больше не строят dictionary.

## Проверки и вторичные clocks

[validation.json](validation.json): pinned Arrow15 — 114 fixture comparisons, normal + ASan/UBSan; оба journals точны по схемам с metadata и ordered values. Sanitizers покрывают собственные sources, а не готовые Arrow libraries. Shared controls: 12 контейнеров на шести units, 20 actual native market executions, все developer gates прошли. Timing: 48 native контейнеров, 24 baseline/candidate сравнения и ещё 40 проверок repeat stability. Всего 136 собственных journal digests проверены runner. Host monotonic intervals всех controls и series не пересекаются. Source hashes и runner freeze сохранились.

Без дополнительной profile-серии использованы existing profile phase clocks. Это диагностические process clocks, не основной Docker clock и не standalone benchmark writer.

| Сценарий | Parquet phase baseline → candidate, с | Core/finalize baseline → candidate, с | Hashing baseline → candidate, с |
|---|---:|---:|---:|
| `t3-gb-mega-throughput` | 0.307333 → 0.240313 | 0.589839 → 0.487677 | 0.157024 → 0.152724 |
| `t3-gb-pop-horizon-scale` | 0.294234 → 0.215661 | 0.329245 → 0.248403 | 0.105822 → 0.105346 |
| `t3-mr-deep-book-state-size` | 0.144309 → 0.081602 | 0.141216 → 0.114343 | 0.038801 → 0.032014 |
| `t3-s001-price-time-priority` | 0.067460 → 0.068664 | 0.005213 → 0.004877 | 0.003206 → 0.002583 |

Core включает simulation, lifecycle finalization и ledger backpressure; Parquet phase включает оставшуюся запись/close/finish после simulation. Поэтому фазы не изолируют стоимость одного encoding вызова и их медианы нельзя складывать в primary clock. Все phase samples сохранены в [result.json](result.json), без отдельного повторного profiling.

Среда: Mac ARM64, эмуляция linux/amd64 в colima-agenthon, 4 CPUs, memory 16g, memory+swap 16g, network none. Это локальный `rankable:false` эксперимент, не официальное timing hardware. Пять samples дают описательные медианы; официального статистического вывода о размере эффекта нет. Source/tests/scripts/image не менялись в измеренной серии.

Baseline image: `sha256:e96d4ea0b819cdf88eb9dde55a6a61d59eefd2247df88139ab0cda03ca0ba1d2`. Candidate: `sha256:81cbb6b1ca47c83743669b66746448afc5739b9e6c2cd6028aa33450a31e996a`. [preflight.json](preflight.json) содержит frozen identity, dependency versions и extension digests; полный build/audit evidence сохранён под `evidence/preflight`.

Первая build попытка отклонена BuildKit из-за FROM image IDs, до компиляции; исправление только рецепта с проверкой cached tags против immutable IDs. После series отчёт сначала ошибочно ожидал 24 comparison records; checker сохраняет ещё 40 stability checks, отчёт исправлен. Обе ошибки/исправления сохранены; timing не повторялся.

Результат гипотезы: полезное ускорение на крупных выбранных workloads с небольшим ростом storage для двух из них; малый s001 замедлился. Универсальная production adoption не выполняется. Merge/push, scorer/card/tolerance changes и all-public/regression65 отсутствуют.

Raw/retained testcase outputs, каждое событие проверки, logs и все samples остаются под ignored `evidence/`. Shared runner сохраняет byte-identical закрытые outputs через отдельные APFS clones с nlink=1. Удалены только воспроизводимые завершённые synthetic fixture Parquet/test binaries; summaries, hashes и logs сохранены. Frozen source/recipe policy описана ниже.

## Изменение

Общая база: `ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5`; ветка: `codex/exp-20261008-output-h01-parquet-encoding`.

В `baselines/native/pqwrite.cpp` меняются только WriterProperties общего `open_writer`: dictionary выключен по умолчанию и включён для `msg_type`/`side`; statistics выключены. Кодек остаётся Snappy: он уже доступен в закреплённой библиотеке и уменьшает I/O без затрат более тяжёлого кодека. Numeric columns получают plain encoding без построения и возможного fallback dictionary. Выбор основан на структуре колонок, без перебора сценарных замеров. Политика зафиксирована в [encoding-policy.json](encoding-policy.json) до timing.

Схемы, pandas/Arrow metadata, nullable columns, порядок значений, row groups по 1 048 576 строк, blocks по 65 536 строк, encoder pool из двух workers и staged publication сохраняются. Изменение hash физических файлов ожидается; каждый events digest должен соответствовать собственному файлу. Заголовок pqwrite.hpp обновлён, поскольку обещание byte equality для H01 уже неприменимо. Нового writer, native launcher и scoring gates нет.

## Проверки Phase 1

[host-checks.json](host-checks.json): Python 3.13.3 / Arrow 25.0.1 / macOS ARM64. Это предварительная проверка, а не подтверждение pinned Arrow15.

- 114 сравнений fixtures, включая 76 candidate normal/ASan/UBSan: schema metadata и ordered decoded values совпали с замороженной базой.
- Проверены codec Snappy, dictionary только для type/side, отсутствие statistics, размеры row groups, mixed/all/no nulls, INT64_MIN/MAX, поздние новые типы вокруг границ 1024/65536, row groups 1Mi и более двух групп.
- Проверены concurrent lifecycle/message encoding через реальный MessagePipeline, full-table и streaming values, неправильные append/offset/partial/closed boundaries и malformed input.
- Empty writer errors Arrow25 совпали с исходной базой и сохранены в evidence; binding штатно обрабатывает пустые lifecycle результаты. Это существующее поведение, не failure реализации. Неожиданных ошибок: 0.
- ASan/UBSan проверили собственные C++ sources; поставляемые Arrow libraries не инструментированы.

Полные commands, исходная версия checker, логи и checks находятся в `evidence/host-01/` и исключены из Git. После завершения проверки синтетические Parquet и test binaries удалены по запросу координатора из-за заполнения диска; их hashes и outcomes сохранены в checks и [storage-compaction.json](storage-compaction.json). Освобождено около 534 MiB, evidence уменьшен с 535 MiB до 572 KiB. Fixtures полностью восстанавливаются из committed tests; реальных testcase outputs в Phase 1 нет. После проверки checker переведён с runtime git-show на byte-identical snapshots writer из base commit, чтобы pinned Docker не зависел от host worktree metadata; соответствие snapshot bytes, hashes остальных native sources и py_compile проверены. Замороженные snapshots и manifest находятся в `tests/`.

Повтор host-проверки из worktree:

```sh
'/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python' experiments/20261008-output-radical/h01-parquet-encoding/tests/check.py --host --out experiments/20261008-output-radical/h01-parquet-encoding/evidence/host-new
```

## Протокол Phase 2

[Dockerfile](Dockerfile) использует cached baseline/runtime и builder tags из общего plan; их соответствие immutable IDs проверяется до и после build под одним lock. Первая попытка FROM image ID отклонена BuildKit до компиляции; исходный лог сохранён в evidence/preflight/build.log, рецепт исправлен без изменения writer. [recipe.json](recipe.json) содержит точные build и pinned-check argv. Любая Docker команда и весь shared runner запускаются через общий `docker_slot.py` с exclusive lock на весь subprocess. Build, pinned checks, controls и единственная timing-серия завершены.

Timing units: `t3-gb-mega-throughput`, `t3-gb-pop-horizon-scale`, `t3-mr-deep-book-state-size`, `t3-s001-price-time-priority`.

Correctness-only: `t3-s012-partial-fill-cancel-race`, `t3-gbatch-hetero-mix`.

Pinned writer tests и shared controls прошли до timing. Оба журнала требуют полного schema equality с metadata и всех ordered decoded values; unchanged shared developer gates и actual native execution проверяются для каждого рынка. Physical byte equality между sides не требуется; собственные file digests обязательны.

Полный прогон измеряется Docker FinishedAt − StartedAt: один исключённый warmup каждой стороны, ровно пять пар AB/BA/AB/BA/AB, все samples/outliers остаются. Проценты: `100 × (1 − median(candidate) / median(baseline))`, плюс означает быстрее. Component profile clocks вторичны. Диагностика ограничена существующими фазами, physical encoding metadata и полными размерами/hashes обоих файлов; дополнительные timing series и настройка по увиденной скорости не планируются.

Среда Phase 2: colima-agenthon, linux/amd64, 4 CPUs, memory 16g, memory+swap 16g, network none. Результаты локальные, `rankable:false`. Full public/regression65 не запускаются; production adoption/merge/push не выполняются.
