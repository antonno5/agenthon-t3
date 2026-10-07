# Experiment 4: independent SimulationContext

## Executive summary

Each market now owns its random numbers, identifiers, agents, event queue and log directory. In the pinned Docker runtime, 42 isolation cases and two mixed-market cases preserved both traces and the caller's state. All four selected units passed the full developer gates, and all 65 public single scenarios passed the standard regression. Local timing results were mixed; the experiment establishes isolation and compatibility, without a general speedup or third-party thread-safety claim. All results are non-rankable developer evidence.

База эксперимента — `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`, а не чистый upstream. Ветка — `codex/exp-20261005-04-market-context`; worktree — `/Users/iopogiba/.codex/worktrees/617b/Агентон`. Начальные HEAD и merge-base совпали с базой. Родительский `../../AGENTS.md` отсутствует; применён доступный локальный AGENTS.md. Другие экспериментальные ветки не использовались.

Новый `abides_fork.simulation_context.SimulationContext` владеет `SimulationState`, конфигурацией, агентами, Kernel, очередью, collector и end state. Жизненный цикл: `created → running → done → terminated`; callback exception переводит контекст в `failed`. `step(max_events)` считает queue pops, включая requeue, и отдаёт управление между полными событиями. `run()` продолжает paused context без вызова `step(1)` для каждого события. Исходное поведение Kernel на границе stop-time сохранено: проверяется предыдущее время, поэтому первый pop за stop-time всё ещё возможен.

`baselines/patches/simulation_context.patch` применяется ПОСЛЕ четырёх существующих upstream patches. В `abides_core.simulation_state` добавлен ContextVar, который выбирает владельца RNG/ID во время конструктора, initialize, runner и terminate. Это не save/restore глобального `np.random` или class counters. Сам master RNG — `RandomState(seed)`; тип `uint64`, порядок seed draws и дополнительные oracle draws сохранены. Upstream constructors без активного контекста сохраняют старое поведение. Новый `simulate` больше не сбрасывает глобальные counters.

Обнаружена особенность общего baseline: `abides.run(config)` игнорирует `config['random_state_kernel']` и создаёт Kernel с default `kernel_seed=0`. Кандидат сохраняет Kernel `RandomState(0)` И неиспользуемый draw конфигурации. Передача этого draw в Kernel изменила бы baseline. Также `SparseMeanRevertingOracle.__init__` потребляет master exponential draw между oracle seed и exchange seed; тесты с настоящим oracle проверяют полный порядок, включая fallback latency.

Collector перехватывает `logEvent` конкретных агентов, а не `Agent.logEvent` для всех рынков. Восстанавливаются и inherited method, и локальный third-party override при исключении. `simulate` поддерживает `buffered`, `legacy` и `verify`; `verify` сравнивает typed order trace с legacy extractor. Message ledger не заменён и не упрощён.

### Аудит глобального состояния

| Источник в pinned upstream | Реализация в контексте |
|---|---|
| `Message.__message_id_counter` | `SimulationState.message_id`, старт 1; поддержаны dataclass subclasses и MessageBatch |
| `Order._order_id_counter` | `SimulationState.order_id`, старт 0; explicit IDs и deepcopy не расходуют новые IDs |
| `Agent` и `Kernel` implicit RNG constructors | seed draw из context master stream |
| `abides_core.utils.get_wake_time` | context master `rand()` |
| `abides_markets.utils.generate_latency_model` | context master seed draw, прежний dtype и алгоритм latency |
| Sparse oracle initial/subsequent megashock times | context master `exponential()` |
| Dense mean-reverting oracle shocks | context master `normal()` |
| Agent, symbol/oracle, latency and Kernel explicit RandomStates | отдельные per-instance streams с прежними seeds |
| Event queue, ledger, seq, causal metadata, book and agent state | принадлежат отдельному Kernel/agent graph |

