The latest develop simulator combines streaming ledger output with a shared arena order book. All 71 public units pass local developer gates; both verbs also pass the current Development runtime restrictions. GitHub Actions publishes the selected sources after verifying the measured runtime.

# Agenthon T3 — team 523

Исходная версия: Track3 codex/develop 57b1a40. Образ публикуется в ghcr.io/antonno5/agenthon-t3, linux/amd64, с тегом sha-<commit>. Происхождение, hashes исходников, полного прогона и отдельных runtime-проверок сохранены в provenance/. Эти результаты локальные, rankable:false.

Полное покрытие developer gates — 71/71. Отдельное покрытие ограничений Development — single t3-s001-price-time-priority и batch t3-gbatch-homog-4: read-only root, uid 65534, tmpfs 64 MiB, без сети, 4 CPU, 16 GiB без swap, ограничения процессов/файлов и 256 MiB output.

Workflow Publish Docker image запускается push в codex/publish-* либо вручную. Он собирает из корня, проверяет Python/upstream/CLI, все package versions, native sources/API и Docker config по измеренным данным, затем публикует immutable digest. Проверка Actions не запускает сценарии. Бинарный hash расширения не сравнивается между сборками: компилятор может изменить binary bytes; проверяются исходники, build flags, API и runtime.

Для CodaBench нужен новый ZIP с опубликованным digest и новым team proof. Team Key используется только локальным упаковщиком. Исходные посылки сохраняются. Ключи, ZIP, claim, .venv и логи исключены из репозитория и Docker context.
