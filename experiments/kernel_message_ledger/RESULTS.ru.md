# Результаты kernel message ledger

## Executive summary

The patches have been applied to separate copies of pinned ABIDES, and the resulting
code passed 61 targeted tests. Message-table extraction became 2.30 times faster;
measured Python heap fell by 41.7%. Keep the component change.
Whole-simulation speed is not established by this local experiment.

## Статус применения

Прогон выполнен 5 октября 2026 года. Патчи **применены**, а не только сохранены:

- Новый патч ядра: [kernel_message_ledger.patch](kernel_message_ledger.patch).
- Изменение адаптера: [adapter.patch](adapter.patch).
- Применённый Kernel: [runs/20261005T173000Z-e65c52/applied/after/abides-core/abides_core/kernel.py](runs/20261005T173000Z-e65c52/applied/after/abides-core/abides_core/kernel.py).
- Применённый адаптер: [runs/20261005T173000Z-e65c52/applied/after/baselines/abides_fork/trace.py](runs/20261005T173000Z-e65c52/applied/after/baselines/abides_fork/trace.py).
- Подтверждение путей, SHA-256 и совпадения с baseline: [application.json](runs/20261005T173000Z-e65c52/application.json).

В baseline новый патч выбран Dockerfile, а адаптер уже содержит новый путь обработки.
Локальный цикл применяет изменения к отдельным копиям и проверяет получившийся код.
В системную Python-установку ABIDES не устанавливается; пересборка образа не выполнялась.

## Тесты и замеры

**61 целевой тест прошёл**, пропусков и ошибок нет. Тесты используют реальные методы
pinned Kernel с тестовыми агентами и сообщениями. Лог: [tests.log](runs/20261005T173000Z-e65c52/tests.log).

90000 доставок, 900 недоставленных отправлений в before; один разогрев и три
измеряемых повтора каждого варианта, порядок вариантов чередуется.

| Метрика | До | После |
|---|---:|---:|
| Сборка таблицы, с | 0.144235 | 0.062739 |
| Пик Python heap, MiB | 85.34 | 49.72 |

Обе таблицы и Parquet побайтово совпали. Время — только извлечение таблицы; память —
создание входных структур плюс извлечение, отдельным tracemalloc прогоном. Это не RSS
и не время всей симуляции. Окружение: Python 3.13.3, pandas 3.0.6,
NumPy 2.5.3, PyArrow 25.0.1.

## Время полного цикла

| Этап | Секунды |
|---|---:|
| preparation | 0.0066 |
| apply_patches | 0.1021 |
| targeted_tests | 1.0712 |
| microbenchmark | 4.1172 |

Сумма измеренных этапов: **5.30 с**. Docker не использовался.

## Вердикт

**Делаем: принимаем как оптимизацию обработки журнала и памяти.**
Время компонента снизилось на 56.5%, Python heap — на 41.7%.
Критерий в [experiment.json](experiment.json): минимум 10% каждого улучшения при
пройденных тестах и точном Parquet. Это локальное правило без статистической оценки.

Общее ускорение контейнера остаётся отдельным вопросом. В ранее сохранённом
[контейнерном эксперименте](../../out/experiments/20260930T212310Z-kernel_message_ledger-7bede9/REPORT.ru.md)
обе трассы совпали с эталонами, но изменение медианного времени маленького unit было
лишь около 0,5%. Его вердикт по порогу 5% общего времени относился к этому другому критерию.

## Повторение

Из корня репозитория: `make experiment-ledger`.

Все этапы, код, логи, сырые замеры и решение сохраняются внутри `runs/` этого каталога.
[Подробный отчёт](runs/20261005T173000Z-e65c52/REPORT.ru.md) · [Машинный результат](runs/20261005T173000Z-e65c52/summary.json) ·
[Изменения относительно предыдущего локального запуска](runs/20261005T173000Z-e65c52/source_changes.json).
