# Python control integration

## Executive summary

This change computes liquidity-gap metrics by scanning the original book-history
rows directly, instead of allocating a pandas Series for every row. It uses
Python only and keeps the original trailing-gap accounting and integer timestamps.
The user selected it for `codex/develop` on 6 October 2026. Previous local results
were promising on cancellation churn, but do not establish a full-suite speedup.

## Что включено

- `baselines/_abides_python_control.py`: исходная проверенная реализация
  `dropout_totals` из эксперимента №5, без C-модуля или компилятора.
- `baselines/patches/dropout_python_control.patch`: заменяет только проход
  `ExchangeAgent.get_time_dropout` через `DataFrame.iterrows()`.
- Стандартный Dockerfile применяет этот пятый патч и включает Python helper.
  Четыре предыдущих патча, очередь, стакан, RNG и порядок сообщений сохранены.
- Непрерывный незакрытый провал ликвидности в конце истории по-прежнему не
  прибавляется к метрике. Отрицательные/одинаковые timestamps и Python integers
  не округляются. Входная история не изменяется.

## Измеренные ранее результаты

Медианы трёх пар на Mac ARM64 / linux/amd64 Rosetta, относительно исходного
baseline; отрицательная величина означает сокращение времени:

| Сценарий | Изменение полного времени Python control |
|---|---:|
| s001 price/time priority | +2,74% |
| oracle variant | −2,43% |
| cancellation / replacement churn | −16,48% |

Источник: [исходный отчёт №5](../native-hotspot/README.md), commit
`42f3b42f03a5996dec327078c330f4849f3c242b`. На churn Python control был быстрее
C в двух из трёх пар. Решение включить этот Python-вариант не означает приёмку
нативного модуля. Новый интеграционный прогон проверяет корректность; нового
утверждения о скорости всего pytest/regression набора не делаем.

## Проверка интеграции

По уточнению пользователя новые Docker-запуски для этой интеграции не выполнялись.
Итог в `result.json` включает:

- 373 passed, 1 existing APFS skip, 38 integration deselected, 2 subtests passed.
  Новые проверки сравнивают прямой проход с прежним pandas-расчётом на восьми
  граничных и 100 случайных историях; проверяют точность и сохранность RNG/данных.
- 71 public manifest/firewall проверки и Ruff прошли.
- Helper и патч побайтно совпадают с измеренным Python control из отчёта №5.
- Обе трассы и full developer gates на s001/oracle/churn повторно проверяются
  по сохранённым результатам прежних Linux/Python3.11 запусков. Это проверка
  артефактов; симулятор не запускался и нового времени прогона не измерено.

Сборку нового development image и новую public regression65 для него не
выполняли. Историческая regression65 нативного C-модуля не приписывается Python
control. Все проверки `rankable=false`; допуска всех 71 units по runtime не заявляем.

Локальные тесты из корня:

```sh
PYTHONPATH="$PWD" .venv/bin/python -m pytest tests/ -q -m 'not integration'
.venv/bin/ruff check baselines/_abides_python_control.py tests/test_dropout_python_control.py
```
