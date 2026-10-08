Ledger streaming and the arena order book are integrated in develop. This report compares fresh paired runs with the previous develop revision; all selected scenarios preserve both journals exactly. Measurements are local and non-rankable.

Предыдущий develop: `18af3d5b56c017bc7297a5f0aa38a449043c97a6`. Реализация: `286ae974641e4ad23e81288b5beee2d7d9da20c5`.

Положительный процент — сокращение полного времени контейнера; отрицательный — замедление. Формула: `100 × (1 − median(candidate) / median(baseline))`. Для каждого сценария выполнены один прогрев каждой стороны и пять AB/BA-пар. Прогревы исключены, все samples и выбросы сохранены.

| Сценарий | До, мс | После, мс | Ускорение / замедление | Быстрее в парах |
|---|---:|---:|---:|---:|
| `t3-gb-mega-throughput` | 1659.020 | 1603.083 | **+3.37%** | 4/5 |
| `t3-gb-pop-horizon-scale` | 1457.657 | 1265.511 | **+13.18%** | 2/5 |
| `t3-gb-horizon-240s` | 1255.192 | 1125.493 | **+10.33%** | 3/5 |
| `t3-mr-deep-book-state-size` | 908.222 | 746.585 | **+17.80%** | 4/5 |
| `t3-mp05-cancel-churn-newest` | 877.845 | 581.050 | **+33.81%** | 4/5 |
| `t3-multilevel-crossing` | 427.608 | 440.249 | **-2.96%** | 2/5 |
| `t3-s001-price-time-priority` | 403.478 | 422.853 | **-4.80%** | 4/5 |

Геометрическое среднее отношений медиан на этих семи сценариях: **+11.02%**, коэффициент ускорения **1.124×**. Это сводка выбранного набора, без переноса на остальные testcase.

Проверки: 22 correctness-запуска на 11 units, 70 timing-запусков и 14 прогревов; оба журнала совпали побайтно, по схеме и порядку значений. Shared developer gates прошли, native подтверждён в каждом рынке. ASan/UBSan прошли 80 000 мутаций стакана и проверки pipeline; pinned Arrow 15 прошёл синтетические границы блоков/row groups и binding-проверки пустого результата и ошибок.

Независимо перепроверено 228 journal digests. Host monotonic timestamps подтверждают последовательность всех 106 запусков. Аномалии Docker wall-clock timestamps: 0; детали сохранены в validation.json.

Среда: Mac ARM64, Colima linux/amd64 с эмуляцией, 4 CPU, 16 GiB memory, 16 GiB memory+swap, network none; `rankable:false`. RNG, float flags, mapping и зависимости сохранены. Baseline image ранее построен из a7fb6c3: исходники baselines у предыдущего develop 18af3d5 идентичны, разница только в отчётах.

Pipeline переносит запись ledger внутрь симуляции: core phase включает backpressure, Parquet phase отражает оставшуюся запись после simulation. Поэтому основные выводы сделаны по полному Docker времени.

Все samples, попарные результаты, фазы и пути evidence сохранены в [result.json](result.json). Проверки: [validation.json](validation.json), [build-record.json](build-record.json), [source-audit.json](source-audit.json). Raw outputs, журналы и логи остаются под evidence/ и исключены из Git.

Измеряемые сценарии и дополнительные correctness-only units зафиксированы до timing в [plan.json](plan.json). Полный public corpus в этом прогоне не запускался.

| Сценарий | Host Docker CLI clock, вторичная метрика |
|---|---:|
| `t3-gb-mega-throughput` | +2.52% |
| `t3-gb-pop-horizon-scale` | +15.31% |
| `t3-gb-horizon-240s` | +5.63% |
| `t3-mr-deep-book-state-size` | +13.36% |
| `t3-mp05-cancel-churn-newest` | +30.27% |
| `t3-multilevel-crossing` | -9.46% |
| `t3-s001-price-time-priority` | +1.59% |
