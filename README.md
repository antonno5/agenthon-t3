# Agenthon T3

Репозиторий iMak AI Lab для решения Track 3 и публикации Docker-образа в `ghcr.io/antonno5/agenthon-t3`.

В репозиторий перенесён вариант с bisect-поиском из подготовленной посылки от 7 октября 2026 года. Исходники адаптера, matching engine, upstream-патчи и CLI совпадают с проверенным образом; Python и зависимости закреплены на его версиях. Происхождение и исходное покрытие проверок записаны в `provenance/`.

Для публикации откройте **Actions → Publish Docker image → Run workflow** и выберите ветку. Push в `master` или `codex/publish-*` тоже запускает публикацию. Workflow использует автоматический `GITHUB_TOKEN`; отдельный PAT не нужен. Он собирает `linux/amd64`, сверяет установленный код и версии всех Python-пакетов с измеренным образом и только после успешной сверки публикует тег `sha-<commit>`. Точная ссылка с digest появляется в отчёте запуска. Эта сверка не запускает сценарии и не расширяет покрытие прежних проверок.

Локальная сборка: `docker --context colima-agenthon build --platform linux/amd64 -t agenthon-t3:local .`. Для сверки: `python3 scripts/verify-image.py --context colima-agenthon agenthon-t3:local`. Сохранённое покрытие — 6 из 71 публичного задания; результаты локальные (`rankable=false`). При дальнейших изменениях решения обновляйте доказательства и `provenance/expected-runtime.json` вместе с кодом.

После первой публикации владелец должен открыть **Package settings → Change visibility → Public** и проверить анонимное скачивание. Публичность GitHub-репозитория не делает GHCR package публичным автоматически. [Документация GitHub](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility#configuring-visibility-of-packages-for-your-personal-account).

Секреты команды и заполненная памятка с доступами хранятся отдельно от этого публичного репозитория.

После публикации нужно упаковать новую посылку с адресом `ghcr.io/antonno5/agenthon-t3` и digest из Actions. Архив прежней посылки с другим repository сам по себе не меняется. Team Key нужен только локальному упаковщику; Actions его не использует.

[Официальный starter kit T3](https://github.com/Agenthon-2026/track3-simulation-public)
