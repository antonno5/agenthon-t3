Executive summary: the standalone C++ command reduced the median complete-container
run time on all four selected scenarios. The improvement was about 44–47% on the
three small scenarios and 10.15% on mega-throughput. All canonical journals were
byte-identical to the current native baseline. The engine, random-number generator,
NumPy logarithm dispatch and Parquet writer are unchanged. Batch still uses the
original adapter. This is a local experiment on emulated hardware, not an official
score or an adopted production change.

Гипотеза H02 завершена. Формула: `100 * (1 - median(candidate) / median(baseline))`;
положительное значение означает сокращение полного времени контейнера.
Основной clock — Docker `FinishedAt - StartedAt`, а не внутренний event-rate.

| Сценарий | Baseline median, s | Candidate median, s | Сокращение времени | Candidate быстрее в парах |
|---|---:|---:|---:|---:|
| `t3-s001-price-time-priority` | 0.420834 | 0.233072 | +44.62% | 5/5 |
| `t3-eq-deterministic-baseline` | 0.393512 | 0.219683 | +44.17% | 5/5 |
| `t3-multilevel-crossing` | 0.541636 | 0.287358 | +46.95% | 4/5 |
| `t3-gb-mega-throughput` | 1.682512 | 1.511683 | +10.15% | 3/5 |

Каждый сценарий получил один excluded warmup на сторону и ровно пять пар
`AB / BA / AB / BA / AB`. Все 40 timing samples и восемь warmups сохранены;
повторов серии, исключения outliers и настройки после просмотра времени не было.
Полные samples и пары — `samples.json`, исходный runner result без изменений —
`result.json`, подтверждение пересчёта и protocol audit — `report-audit.json`.

Компонентные median времена из тех же запусков показаны отдельно. Это диагностические
phases полного запуска, не самостоятельные benchmarks; simulation включает trace
finalization, hashing использует тот же ускоренный OpenSSL provider с обеих сторон.

| Сценарий / phase | Baseline median, s | Candidate median, s |
|---|---:|---:|
| `t3-s001-price-time-priority` / `configuration` | 0.003590 | 0.008826 |
| `t3-s001-price-time-priority` / `simulation_and_trace_finalize` | 0.005975 | 0.005141 |
| `t3-s001-price-time-priority` / `parquet_write` | 0.110117 | 0.078548 |
| `t3-s001-price-time-priority` / `hashing` | 0.003532 | 0.016938 |
| `t3-eq-deterministic-baseline` / `configuration` | 0.002899 | 0.008862 |
| `t3-eq-deterministic-baseline` / `simulation_and_trace_finalize` | 0.009528 | 0.009154 |
| `t3-eq-deterministic-baseline` / `parquet_write` | 0.082018 | 0.080489 |
| `t3-eq-deterministic-baseline` / `hashing` | 0.004921 | 0.017781 |
| `t3-multilevel-crossing` / `configuration` | 0.003191 | 0.008643 |
| `t3-multilevel-crossing` / `simulation_and_trace_finalize` | 0.033910 | 0.025123 |
| `t3-multilevel-crossing` / `parquet_write` | 0.159038 | 0.094929 |
| `t3-multilevel-crossing` / `hashing` | 0.013124 | 0.032095 |
| `t3-gb-mega-throughput` / `configuration` | 0.003032 | 0.012840 |
| `t3-gb-mega-throughput` / `simulation_and_trace_finalize` | 0.658379 | 0.791160 |
| `t3-gb-mega-throughput` / `parquet_write` | 0.357291 | 0.357889 |
| `t3-gb-mega-throughput` / `hashing` | 0.178603 | 0.177048 |

Реализация — `baselines/native/cli.cpp`, `scenario.hpp`, `sha256.hpp`; сборка —
`baselines/build_executable.py` и experiment `Dockerfile`. `simulate --config FILE
--out FILE --seed INTEGER --trace-mode buffered` запускает ELF без Python на
поддерживаемом одиночном сценарии. `engine.cpp`, `engine.hpp`, `rng.hpp`,
`message_pipeline.hpp`, `pqwrite.cpp`, `pqwrite.hpp`, `nplog.cpp`, `nplog.hpp` и SVML
assembly сохранены байт-в-байт относительно ff2c1d6. Сохранены IEEE flags, pyarrow
15.0.2 и те же `libarrow.so.1500` / `libparquet.so.1500`; новая схема, encoding или
writer не вводились. Сравнивается полный native front end и его lifecycle;
компонентные числа не доказывают изолированное ускорение самого matcher.