Незакрытые состояния конкретны: upstream `configs/rmsc03.py` и `configs/rmsc04.py` всё ещё вызывают `np.random.seed`/global draws; новый путь их не использует. Старый standalone `build_config` также сохраняет global режим. `abides_core.abides.run` конфигурирует global coloredlogs; новый Context API обходится прямым Kernel. Logger registry/handlers остаются общими. Diagnostic `ComponentProfiler.instrument()` и legacy `TraceCollector.capture()` всё ещё временно меняют class methods; interleaved Context API их не использует, а threaded profiling не поддерживается. Third-party код с прямыми `np.random.*`, собственными class counters, module caches или внешними thread/task callbacks должен получить явно свой RNG/owner. Вызов конструктора Order/Message вне `state.activate()` принадлежит legacy global режиму. Gym environment/config drivers не включены в scope. Один контекст нельзя одновременно исполнять несколькими потоками. Дополнительный аудит выявил, что upstream `Kernel.write_summary_log()` игнорирует `skip_log` и ВСЕГДА пишет summary в общий `./log/<unix-second>`. Прежнее утверждение об отсутствии этих файлов при `skip_log=True` было неверным. Теперь каждый Context получает уникальный абсолютный instance-owned log directory, даже в non-retained режиме. Non-retained scratch очищается после terminate или lifecycle exception; `retain_logs=True` сохраняет summary и agent logs под уникальным каталогом в caller-provided `log_root`. CWD не меняется. Third-party код, который пишет собственные абсолютные/общие пути в обход Kernel, требует отдельной интеграции и не покрывается этой гарантией.

### Что проверено локально

- 34 CPU integration tests выполняют patched pinned исходники с synthetic agents/configuration: IDs и копии, caller RNG, A-B-A, одинаковые/разные seeds, порядок создания/исполнения, два одновременно живых initialized contexts с чередованием queue pops, все три trace modes, обе parquet byte streams, exceptions, stop boundary, requeue и paused resume, unique retained summary/agent files для двух live contexts во всех trace modes, неизменный CWD/global log tree и cleanup при успехе/ошибке. Это checker Python 3.13, не замена runtime Docker Python 3.11 и не real-scenario admissibility.
- Hermetic suite до follow-up с parallel correctness wrapper: 347 passed, 1 existing skipped, 2 subtests passed. Для нового wrapper выполнен отдельный smoke ниже.
- 71 manifests verified и 71 public firewall checks passed (142/142).
- Ruff по изменённому Python-коду, compile/import-help smoke и `git diff --check` прошли.
- Raw logs и upstream scratch сохранены только в игнорируемом `out/`. `upstream_sources.json` фиксирует SHA исходников; тесты не скачивают их и не обращаются к Docker.

Все заданные units существуют: `t3-s001-price-time-priority`, `t3-as05-oracle-variant`, `t3-momentum-mix-priority`, `t3-gbatch-homog-4`; замен нет. `stage_inputs.py` подготовил три single configs и четыре batch sub-configs без references. Units/cards/scorer/tolerances/reference files не менялись.

### Воспроизведение CPU tests

Из корня этого worktree:

```bash
CHECKER='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
QFB2_ABIDES_SOURCE="$PWD/out/upstream/abides-jpmc-public-f9cbe51342b7dedd9587e4e069040d68a5c6477f" \
  PYTHONPATH="$PWD" "$CHECKER" -m pytest tests/integration/test_market_context.py \
  -m integration -q --tb=short --disable-warnings
PYTHONPATH="$PWD" "$CHECKER" -m pytest tests/ --ignore=tests/integration -q --tb=short
```

Для другой машины `QFB2_ABIDES_SOURCE` указывает на checkout неподправленного upstream `f9cbe51342b7dedd9587e4e069040d68a5c6477f`. Тесты проверяют SHA и сами применяют четыре control patches, затем context patch. Raw source не включён в Git.

### Воспроизведение Docker validation в эксклюзивном слоте

Overlay использует неизменный образ, сохраняет версии зависимостей и применяет patch к временной копии installed sources и переносит изменения обратно (GNU patch 2.8 отказывается проходить через symlink directories). Build-time `patch` устанавливается и удаляется внутри одного слоя. Полный fallback build — существующий `baselines/Dockerfile` с теми же pinned версиями.

```bash
docker --context colima-agenthon tag \
  sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2 market-context-base:0bd010981f4f
docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE=market-context-base:0bd010981f4f \
  -f experiments/market-context/Dockerfile.overlay \
  -t market-context:20261005 .

# При необходимости повторно stage в новый каталог; existing path намеренно отвергается.
PYTHONPATH="$PWD" "$CHECKER" experiments/market-context/stage_inputs.py \
  --out out/context-isolation-input-new
mkdir -p out/context-runtime
docker --context colima-agenthon run --rm --platform linux/amd64 \
  --network none --cpus 4 --memory 16g --memory-swap 16g \
  -v "$PWD/out/context-isolation-input-new:/input:ro" \
  -v "$PWD/out/context-runtime:/diagnostic" market-context:20261005 \
  python /opt/market_context_isolation.py --scenarios-dir /input \
  --trace-mode verify --out /diagnostic/isolation-verify.json
```

