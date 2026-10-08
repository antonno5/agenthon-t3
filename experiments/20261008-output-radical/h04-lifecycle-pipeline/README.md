Executive summary: this bounded lifecycle pipeline preserved both journals exactly in all 48 runs of the fixed local timing series. Full-container median time reductions were t3-gb-mega-throughput +1.18%, t3-gb-horizon-240s +5.58%, t3-mr-deep-book-state-size +36.35%, t3-mp05-cancel-churn-newest +12.13%. Positive means faster and negative means slower. The implementation encodes six immutable columns of the first 1 Mi lifecycle row group during Sim and finalizes event types afterwards. These macOS ARM / emulated Linux amd64 results are non-rankable; no production adoption is proposed.


Реализация изолирована на ветке `codex/exp-20261008-output-h04-lifecycle-pipeline`, общий frozen base — `ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5`. Ни corpus, ни scoring gates, ни карточки, ни допуски не менялись. Docker в фазе 1 не запускался; merge/push/production adoption не выполнялись.

`TraceStream` по-прежнему сортирует завершённый timestamp по времени, order id, владельцу и исходному порядку лога. Quote-строки с order id −1 идут первыми, обновления quote одного timestamp остаются последним значением. Сохраняется исходный `last_execution_`: следующая execution демотирует предыдущую в `PARTIAL_FILL`, а последняя сохранённая execution остаётся `ORDER_FILLED`, даже если у заявки остался объём. Отправляемый writer-блок вообще не содержит `msg_type`, поэтому worker не читает данные, которые Sim может изменить.

После каждых 65 536 упорядоченных строк producer передаёт immutable-копию в `TracePipeline`. Два reusable worker-буфера плюс producer-буфер ограничивают добавочную очередь тремя блоками. Writer кодирует timestamp, agent, side, price, size и order id первого row group, включая progressive dictionary fallback и Snappy compression. Полный исходный lifecycle trace сохраняется: его окончательные типы нужны writer в конце, и buffered `_t3engine.run(cfg)` сохраняет старый интерфейс и данные.

Лимит раннего кодирования — **1 048 576 строк**, ровно один исходный row group. Он нужен, чтобы не закрывать group с ещё неизвестным `msg_type` и не накапливать неограниченно много encoded groups. После лимита Sim продолжает обычное накопление lifecycle; producer не ждёт финализации типов. В конце writer дописывает типы первого group, закрывает его и кодирует последующие canonical groups. Поэтому эта версия переносит в Sim кодирование и сжатие immutable-первого-group; физическая запись lifecycle column chunks и footer завершается после Sim. На коротких сценариях без полного блока overlap отсутствует, и проявляются setup/tail costs.

