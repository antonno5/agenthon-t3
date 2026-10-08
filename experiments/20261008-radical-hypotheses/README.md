Four isolated radical optimization experiments. Positive percentages mean less complete-container time; negative percentages mean longer runs. All timings are local and non-rankable.

Знак: **+ — ускорение, − — замедление**. Формула: `100 × (1 − median(candidate) / median(baseline))`. Каждый сценарий: один прогрев каждой стороны и пять новых AB/BA-пар; прогревы исключены, все выбросы сохранены. Основная метрика — полное время Docker-контейнера.

| Гипотеза | Сценарий | База, мс | Вариант, мс | Ускорение / замедление | Быстрее в парах |
|---|---|---:|---:|---:|---:|
| [Специализированный Parquet writer](h01-parquet-codes/README.md) | `t3-gb-mega-throughput` | 1666.175 | 1577.160 | **+5.34%** | 3/5 |
| [Специализированный Parquet writer](h01-parquet-codes/README.md) | `t3-gb-pop-horizon-scale` | 1195.908 | 1213.226 | **-1.45%** | 2/5 |
| [Специализированный Parquet writer](h01-parquet-codes/README.md) | `t3-mr-deep-book-state-size` | 731.699 | 922.489 | **-26.07%** | 0/5 |
| [Специализированный Parquet writer](h01-parquet-codes/README.md) | `t3-s001-price-time-priority` | 396.766 | 398.717 | **-0.49%** | 4/5 |
| [Потоковая запись message ledger](h02-ledger-pipeline/README.md) | `t3-gb-mega-throughput` | 1829.212 | 1655.959 | **+9.47%** | 3/5 |
| [Потоковая запись message ledger](h02-ledger-pipeline/README.md) | `t3-gb-pop-horizon-scale` | 1021.859 | 987.284 | **+3.38%** | 3/5 |
| [Потоковая запись message ledger](h02-ledger-pipeline/README.md) | `t3-gb-horizon-240s` | 1062.136 | 979.517 | **+7.78%** | 4/5 |
| [Потоковая запись message ledger](h02-ledger-pipeline/README.md) | `t3-s001-price-time-priority` | 307.128 | 297.573 | **+3.11%** | 3/5 |
| [Очереди получателей без повторных requeue](h03-recipient-scheduler/README.md) | `t3-coarse-tick-ties` | 398.980 | 395.569 | **+0.85%** | 3/5 |
| [Очереди получателей без повторных requeue](h03-recipient-scheduler/README.md) | `t3-eq-deterministic-baseline` | 289.331 | 300.787 | **-3.96%** | 2/5 |
| [Очереди получателей без повторных requeue](h03-recipient-scheduler/README.md) | `t3-s012-partial-fill-cancel-race` | 520.624 | 577.441 | **-10.91%** | 1/5 |
| [Очереди получателей без повторных requeue](h03-recipient-scheduler/README.md) | `t3-gb-pop-horizon-scale` | 1096.446 | 1280.710 | **-16.81%** | 1/5 |
| [Очереди получателей без повторных requeue](h03-recipient-scheduler/README.md) | `t3-s001-price-time-priority` | 304.855 | 316.011 | **-3.66%** | 2/5 |
| [Арена заявок и разреженный индекс цен](h04-book-arena/README.md) | `t3-mr-deep-book-state-size` | 683.108 | 709.476 | **-3.86%** | 1/5 |
| [Арена заявок и разреженный индекс цен](h04-book-arena/README.md) | `t3-mp05-cancel-churn-newest` | 655.236 | 530.268 | **+19.07%** | 5/5 |
| [Арена заявок и разреженный индекс цен](h04-book-arena/README.md) | `t3-multilevel-crossing` | 436.244 | 404.774 | **+7.21%** | 4/5 |
| [Арена заявок и разреженный индекс цен](h04-book-arena/README.md) | `t3-s001-price-time-priority` | 295.502 | 322.313 | **-9.07%** | 2/5 |

Ускорения в разы на выбранных сценариях не получено. Максимальный выигрыш полного времени — **19,07% (1,24×)** у H04 cancel churn. H02 дал положительный результат во всех четырёх выбранных сценариях (+3,11…+9,47%); H01, H03 и H04 имеют регрессии. Это основание для проверки H02 и профильного H04 на целевом Linux-хосте, но не подтверждение устойчивого универсального выигрыша.

Аномалия часов: Docker timestamps двух последовательных H04 s001 candidate runs (timing 2/3) формально пересекаются на 18,671528 мс. Запуски выполнялись синхронно под exclusive lock, runner проверял пустой docker ps перед каждым запуском и завершённый state после. Причина несогласованности не установлена; исходные samples сохранены. Результат короткого H04 контроля следует интерпретировать осторожно. Точные timestamps записаны в orchestration-audit.json.

Каждая реализация находится в отдельной ветке и worktree; в этом checkout собраны только отчёты. Автоматической интеграции в production нет. Полный public corpus не запускался: наборы измерений и дополнительные проверки корректности перечислены в `plan.json`.

Среда: Mac ARM64, Colima linux/amd64, четыре CPU, 16 GiB memory+swap, network none; `rankable:false`. Небольшие изменения в пределах нескольких процентов не устанавливают устойчивого эффекта и требуют проверки на целевом Linux-хосте.

Полные samples, фазы и пути сырых доказательств сохранены в индивидуальных `result.json`. `comparison.json` содержит сводку; `orchestration-audit.json` — независимую проверку медиан, журналов, последовательности запусков и аномалий Docker timestamps.

| Гипотеза | Ветка | Чат |
|---|---|---|
| Специализированный Parquet writer | `codex/exp-20261008-radical-h01-parquet-codes` | `01a11aaa-cc14-76a3-9333-fb20d03af66d` |
| Потоковая запись message ledger | `codex/exp-20261008-radical-h02-ledger-pipeline` | `01a11aaa-d11d-78e0-85fb-ba8e001dc771` |
| Очереди получателей без повторных requeue | `codex/exp-20261008-radical-h03-recipient-scheduler` | `01a11aaa-d552-7850-936e-d3371fd36441` |
| Арена заявок и разреженный индекс цен | `codex/exp-20261008-radical-h04-book-arena` | `01a11aaa-d8a6-7313-8a8b-e2af7dc6ec4b` |