Retained-logs diagnostic (в эксклюзивном Docker-слоте):

```bash
docker --context colima-agenthon run --rm --platform linux/amd64 \
  --network none --cpus 4 --memory 16g --memory-swap 16g \
  -v "$PWD/out/context-isolation-input-new:/input:ro" \
  -v "$PWD/out/context-runtime:/diagnostic" market-context:20261005 \
  python /opt/market_context_isolation.py --scenarios-dir /input --trace-mode verify \
  --retain-logs --log-root /diagnostic/context-logs --out /diagnostic/isolation-retained-verify.json
```

Runtime diagnostic проверяет, что все contexts имеют разные абсолютные log directories, `cwd` и дерево `cwd/log` не меняются, retained summary присутствует и читается, а non-retained scratch удалён. Runtime retained/non-retained проверки повторяются во всех трёх trace modes. Логи хранятся в diagnostic mount, а не в solver output.

`isolation.py` сравнивает обе bytes трасс с isolated candidate для A-B-A и interleaved same/different seeds в обоих порядках. Он отдельно сохраняет время configuration, simulation и trace finalize для первого и последующих запусков в одном процессе. Повторить с `--trace-mode legacy` и `buffered` и разными JSON output paths. Скорость в этом диагностическом тесте не используется как benchmark.

Полные developer gates + точные обе трассы + sanitizer + paired benchmark выполняет `paired.py`:

```bash
PYTHONPATH="$PWD" "$CHECKER" experiments/market-context/paired.py \
  --baseline-image orchestration-baseline:20261005-a5dbe46 \
  --candidate-image market-context:20261005 \
  --batch-control-image orchestration-control:20261005-a5dbe46 \
  --repeats 3 --out out/context-paired
```

Для только gates использовать тот же вызов с `--gates-only --out out/context-gates`. Каждая команда Docker содержит `--context colima-agenthon`. Runner последовательно делает один warmup pair, три unprofiled AB/BA pairs и отдельный profile pair; при обнаружении других контейнеров отказывается начинать измерение. Логи лежат рядом с solver-output, не внутри него. Каждый output проходит неизменный C3 sanitizer и все developer gates, затем bytes order/message traces сравниваются с baseline. Сохраняются image IDs, full-run container/host clocks, adapter clock и component phases. `container_sec - adapter_sec` — оценка startup/exit, не точный JIT timer; новый JIT не вводится. Fresh-container repeats не называются warmed in-process execution. Это локальный `rankable=false` опыт на Mac ARM64 с linux/amd64 emulation; переносить его скорость на official Linux CPU нельзя.

Важное отдельное изменение кандидата: batch больше не пишет root `profile.json`; диагностика остаётся в разрешённых `<sub>/profile.json`. Allowlist/sanitizer не менялись. Исходный baseline всё ещё должен получить честный `path_not_allowed`; runner сохраняет этот failure и не объявляет batch gates завершёнными без отдельного explicit contract-only control с exact original trace bytes. Control image проверен здесь отдельно во всех gates/timing/profile stages, его обе trace bytes совпали с original baseline. Для batch показаны и raw-baseline ratio, и отдельно control/candidate ratio, чтобы эффект sidecar repair не скрывался.

Исходная команда public regression по всем 65 singles (references остаются снаружи worktree). Для запланированного запуска использовать checkpoint wrapper ниже:

```bash
DOCKER_CONTEXT=colima-agenthon PYTHONPATH="$PWD" "$CHECKER" regression_suite/run_regression.py \
  --candidate-image market-context:20261005 \
  --scenarios-dir regression_suite/scenarios/ \
  --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' \
  --output-dir "$PWD/out/context-public-regression" --workers 1
```

Public regression не заменяет message-ledger gates и exact comparison обеих трасс. Оба вида validation завершены здесь. Итог: `validated_isolation_and_public_compatibility`, developer admissible; official Final timing не заявляется. Критерий эксперимента — доказанная изоляция и совместимость, ускорение не обязательно.

### Checkpoint/recovery wrapper, follow-up 2026-10-06

Для длительного regression65 добавлен отдельный host tool `regression_checkpoint.py`; standard regression/scorer/refs не менялись. По последнему указанию менеджера correctness допускает до трёх независимых контейнеров по 3 GB, после завершения строго последовательных timing/profile runs. Команда regression после завершения этих измерений:

