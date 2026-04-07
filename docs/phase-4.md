# Фаза 4 — Доступ сервера к GitHub (deploy key)

## Статус
- Статус: ✅
- Дата/время: 2026-04-07 07:46:58 +05:00

## Цель фазы
- Дать серверу чтение приватного репозитория `vapecoding/voice-inbox` через отдельный deploy key.

## Что сделано
- На сервере сгенерирован ключ `/root/.ssh/github_deploy`.
- В `/root/.ssh/config` добавлен блок для `github.com` с `IdentityFile ~/.ssh/github_deploy`.
- Проверено содержимое серверного `~/.ssh/known_hosts`.
- Публичный ключ сервера забран на локальную машину.
- Deploy key зарегистрирован в GitHub-репозитории как `server`.
- Выполнена проверка доступа с сервера к репозиторию.

## Проблемы и отклонения
- `github.com` уже присутствовал в серверном `known_hosts`.
- Для `gh repo deploy-key add` на Windows удобнее и надёжнее использовать путь к временному `.pub`-файлу, а не stdin/heredoc.

## Как решено
- Уже существующие записи `github.com` в `known_hosts` были переиспользованы без дублирования.
- Публичный ключ сервера был временно сохранён локально и передан в `gh repo deploy-key add` как файл.

## Проверки
- `gh repo deploy-key list --repo vapecoding/voice-inbox` показал deploy key `server` со статусом `read-only`.
- `ssh voice-inbox-server "git ls-remote git@github.com:vapecoding/voice-inbox.git HEAD"` вернул хеш `HEAD`.

## Артефакты и изменения
- Созданы/обновлены серверные файлы:
  - `/root/.ssh/github_deploy`
  - `/root/.ssh/github_deploy.pub`
  - `/root/.ssh/config`
- В GitHub-репозитории `vapecoding/voice-inbox` создан deploy key `server`.

## Следующий шаг
- Перейти к Фазе 5: клонировать проект на сервер, создать `.venv`, подготовить серверный `.env`, systemd unit и запустить сервис.
