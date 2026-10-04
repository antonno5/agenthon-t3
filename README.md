# Agenthon T3

Репозиторий iMak AI Lab для решения Track 3 и публикации Docker-образа в `ghcr.io/antonno5/agenthon-t3`.

Добавьте код решения и `Dockerfile` в корень репозитория. Для публикации откройте **Actions → Publish Docker image → Run workflow**, выберите ветку и запустите сборку. Workflow использует автоматический `GITHUB_TOKEN`; отдельный PAT не нужен. В результате появится образ для `linux/amd64` с тегом `sha-<commit>` и точной ссылкой с digest в отчёте запуска.

После первой публикации владелец должен открыть **Package settings → Change visibility → Public** и проверить анонимное скачивание. Публичность GitHub-репозитория не делает GHCR package публичным автоматически. [Документация GitHub](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility#configuring-visibility-of-packages-for-your-personal-account).

Секреты команды и заполненная памятка с доступами хранятся отдельно от этого публичного репозитория.

[Официальный starter kit T3](https://github.com/Agenthon-2026/track3-simulation-public)