```bash
DOCKER_CONTEXT=colima-agenthon PYTHONPATH="$PWD" "$CHECKER" experiments/market-context/regression_checkpoint.py \
  --candidate-image market-context:20261005 --scenarios-dir regression_suite/scenarios/ \
  --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map' \
  --output-dir "$PWD/out/context-public-regression-checkpoint" --workers 3
```

Повтор той же команды возобновляет работу. `binding.json` фиксирует immutable image ID, hashes 65 configs/reference traces, card hashes и identity checker/исходных функций. Checkpoints/progress пишутся атомарно после flush/fsync; запись `running` создаётся перед запуском, `completed` — сразу после returned result. Final `report.json` не нужен для восстановления. Каждый attempt имеет отдельный output path; повреждённый/недоступный output не перезаписывает прежний attempt.

Saved outputs обязательно заново проходят неизменный `run_regression.run_scenario`: временный scoped local launcher передаёт сохранённые trace/events в temp output вместо Docker. Все исходные parsing, regular-file copy guards, Tier-A/B, stylized-fact и events checks выполняются снова. Не копируются и не переопределяются scoring функции. Валидные failing gates остаются FAIL и не запускаются повторно; missing/corrupt/modified outputs получают новый attempt. Outputs, сохранённые до interruption, но до completed checkpoint, также могут быть восстановлены после полной перепроверки. Binding change требует нового output directory.

Все cached outputs перепроверяются последовательно в parent до первого нового запуска. Затем `ProcessPoolExecutor` со spawn держит не более `--workers` активных задач (допустимы 1, 2 или 3; default 1). Только parent пишет checkpoints/progress, сохраняет каждый returned result перед заполнением свободного slot и собирает final report в порядке исходного плана. Worker вызывает неизменный `run_scenario` и возвращает result; scoring и reference файлы не изменяются.

Actual launches используют pinned image ID и explicit `docker --context colima-agenthon`, `--cpus 4 --memory 3g --memory-swap 3g --network none`. Эти caps относятся только к correctness regression; это не изменение resource cards и не performance benchmark. Timing/profile runner остаётся строго последовательным с прежними 4 CPU/16 GB. Timeout cleanup стандартного helper получает тот же `DOCKER_CONTEXT`. Parent записывает CID path до submit; при interruption запрещает новые запуски, а cleanup/resume могут удалить только container из собственного unfinished checkpoint: CID и labels binding/scenario проверяются перед `rm -f`. Параллельный запуск нескольких wrapper в одном output directory не поддерживается.

Подготовка без Docker уже выполнена: `--dry-run --workers 3` проверил все 65 configs и public refs (plan-only, container/image inspection отсутствуют). Десять существующих hermetic recovery tests повторно прошли на текущем wrapper: interruption на следующем scenario и после output retention, recheck/remaining-only, изменение saved bytes/image binding, сохранение FAIL, настоящий replay исходных gates/regular-file guards, явный Docker context/pinned ID, отказ удалять чужой container и retry неполного output. Evidence: `out/checkpoint-parallel-recovery-tests.log`.

Новый `checkpoint_parallel_smoke.py` проверил пять synthetic scenarios через настоящие standard gates без Docker: один cached output перепроверен в parent до запусков, четыре оставшихся выполнены тремя spawned processes, все пять PASS. Все 21 checkpoint/progress writes сделаны parent; попытка worker записать checkpoint вызывает failure. Smoke проверяет explicit context, caps 3g/3g/4 CPU и completed checkpoints. Evidence: `out/checkpoint-parallel-smoke/smoke.json` и `out/checkpoint-parallel-smoke.log`. Воспроизведение (новый output directory):

```bash
PYTHONPATH="$PWD" "$CHECKER" experiments/market-context/checkpoint_parallel_smoke.py \
  --out out/checkpoint-parallel-smoke-new
```

Regression65 завершён: 65 PASS. Recovery regression сохраняет standard trace/events; полные developer gates и message ledger/exact обеих трасс по selected units выполнены отдельно. Docker-слот освобождён, active containers: 0.


### Actual runtime validation, 2026-10-06

Immutable baseline: `sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2`. Candidate: `sha256:89451763457dd7a58d53972bf4c9bf94ccb88f6eeb2f9131b65cb90eec9b48fb`. Explicit serial contract control: `sha256:66674764c6906050f57b83cd34b32b0942afd4900af44dd5c3ac7adae0c2f98e`. Runtime: Python 3.11.17, NumPy 1.26.4, pandas 1.5.3, pyarrow 15.0.2; packages inherited from pinned baseline. Colima runs ARM64 Linux with linux/amd64 emulation. Это локальные `rankable=false` результаты.

