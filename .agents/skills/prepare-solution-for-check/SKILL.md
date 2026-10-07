---
name: prepare-solution-for-check
description: Подготовить решение Track 3 Agenthon к проверке — переиспользовать подходящие результаты, опубликовать образ через командный GitHub Actions и собрать новый ZIP для CodaBench. Использовать по запросам «подготовить решение к проверке» или «подготовить посылку на скор».
---

# Подготовить решение к проверке

Prepare the chosen Track 3 simulator for evaluation: reuse matching validation,
publish through the team's GitHub Actions workflow, and create a new ZIP with the
published image digest and team proof. Organizers verify the team and dispatch
uploads before automated evaluation starts. Preparation ends with a validated ZIP;
upload it only when the user has asked you to submit it.

## Контекст и входные данные

- Определи `SOLUTION_REPO` (исходники, toolkit и результаты проверок) и
  `PUBLISH_REPO` (командный репозиторий публикации). Прочитай применимые
  `AGENTS.md`, контракт отправки и README/workflow обеих репозиториев.
  В текущем проекте это соседние `track3-simulation-public` и `agenthon-t3`:
  первый собирает из `baselines/`, второй — из корня с `Dockerfile`.
- Зафиксируй выбранную версию, ветку, HEAD, изменения и build context.
  Если пользователь дал готовый ZIP, прочитай его `submission.json` и связанные
  readiness/build-отчёты: именно этот образ и его исходники являются выбранным
  решением. Не заменяй их более свежим checkout без указания пользователя.
- Нужны: выбранный registry/repository, номер команды, фаза соревнования, лицензия
  решения; для отправки также страница Track 3 и назначенный аккаунт CodaBench.
  Возьми известные значения из контекста; запроси отсутствующие вместе и продолжай
  независимые локальные шаги. Текущие согласованные значения: команда `523`,
  GitHub `antonno5/agenthon-t3`, образ `ghcr.io/antonno5/agenthon-t3`.
  Новые указания пользователя имеют приоритет; не выбирай другой namespace
  или лицензию самостоятельно.
- Team Key вводится локально скрытым вводом упаковщика либо читается из указанного
  пользователем файла вне репозитория с правами `0600`. Не запрашивай ключ в чате,
  не ищи его по файловой системе и не сохраняй его в отчётах, образе или архиве.
- Используй явно указанный Docker context; текущий глобальный context не переключай.
  Для существующей локальной среды проекта используй `--context colima-agenthon`;
  VM/context `avito` исключён существующими инструкциями. Проверь доступность
  среды и чужие активные нагрузки до тяжёлых запусков; не останавливай их.

## Проверка и сборка

1. Используй checker Python 3.13 и toolkit из публичного тега `v2.4.4`
   в `SOLUTION_REPO` (либо актуальный pin применимого контракта):

   ```sh
   .venv/bin/python -m pip install 'qfbench2-common[data] @ git+https://github.com/Agenthon-2026/Agenthon2026-public.git@v2.4.4#subdirectory=common'
   ```

   Если это окружение уже соответствует требованиям, переиспользуй его.
   Команды toolkit и Makefile ниже выполняются из `SOLUTION_REPO`; в
   репозитории публикации отдельная `.venv` и публичные задания не обязательны.
   Runtime ABIDES в Docker остаётся Python 3.11 с зависимостями Dockerfile.

2. Сначала сверь существующий проверенный образ с текущим кодом: image ID,
   версии зависимостей, upstream-патчи, adapter, вспомогательные модули,
   конфигурации заданий и параметры запуска. Переиспользуй достоверные отчёты
   для совпадающих исходников, inputs и условий запуска, сохраняя их исходный scope.
   Условия включают Docker config (`WorkingDir`, `Entrypoint`, `Cmd`, `Env`, `User`)
   и ограничения платформы. Совпадение Python-файлов и пакетов само по себе
   не подтверждает runtime-совместимость. Новый registry, repository, тег, digest
   сборки или упаковка без иных изменений не требуют повторного прогона.
   При переносе через Actions переходи
   к шагу 4: отдельная локальная пересборка такого же кода не обязательна.
   Для локальной проверки изменённого решения собери новый кандидат и сохрани лог:

   ```sh
   docker --context colima-agenthon build --platform=linux/amd64 \
     -t "$CANDIDATE_IMAGE" baselines/
   ```

   При недоступном registry можно собрать overlay на уже сохранённом образе
   с подтверждённым набором зависимостей и upstream-патчей. Зафиксируй его image ID,
   сверь установленный код с нужными патчами, скопируй актуальный adapter и модули
   из checkout, сохрани отдельный Dockerfile и происхождение. Не называй такой
   overlay чистой сборкой из исходного Dockerfile.

   Проверь `linux/amd64`, label `qfbench2.interface_version=2.0`, обе команды
   `simulate` / `simulate-batch`, локальный image ID и происхождение исходников.
   Все runtime-зависимости должны быть внутри образа: проверка работает без сети.