`TraceParquetWriter` использует public `ColumnWriter::WriteArrow`, тот же leaf-entry point, который вызывает Arrow `FileWriter::WriteRecordBatch`. Все lifecycle fields плоские, nullable по исходной схеме, но без null values: definition levels равны 1. Контексты независимы по колонкам; dispatcher находится вне encoder pool. [Arrow 15 writer source](https://raw.githubusercontent.com/apache/arrow/apache-arrow-15.0.2/cpp/src/parquet/arrow/writer.cc) подтверждает этот путь. Перечисление колонок, row groups 1 Mi, write batch 1024, Snappy, dictionary/statistics, Parquet 2.6, V1 pages и pandas/Arrow schema metadata сохраняются. Оба журнала делят один прежний pool на двух workers, дополнительных encoder pools нет.

При отрицательной latency/delay lifecycle handoff отключается, исходная финальная сортировка и buffered writer сохраняются. Для нормального пути lifecycle и ledger записываются в уникальные sibling staging files. Пустой trace возвращает `None` и сохраняет существующие outputs. При исключении dispatcher joined прежде, чем уничтожаются writer, callbacks и staging. Queue-тесты проверяют reuse, backpressure, callback/close exceptions, пробуждение blocked producer и cancellation. Два dispatcher threads могут существовать одновременно; они не исполняют encoding внутри пула и обычно ждут callbacks/буферов.

Host evidence использует macOS ARM, Python 3.13.3 и Arrow 25.0.1. Host Arrow требует C++20; pure queue/trace проверки отдельно прошли с C++17. Pinned build остаётся C++17, Python 3.11, Arrow 15.0.2 и исходные численные флаги `-fno-fast-math -ffp-contract=off`. Test-only ARM numpy-log stub одинаков для baseline/candidate, отсутствует в production и Docker recipe; host-проверка доказывает равенство между двумя native variants, а не соответствие новой платформе official timing.

[Host binding summary](evidence/host-bindings-attempt01/summary.json): s001 даёт 604 lifecycle / 664 ledger rows; s012 — 202 291 / 178 236. Все native buffers, schema с metadata, ordered values и точные байты обоих журналов совпадают с frozen base. Диагностика `lifecycle_pipeline_diagnostics()` на s012 зафиксировала **131 072 immutable rows**, завершённых до выхода из event loop; всего закодировано 202 291 строк четырьмя блоками. На s001 ранних строк 0. Empty, missing-parent-empty, simulation exception и оба writer-error controls прошли; staging-файлы не остаются.

[Host synthetic summary](evidence/host-attempt04/summary.json): 12 пар покрывают 1, 1023, 1024, 1025, 65535, 65536, 65537, 1 Mi−1, 1 Mi, 1 Mi+1, 2 Mi+1537 и late-fill после первого row group. Схемы, metadata, ordered values и rowgroup boundaries совпадают везде; байты совпали у семи пар. Пять крупных Arrow25-пар отличаются из-за добавленного page-row cap. [Test-only page-cap probe](evidence/host-page-cap-attempt01/summary.json) меняет только source snapshot для обеих сторон, поднимая этот cap до 1 Mi: все 12 пар тогда byte-exact. Production properties не менялись. Неподправленный pinned Arrow15 build обязан отдельно пройти строгий byte assert до timing.

Trace boundary tests проверяют стабильные ties и quote overwrites, включая один timestamp, пересекающий 64 Ki block; demotion после более чем 1 Mi строк; `ORDER_FILLED` с остатком; отрицательные timestamps; bounded prefix и реальный worker progress до завершения producer. Queue/trace checks прошли ASan+UBSan. Финальная расширенная tie-проверка также отдельно прошла optimized и sanitized C++17.

Исходные ошибки сохранены. Попытка создания файлов №1 не состоялась из-за `no space left on device`; данных других экспериментов не удаляли. `host-attempt02` содержит C++17 compilation failure на Arrow25; host-only standard исправлен на C++20. `host-attempt03` содержит ошибку нулевого direct writer probe: исходный baseline тоже отвергает пустой string data buffer при `Table::Validate`. Нулевые outputs проверены через поддерживаемый `run_write` empty-path, не через недостижимый для него прямой writer. Production empty handling не менялось. Ранние failed logs и успешные evidence остаются ignored. Совпадающие Parquet pairs после независимого hash/schema/value сравнения hardlinked, чтобы не хранить несколько физических копий.

[Dockerfile](Dockerfile) использует только новый `track3-output-base:ff2c1d6` и cached builder `track3-output-base-builder:ff2c1d6`. Builder компилирует candidate и запускает строгие synthetic byte checks; runtime сохраняет отдельную baseline extension для binding controls. [recipe.py](recipe.py) сверяет immutable IDs из shared `BASELINE_READY.json` и использует **тот же shared `docker_slot.py`** для каждого целого Docker subprocess, включая inspect/build/run и shared focused runner. В runtime: `colima-agenthon`, linux/amd64, 4 CPUs, memory=16g, memory-swap=16g, network none. Recipe в фазе 1 только подготовлен.

Предопределённые timing units:

| Unit | Что проверяет |
|---|---|
| `t3-gb-mega-throughput` | большие журналы, лимит prefix и несколько canonical groups |
| `t3-gb-horizon-240s` | длинный event loop и устойчивый overlap |
| `t3-mr-deep-book-state-size` | глубокая книга и сохранённое состояние |
| `t3-mp05-cancel-churn-newest` | cancellation churn и late execution labels |

Correctness-only: `t3-s012-partial-fill-cancel-race`, `t3-partialfill-atomicity`, `t3-coarse-tick-ties`, `t3-s001-price-time-priority`, `t3-gbatch-hetero-mix`. Эти unit lists и policy frozen в [policy.json](policy.json). Никакие all-public/regression65 runs не запланированы.

Фаза 2 сначала проверяет обе схемы с metadata, все ordered decoded values, точные file bytes обоих журналов, собственные file hashes, неизменённые shared developer gates и actual native provenance каждого market. Затем source/image identities frozen; одна исключённая warmup на сторону и ровно пять paired runs AB, BA, AB, BA, AB на timing unit. Все samples/outliers остаются, retries/tuning после performance inspection запрещены. Primary clock — полный Docker `FinishedAt − StartedAt`; improvement = `100*(1−median(candidate)/median(baseline))`, плюс означает быстрее, минус медленнее. Диагностика ранних rows и adapter phases отделяется от этого полного clock. Ниже приведена завершённая серия по этой политике.

Pinned preflight завершён для implementation commit `3cb8784279483ce8ba7206d937ee2fddd109f786`, candidate `sha256:ff2a2f6032dd5650508b6847843b93380ed9e12776d5f4bba127f5e24847329a` (`track3-output-h04:3cb878427948`). [Полный preflight summary](evidence/preflight-summary.json) содержит IDs, hashes и ссылки на evidence. Pinned Python 3.11.17 / Arrow 15.0.2 synthetic checks прошли: все 12 пар byte/schema/metadata/value-exact без test-only page-cap override. Linux/amd64 ASan+UBSan queue и trace tests прошли. Пакеты NumPy 1.26.4, pandas 1.5.3, Arrow 15.0.2, SciPy 1.17.1, Python, numeric dispatch, Python adapter hashes и сохранённая baseline extension совпали с новым audited baseline; установленная candidate extension совпала с own build manifest. Native source hashes совпали с READY.

[Pinned binding checks](evidence/phase2-controls-attempt01/bindings/summary.json) подтвердили buffers/counts, оба журнала exact bytes, empty handling и exceptions. До завершения kernel event loop на s012 закодированы 131 072 immutable lifecycle rows; всего 202 291 четырьмя блоками. На s001 ранних rows 0. В C++ пути максимум пять application threads: Sim, два dispatcher и два shared encoders; resource CPU quota остаётся четыре. Dispatcher callbacks не запускаются внутри encoder pool.

[Shared selected controls](evidence/phase2-controls-attempt01/focused/summary.json) принял все девять объявленных units: 18 контейнеров, 26 actual native market executions, 26 byte/schema/metadata/ordered-value-exact пар journals; unchanged shared developer gates и own file digests прошли. [Storage/native integrity check](evidence/phase2-preflight-integrity/summary.json) подтвердил single-link plain files для всех 130 Parquet files внутри controls evidence, после восстановления shared public corpus и accepted fresh corpus-preflight. Shared runner использовал APFS clones; scored input и retained outputs не hardlinked. Host-only synthetic supporting pairs, описанные выше, не подаются в scorer. Failed phase-2 builds/controls отсутствуют. Build, inspect, binding run, sanitizer run, runtime audit и controls держали общий exclusive Docker slot. На момент завершения preflight timing ещё не запускался: readiness записана в shared `PREFLIGHT-h04-lifecycle-pipeline.json`; После этого координатор отдельно разрешил единственную timing series, приведённую ниже.

Timing завершён: одна серия, без retry, tuning, удаления outliers или дополнительных profile-only launches. 8 исключённых warmups + 40 timed samples = 48 принятых контейнеров; все 48 market executions actual native. 64 stability/cross-side comparisons охватывают 128 пар journals; в каждой byte/schema/metadata/ordered-values равенство, unchanged shared developer gates и собственные digests прошли. Source/test hashes не менялись, runner frozen SHA256 `5e04867e8d11a6d4983648d1647d028623b2a2307c1c22e589991d575341ea70`.

Primary результат — полный Docker `FinishedAt − StartedAt`, включая startup, Sim/finalization, оба writers/drain/footers и hashes. `100*(1−median(candidate)/median(baseline))`: плюс быстрее, минус медленнее.

| Unit | Baseline median, s | Candidate median, s | Time reduction | Faster pairs |
|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | 1.728614650 | 1.708198889 | +1.18% | 2/5 |
| t3-gb-horizon-240s | 0.998866013 | 0.943128445 | +5.58% | 2/5 |
| t3-mr-deep-book-state-size | 1.184253422 | 0.753805739 | +36.35% | 4/5 |
| t3-mp05-cancel-churn-newest | 0.712181137 | 0.625825197 | +12.13% | 2/5 |

Все full-container samples ниже сохранены. Warmup исключён из median; P1/P3/P5 — AB, P2/P4 — BA. Никакие samples не отброшены.

| Unit | Side | Excluded warmup | P1 AB | P2 BA | P3 AB | P4 BA | P5 AB |
|---|---|---:|---:|---:|---:|---:|---:|
| t3-gb-mega-throughput | baseline | 1.550229967 | 1.573427750 | 1.728614650 | 2.097822834 | 1.784411759 | 1.454817175 |
| t3-gb-mega-throughput | candidate | 1.831321156 | 1.654038033 | 2.377365372 | 1.816891513 | 1.641975103 | 1.708198889 |
| t3-gb-horizon-240s | baseline | 1.166378217 | 0.805133864 | 0.998866013 | 0.758491237 | 1.147994783 | 1.059115913 |
| t3-gb-horizon-240s | candidate | 0.854044854 | 0.840706789 | 1.347214324 | 1.203095027 | 0.731066452 | 0.943128445 |
| t3-mr-deep-book-state-size | baseline | 0.931664269 | 0.682220335 | 1.184253422 | 1.374057981 | 1.488975007 | 0.766410231 |
| t3-mr-deep-book-state-size | candidate | 0.733082994 | 0.753805739 | 0.726170929 | 1.169638097 | 1.053829947 | 0.633608548 |
| t3-mp05-cancel-churn-newest | baseline | 1.252648204 | 0.712181137 | 0.536225392 | 0.817606007 | 0.669936276 | 0.728514297 |
| t3-mp05-cancel-churn-newest | candidate | 0.835881345 | 1.116910277 | 0.625825197 | 1.030548277 | 0.574198040 | 0.589856750 |

Component diagnostics ниже — median adapter phases, секунды. Core включает lifecycle finalization и producer backpressure; `parquet_write` — остаточная writer/drain/footer работа после Sim. Независимые phase medians не складываются в median полного контейнера. Они не измеряют отдельно worker CPU, blocking или contention и не заменяют primary clock.

| Unit | Side | Configuration | Sim + trace finalize | Parquet tail | Hashing |
|---|---|---:|---:|---:|---:|
| t3-gb-mega-throughput | baseline | 0.003129196 | 0.741179490 | 0.376923230 | 0.176130149 |
| t3-gb-mega-throughput | candidate | 0.005012878 | 0.767509778 | 0.338923638 | 0.173537824 |
| t3-gb-horizon-240s | baseline | 0.002716982 | 0.253201680 | 0.259168496 | 0.085541011 |
| t3-gb-horizon-240s | candidate | 0.003893010 | 0.240741420 | 0.239504152 | 0.080270395 |
| t3-mr-deep-book-state-size | baseline | 0.003832785 | 0.265294562 | 0.245129992 | 0.049215850 |
| t3-mr-deep-book-state-size | candidate | 0.004297111 | 0.258966541 | 0.149963036 | 0.039535523 |
| t3-mp05-cancel-churn-newest | baseline | 0.002919186 | 0.123802588 | 0.224566768 | 0.034509241 |
| t3-mp05-cancel-churn-newest | candidate | 0.003301606 | 0.131470383 | 0.167018626 | 0.037608015 |

Scope ограничен immutable-колонками первого canonical row group на 1 Mi rows; `msg_type` остаётся deferred и следующие row groups пишутся после Sim. Это не полный streaming writer lifecycle и не изолированный benchmark matcher. Before-Sim-finished encoding отдельно подтверждено preflight-диагностикой на s012. Эффект полного запуска зависит также от setup, bounded-buffer copies/backpressure, конкуренции с существующим ledger writer и общего encoder pool; пять локальных пар не обосновывают результаты на official hardware или непроверенных scenarios. Host — macOS ARM, containers — emulated Linux amd64, четыре CPU / 16g RAM / swap cap16g / network none; `rankable:false`, `adopted:false`.

[result.json](result.json) — точная копия standard shared runner result; [measurement-summary.json](measurement-summary.json) фиксирует проверенные counts, medians и hashes. Raw summary/result, все журналы, Docker state, profiles, comparisons, command и launcher log остаются в ignored [timing evidence](evidence/phase2-timing/). Reports-only postprocessing также держал общий `docker_slot.py` lock. Никакие production sources, tests, cards, gates или tolerance не менялись после начала серии. Merge/push/integration не выполнялись.