- Isolation campaign: 7 public configs × 3 modes × 2 log policies = 42 PASS, 504 context runs. Каждый case проверил isolated/A-B-A, same/different seeds, оба порядка создания/чередования, byte hashes обеих traces, caller NumPy/class counters/Agent method/cwd/shared log tree, unique absolute logs и cleanup/retention. Evidence: `out/context-isolation-campaign/summary.json`; каждый input/mode/policy сохранён отдельно, повтор команды восстанавливает только незавершённые cases.
- Heterogeneous pair: oracle-variant + momentum-mix, `buffered/default` и `verify/retained`, 8 context runs. Обе traces каждого рынка совпали с isolated candidate; host сравнил все 8 файлов с published public references, hashes exact. Caller/filesystem checks PASS. Evidence: `out/context-heterogeneous/host-reference-comparison.json`.
- Четыре selected units: полные developer gates и неизменный C3 PASS для candidate. Original batch получил `TreeRefused: path_not_allowedx1` из-за root `profile.json`; исходный failure сохранён. Отдельный serial contract control PASS и exact original обе traces. Evidence: `out/context-gates/summary.json`.
- Warmup + 3 unprofiled AB/BA repeats + separate profile, строго последовательно: 20/20 comparisons PASS, 45 container records. Warmup/profile исключены из ratios; batch control показан отдельно. Evidence: `out/context-paired/summary.json` и `out/context-runtime-summary.json`.
- Correctness regression65: 65 PASS, 0 FAIL, 0 ERROR, max 3 independent containers × 3g. После interruption 27 saved outputs перепроверены через original gates в parent, remaining 38 запущены; completed runs не повторены. Evidence: `out/context-public-regression-checkpoint/report.json` и `progress.json`. Regression throughput не является performance evidence.

| Unit | Baseline container median, s | Candidate container median, s | Baseline / candidate | Contract control / candidate |
|---|---:|---:|---:|---:|
| `t3-s001-price-time-priority` | 1.544849 | 1.644003 | 0.940× | — |
| `t3-as05-oracle-variant` | 3.011435 | 3.025484 | 0.995× | — |
| `t3-momentum-mix-priority` | 5.728867 | 5.474669 | 1.046× | — |
| `t3-gbatch-homog-4` | 3.401827 | 3.212310 | 1.059× | 1.053× |

Ratios смешанные: small matching case медленнее, oracle почти без изменения, momentum/batch немного быстрее в этих трёх local repeats. Общий speedup не заявляется. Изоляция/совместимость подтверждены в согласованном scope.

Container/host clocks, adapter time, startup/exit estimate и separate component profiles сохранены в `out/context-runtime-summary.json`. First/subsequent same-process configuration/simulation/trace-finalize times сохранены отдельно для каждого isolation case; filesystem validation вынесена в отдельное поле. Эти diagnostics не сравнивают скорости baseline/candidate. Новый JIT не вводился.

Первый regression attempt не получил inputs: macOS `/var/folders` не был shared в Colima. Это transport environment failure, до semantic gates. Все failed checkpoints/CLI errors сохранены в `out/context-public-regression-unshared-temp-failure/` и соседнем `.log`. Исправление затрагивает только host scratch: scoped `tempfile.tempdir` и `TMPDIR` внутри абсолютного worktree path, явно применены в каждом spawned worker и восстановлены после attempt. Scorer/image/scenarios/refs не менялись. Один actual mount-smoke case PASS был перенесён в final checkpoint после проверки identity hashes и заново прошёл standard gates на resume, без нового Docker launch. Isolation/gates/timing campaigns повторно не запускались.

Небольшие checks после transport/build orchestration fixes: existing 4 runner tests и 10 recovery tests PASS, Ruff PASS. Исходный full hermetic suite 347 PASS и 34 synthetic integration tests — отдельная более ранняя evidence; они не выданы за runtime validation. Build исправлен после двух failed preflights: local verified tag вместо raw ID в `FROM`, copied staging вместо symlink traversal. Successful build log: `out/context-overlay-build-final.log`.

Код не меняет scorer, unit cards, tolerances, references или другую экспериментальную ветку. Произвольные third-party global RNG/counters/caches/background callbacks остаются за пределами гарантии; один Context нельзя одновременно исполнять несколькими потоками. Docker slot явно released, active containers: 0.