3. До объявления готовности проверь реальный запуск обоих verbs с ограничениями
   из актуального Development runtime guide. Переиспользуй доказательства такого
   запуска только при совпадении кода, inputs и Docker config. `--help`, обычный
   `docker run`, проверки на root-пользователе и сверка установленного кода
   этого не заменяют. Для изменения только среды запуска достаточно одного
   single-задания и одного batch-задания с проверкой результатов; это не 71/71.

   В текущем Development T3 применяются `--read-only --user 65534:65534`,
   `--cap-drop=ALL --security-opt no-new-privileges`,
   `--tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m`, `--network=none`,
   `--pids-limit 256 --ulimit nofile=1024:1024 --ulimit nproc=256:256`,
   4 CPUs, 16 GiB без swap и 64 MiB per-file/output-tree limits.
   Монтируй только scenario inputs в `/input:ro`, без reference traces;
   `/output` должен быть доступен uid 65534. Не подменяй рабочую директорию
   аргументом `--workdir` при проверке готового образа: проверяется его Docker config.
   Сохраняй команду, image ID, exit code, stdout/stderr, output и проверки
   allowlist, схем, digest и семантики. Ожидаются exit 0 и корректные результаты.
   ABIDES всегда пишет summary log относительно рабочей директории: `/work/log`
   падает на read-only root; в текущем образе `WORKDIR /tmp` оставляет временные
   журналы в tmpfs, вне deliverables. Ошибка требует исправления образа, затем
   нового registry digest и перепаковки ZIP. При явном запрете пользователя
   запускать сценарии соблюдай запрет и явно обозначь непроверенную runtime-совместимость.

   Проверь только непокрытые существенные изменения. Например, если изменился
   только вывод `simulate-batch`, сохрани доказательства прежних single-run проверок
   и запусти шесть batch-заданий:

   ```sh
   DOCKER_CONTEXT=colima-agenthon make batch-check \
     IMAGE="$CANDIDATE_IMAGE" RESULTS="$RESULTS"
   ```

   Полный прогон нужен при изменении движка, случайных потоков, схемы или отсутствии
   пригодных результатов, либо по явному запросу пользователя. Явное указание
   пользователя не запускать сценарии сохраняй; укажи фактическое покрытие и
   непроверенные изменения. Если полный прогон входит в согласованный объём,
   запусти developer gates последовательно на всех 71 публичном задании:

   ```sh
   DOCKER_CONTEXT=colima-agenthon make all-unit-gates \
     IMAGE="$CANDIDATE_IMAGE" RESULTS="$RESULTS"
   ```

   Makefile запускает Docker CLI из Python-процессов; экспортированный
   `DOCKER_CONTEXT` выбирает context и для них. Не полагайся лишь на одноимённую
   Make-переменную; проверь выбор через `DOCKER_CONTEXT=colima-agenthon docker context show`.
   Не выдавай `make check` или regression65 за полные runtime gates: они не покрывают
   все message ledgers и batch isolation. Прежние частичные результаты остаются частичными;
   повторно подтверждать тот же scope без изменений не нужно.
   При сбое сохрани отчёт, установи причину и исправь дефект решения в рамках задачи;
   после изменения пересобери образ и обнови только затронутые доказательства. Не ослабляй scorer,
   эталоны, карточки, допуски или sanitizer. В batch-корне допускается только
   `batch_events.json`; диагностический `profile.json` разрешён в подкаталогах.
   Проверка одного задания не подтверждает прохождение всего набора.
   Локальные результаты имеют `rankable=false` и не являются официальным скором.

