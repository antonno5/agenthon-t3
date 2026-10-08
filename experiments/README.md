# Track 3 experiments

## Executive summary

Each experiment records what changed, how it was measured and whether to keep it.
Source snapshots, logs, trace checks and component timings are saved in a separate
history directory. Kernel ledger iterations apply patches and run locally without Docker. Correctness checks use the requested small public unit; the full
public suite is not run automatically. These are local results, not official scores.

## Эксперименты

| Каталог | Что сравнивает | Одна команда |
|---|---|---|
| [native-io-batch-comparison](native-io-batch-comparison/README.md) | Сводное сравнение потокового SHA256 и параллельных batch-рынков; только отчёты и данные, код не принят. | `comparison.json` и `orchestration-audit.json` |
| [stream-hash](stream-hash/README.md) | Потоковый SHA256 при записи Parquet и общий batch-пул; архив замеров. | Исходная ветка и исторические команды в отчёте |
| [native-batch](native-batch/README.md) | Независимые native batch-рынки: база, один и два worker; архив замеров. | Исходная ветка и исторические команды в отчёте |
| [hotpaths-20261006](hotpaths-20261006/ARCHIVE.md) | Пять гипотез: все отчёты, доказательства и независимое сравнение. | См. `comparison.json` и `archive-index.json` |
| [startup-integration](startup-integration/README.md) | Отложенный импорт SciPy вместе с уже принятыми DEBUG-guards. | Стандартная сборка `baselines/Dockerfile` |
| [components](components/README.md) | Общие логи и типизированный сборщик событий; время компонентов. | `make experiment` |
| [kernel_message_ledger](kernel_message_ledger/README.md) | Применение патчей, целевые тесты, сборка таблицы и память без Docker; контейнерный режим отдельный. | `make experiment-ledger` |
| [heap-queue](heap-queue/README.md) | Однопоточная очередь: исторический отчёт, код остался в экспериментальной ветке. | См. исходную ветку в `result.json` |
| [book-index](book-index/README.md) | Индексы цены и order ID: исторический отчёт, код остался в экспериментальной ветке. | См. исходную ветку в `result.json` |
| [process-batch](process-batch/README.md) | Пул процессов: исторический отчёт, код остался в экспериментальной ветке. | См. исходную ветку в `result.json` |
| [market-context](market-context/README.md) | Изоляция состояния рынков: исторический отчёт, код остался в экспериментальной ветке. | См. исходную ветку в `result.json` |
| [native-hotspot](native-hotspot/README.md) | Нативный reducer и Python control: исторический отчёт. | См. исходную ветку в `result.json` |
| [differential-gates](differential-gates/README.md) | Обе точные трассы и полные developer gates: включено в `codex/develop`. | `make differential-check` |
| [management-20261006](management-20261006/README.md) | Сравнение всех шести гипотез и решение об интеграции. | Отчёт и `comparison.json` |
| [python-control-integration](python-control-integration/README.md) | Прямой Python-проход по истории для метрик ликвидности, включённый в develop. | Команды и итог проверки в отчёте |
| [differential-gates](differential-gates/README.md) | Раздельные baseline/candidate images, обе точные трассы, полный developer gate и batch isolation. | `make differential-check` с явными images/commit/units/output |

## Порядок работы

1. В каталоге эксперимента записываем краткое описание изменения и команду повторения.
2. Фиксируем исходники, diff, параметры, зависимости и окружение; image ID — в контейнерном режиме.
3. Скорость измеряем с разогревом и тремя повторами; подробный профиль запускаем отдельно.
4. После замены компонента собираем candidate image с теми же закреплёнными зависимостями и запускаем `make differential-check`: обязательные точные event/message traces, все developer gates и batch isolation на явно выбранных релевантных units, включая `t3-s001-price-time-priority`. Затем сохраняем report и коммитим изменение. Неуспешное или незавершённое сравнение не принимаем; параметры Make и полный цикл описаны в [differential-gates](differential-gates/README.md#development-cycle).
5. Сохраняем отчёт, машинные результаты, логи и вердикт **«делаем / не делаем»** с причиной.
6. Следующие запуски создают новый каталог, не перезаписывая предыдущие результаты.

История компонентов и контейнерных прогонов: `out/experiments/<UTC>-<название>-<id>/`.
Локальные итерации журнала: `kernel_message_ledger/runs/<UTC>-<id>/`. В каждом завершённом эксперименте
есть `CHANGE.ru.md`, `decision.json`, `REPORT.ru.md`, `summary.csv`, `summary.json`,
`metadata.json`, снимок кода и журнал запусков. Вердикт является рекомендацией;
скрипт не откатывает код автоматически. Незавершённый эксперимент не принимается.

Критерий зависит от цели эксперимента: компоненты/контейнер — точные трассы и
снижение времени контейнера не менее 5%; локальный kernel_message_ledger — целевые
тесты, точный Parquet и снижение времени сборки таблицы и пика Python heap не менее 10%
каждого. Порог журнала записан в его `experiment.json`. Это локальные практические
правила, без оценки статистической значимости. Улучшение компонента и ускорение всего
контейнера описываются отдельно.

## Единственная проверка публичного задания

```sh
DOCKER_CONTEXT=colima-agenthon make unit \
  UNIT=t3-s001-price-time-priority \
  IMAGE=my-simulator:local \
  RESULTS=out/quick-check
```

Команды выполняются из корня репозитория. Нужны готовая `.venv` и работающий контекст
Docker. Глобальный контекст не меняется, VM автоматически не запускается. Число
сценариев ограничиваем выбором этого unit, без искусственного лимита 30 секунд или
3 минуты. Более широкие проверки требуют отдельного выбора заданий.