Mapping перенесён из `native.py::_build` и `scenario_params.py` со всеми defaults,
единицами времени, bounds и ties-to-even. Python coercions за пределами native
parser, неизвестный NumPy dispatch, неподдерживаемые агенты, пустая trace и другие
состояния вне envelope возвращаются в неизменённый исходный адаптер. Native-required
mapping/runtime failures завершаются ошибкой. `legacy`, `verify`,
`--profile-components`, `--engine python` сохраняют исходный adapter. Batch verb
и его независимые рынки полностью остаются в исходном `simulate-batch`;
ускорение batch не заявляется. CLI сохраняет поля events/profile, собственные file
SHA256, wall-clock phases и Linux process peak RSS. Дополнительные native diagnostics
сообщают executable, NumPy dispatch и OpenSSL provider.

До timing прошли 70 host mapping checks, 11 runtime configs с exact binary64,
10 CLI boundaries, пять SHA256/error checks, 10,000 NumPy log samples с нулём
расхождений и ASan/UBSan s001. Leak detection выключен для emulated ASan runtime;
проверки утечек не заявляются. Запуск с PATH без Python подтвердил самостоятельное
исполнение; ldd подтвердил отсутствие libpython. Baseline hashlib и CLI используют
OpenSSL 3.5.7 default EVP SHA256 и один pinned `libcrypto.so.3`.

Финальные untimed controls: 14 accepted runs на семи assigned units, 22 journal
comparisons с точным совпадением bytes, полного schema с metadata и ordered values.
Correctness-only units: `t3-s012-partial-fill-cancel-race`,
`t3-eq001-pareto-latency-tail`, `t3-gbatch-hetero-mix`. Все пять batch markets
независимы и native. Timing дал 48 accepted runs и 64 comparison records, включая
cross-side comparisons и repeat stability; оба journals byte-exact во всех случаях.
Shared developer gates, scorer, cards и tolerances не изменялись. Собственные
file digests проверены каждым run; retained Parquet — plain single-link files.
Все Docker builds/checks/timing и существенная постобработка выполнялись под одним
campaign `docker_slot.py` lock. Слепки evidence, gates, raw/retained outputs,
samples и logs находятся в ignored `evidence/`; storage использует APFS clones,
не hardlinks, чтобы сохранять C3 plain-file contract.

До первого timing исправлены: Python truthiness пустой строки, замена portable
PicoSHA2 на тот же OpenSSL provider и ошибочно игнорируемый `--seed ""`.
Сохранены исходный mapping failure, intermediate images, empty-seed failure,
предыдущие controls, corpus-readiness deferral и harness FileExistsError.
Временное заполнение общего диска не требовало удаления чужих файлов.
История — `evidence/failure-history.json`; последняя версия полностью перепроверена
до единственной timing series. Corpus restoration координатора принят общим
manifest/firewall; проверок не обходили.

Runtime: colima-agenthon, linux/amd64 на ARM Mac, network none, 4 CPU, memory 16g,
swap cap 16g. Это emulation и local developer profile с `rankable=false`; результаты
не переносятся на официальное hardware и все public scenarios. Пять пар описывают
этот запуск, не являются confidence interval. Peak RSS — process peak, component
phases зависят от перекрытия работы. Никакой production adoption, merge или push
не выполнялся. Исходники заморожены до конца серии; итоговый commit меняет только
отчёты. Внешний абсолютный evidence путь и immutable identities сохранены в JSON.

Implementation commit: `a91b789ef63f7bb0a70e7a734e5657a999b90c10`.

Baseline image: `sha256:e96d4ea0b819cdf88eb9dde55a6a61d59eefd2247df88139ab0cda03ca0ba1d2`.

Candidate image: `sha256:8957952bff08dbac958064408af26343b925fbf81b1f35d453a8b5b978c47499`.

Builder image: `sha256:c0add3d93b48acb8c7fb429aabf5e751b3c96335e55fb4c57704b021062a616e`.

Runner SHA256: `5e04867e8d11a6d4983648d1647d028623b2a2307c1c22e589991d575341ea70`.
