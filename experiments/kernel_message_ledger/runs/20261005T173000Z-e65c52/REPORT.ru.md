# Применение и проверка kernel message ledger

## Executive summary

The experiment applies the old and new kernel patches to separate copies of pinned
ABIDES, tests the applied code, and measures table extraction and Python heap.
Docker is not used. The decision covers this component, not full simulation speed.

## Изменение и применение

Компактные записи окончательных доставок вместо списка отправлений, таблицы seq и сортировки; фиксированная причинность и отдельные получатели рассылки.

Статус: `complete`. Код применения и SHA-256: [application.json](application.json).
После применения код находится в `applied/before/` и `applied/after/`; именно after-адаптер
и оба применённых Kernel использованы в тестах. Пакет ABIDES в системе не устанавливается.

**Вердикт: делаем.** Сборка таблицы: снижение времени 56.5%; пик Python heap: снижение 41.7%. Порог каждого — 10%; все целевые тесты пройдены, Parquet совпал. Решение относится к компоненту; ускорение всей симуляции не доказано.

## Целевые тесты

Пройдено: **61**, пропущено: 0, failures: 0, errors: 0.
Лог: [tests.log](tests.log); машинный результат: [tests.xml](tests.xml).

## Замеры компонента

90000 доставок; один разогрев и 3 повтора каждого варианта.

| Метрика | Before | After |
|---|---:|---:|
| Сборка таблицы, с | 0.144235 | 0.062739 |
| Пик Python heap, MiB | 85.34 | 49.72 |

Ускорение компонента: 2.30x. Parquet совпал: True.
Время включает только extract_message_trace. Создание входа и Parquet исключены.
Память включает создание входных структур и таблицы; измерена отдельным tracemalloc прогоном, это не RSS.
Окружение: Python 3.13.3, пакеты {'numpy': '2.5.3', 'pandas': '3.0.6', 'pyarrow': '25.0.1'}; локальная .venv, без Docker.

## Время этапов эксперимента

| Этап | Секунды |
|---|---:|
| preparation | 0.0066 |
| apply_patches | 0.1021 |
| targeted_tests | 1.0712 |
| microbenchmark | 4.1172 |

Код, патчи, зависимости и команды сохранены в snapshot/, metadata.json и логах.
Тесты исполняют методы реального pinned Kernel с тестовыми агентами и сообщениями.
Полный запуск ABIDES, CLI контейнера и official Final этим режимом не проверяются.