## Публикация через командный GitHub Actions

4. Подготовь публикацию выбранного решения в `PUBLISH_REPO`.

   - Если подходящий образ уже опубликован в выбранном repository и связан
     с нужными исходниками, переиспользуй его после проверки доступа по digest.
   - Перенеси нужные build ingredients из выбранной версии: adapter, matching,
     upstream-патчи, control-модуль, CLI и лицензии. Сверь хеши с исходным
     отчётом; не копируй весь рабочий каталог, ZIP, claim, ключи, `.venv` и логи
     в публичный репозиторий. Проверь `.gitignore` и `.dockerignore`.
   - Сборка из корня должна работать на GitHub runner без локальных Docker-образов.
     При сохранении того же решения закрепи базовый образ по измеренному digest
     и версии зависимостей. Зафиксируй происхождение в `provenance/`.
   - Используй существующий `.github/workflows/publish-image.yml`: `linux/amd64`,
     label `qfbench2.interface_version=2.0`, `packages: write`, вход в GHCR через
     автоматический `GITHUB_TOKEN`, публикация тега `sha-<commit>`.
     Каждый участник пользуется своим GitHub-аккаунтом. Отдельный PAT для
     публикации внутри Actions не нужен; SSH push и авторизация `gh`/браузера
     для запуска workflow — отдельные способы доступа к репозиторию.
   - Для переиспользования измеренных результатов выполни имеющийся
     `scripts/verify-image.py` в Actions: он сверяет установленные Python-исходники,
     CLI/control, версии пакетов и запуск обеих команд без сети, без сценариев.
     Он не запускает сценарии и не заменяет проверку с ограничениями платформы
     из шага 3. Сверь также Docker config опубликованного образа с прошедшим
     эту проверку кандидатом; provenance должен ссылаться на эти runtime-отчёты.
     `provenance/expected-runtime.json` должен происходить из ранее проверенного
     образа. При изменении решения обновляй его вместе с доказательствами;
     не подменяй эталон новым непроверенным образом ради прохождения сверки.
   - При порученной публикации отправь изменения в согласованную ветку (новые
     ветки — `codex/…`) и запусти workflow через существующий push trigger
     либо **Run workflow**, выбрав ветку с Dockerfile. Не добавляй новые триггеры
     только ради обхода отсутствующей авторизации. Зафиксируй commit и run URL.
     Дождись успешной сборки, сверки и push; при неизвестном исходе сначала
     проверь существующий run, а не запускай дубликат. Исправляй подтверждённую
     причину сбоя в рамках задачи; при блокировке правами сохрани готовые файлы
     и сообщи требуемое действие владельца.

   Прямой локальный push/overlay используй, если пользователь выбрал такой
   маршрут или он нужен как согласованный fallback. При public route проверь
   manifest по immutable digest, `linux/amd64`, config и доступность всех слоёв
   без локальных registry credentials. После первой публикации пакет может быть
   private: сначала проверь доступ; при блокировке владелец делает **Package
   settings → Change visibility → Public**. Публичный GitHub-репозиторий не
   гарантирует публичность GHCR. Сохрани registry manifest digest из Actions
   и/или независимой проверки registry; локальный image ID его не заменяет.
   Private route допустим только с подтверждённой организаторами ссылкой зеркала.

## Новый ZIP и CodaBench

5. При смене registry, repository или digest создай **новую посылку**.
   Исходный ZIP сохрани: он продолжает ссылаться на прежний образ. Для того же
   решения возьми дескриптор из него, обнови `image` и заново reseal/pack через
   toolkit; команду, фазу, category и лицензию сохраняй, если они актуальны.
   Для первой посылки скопируй fixture установленного toolkit
   `qfbench2_common/contracts/fixtures/c5/simulation_<phase>.json`.
   Измени image, подтверждённую лицензию и image_access; убери fixture team_id,
   чтобы `pack` вычислил настоящий. Для Development:
   `competition_id=agenthon2026-simulation-dev`, `track=simulation`, `phase=dev`,
   `category=simulator`, `models=[]`. Фазу и актуальные сроки сверь с объявлениями;
   не переноси Development identifier в Final. `image` — объект registry/repository/digest.
   Если уже известен производный team_id, пересчитай `descriptor_digest` через toolkit
   и проверь `SubmissionDescriptor.from_mapping`. Иначе оставь team_id отсутствующим
   для `pack`: упаковщик сам выводит ID, reseal и проверяет полный дескриптор.
   При отсутствующем registry digest сохраняй явно обозначенный черновик, а не готовую посылку.

6. Упакуй без передачи Team Key аргументом:

   ```sh
   .venv/bin/qfbench2 submission pack --descriptor "$DESCRIPTOR" \
     --team-number "$TEAM_NUMBER" --out "$SUBMISSION_ZIP"
   ```

   `pack` вычисляет team_id, reseal и proof. Старый `team-claim.json` не переносится:
   HMAC proof привязан к точным байтам нового descriptor. Без Team Key можно
   сохранить validated descriptor и команду упаковки, но не объявлять ZIP готовым.
   В архиве должны быть ровно два файла
   в корне: `submission.json` и `team-claim.json`. Проверь дескриптор из самого ZIP;
   сверяй image repository/digest, team number в claim, привязку claim к байтам
   дескриптора и целостность ZIP. Не редактируй его после упаковки.
   При известном внешнем файле ключа добавь `--team-key-file "$TEAM_KEY_FILE"`;
   сам ключ аргументом не передавай. Копию на рабочем столе назови однозначно,
   например `agenthon-t3-team<номер>-<digest-prefix>.zip`, и сообщи, что это
   новый архив для нового образа. Не перезаписывай исходную посылку.

7. Для всей команды используется **один назначенный аккаунт CodaBench**.
   На странице Track 3 с него нажимают **Request to participate** и ждут
   одобрения; первый ZIP с claim связывает аккаунт с зарегистрированной командой.
   Это отдельная регистрация от личных аккаунтов GitHub.
   Если пользователь поручил загрузку, загрузи новый ZIP с этого аккаунта,
   зафиксируй submission ID и статус. Организаторы сначала проверяют команду
   и вручную отправляют посылку на выполнение; оценка после запуска автоматическая.
   **Submitted** во время ожидания этой проверки нормален. Проверяй актуальные
   инструкции соревнования; не обещай мгновенный запуск и не дублируй upload
   при неизвестном исходе. Held/cancelled uploads расходуют попытки.
   При запросе только подготовки или при «я сам загружу» закончи готовым
   архивом и ссылкой на соревнование.

## Результат

Сохрани артефакты в новом каталоге `out/submissions/`: логи, отчёты по заданиям,
происхождение исходников и image ID, commit/run Actions, registry digest, descriptor
и ZIP при наличии входных данных. В репозитории публикации `out/` должен быть
ignored. Кратко сообщи, что выполнено, сколько заданий прошло, **какой новый ZIP
загружать**, какой образ он описывает, где сохранён исходный архив
и что конкретно блокирует оставшиеся шаги. Укажи точное локальное покрытие и
ссылки на переиспользованные результаты; не утверждай «71/71», если этого
доказательства нет. Готовность архива требует подтверждённых проверок затронутого
кода, анонимного доступа к образу и успешной упаковки.

## Авторитетные инструкции

- Локальный контракт: `SOLUTION_REPO/SUBMISSION_CLI.md`.
- [Контракт трека](https://github.com/Agenthon-2026/track3-simulation-public/blob/main/SUBMISSION_CLI.md).
- [Командный workflow](https://github.com/antonno5/agenthon-t3/actions/workflows/publish-image.yml) — выбирай ветку с решением.
- [CodaBench Track 3: Overview → Registering / After you upload](https://www.codabench.org/competitions/17767/#/pages-tab).
- [Образы и доступ](https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/IMAGE-SUBMISSIONS.md).
- [Дескриптор и упаковка](https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/starter-packs/track3/SUBMISSION-DESCRIPTOR.md).
- [Фаза, runtime и лимиты](https://github.com/Agenthon-2026/Agenthon2026-public/blob/main/docs/DEVELOPMENT-RUNTIME.md).
