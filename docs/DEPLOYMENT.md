# Voice Inbox — Деплой

## Что деплоится

Серверный инстанс `Voice Inbox` состоит из:
- git-клона проекта в `/root/voice-inbox`
- Python venv в `/root/voice-inbox/.venv`
- серверного `.env`
- systemd unit `voice-inbox.service`

Приложение слушает HTTP-порт `8080`.

## Требования

Нужно иметь:
- Ubuntu-сервер с root-доступом
- локальный `.env` с:
  - `TELEGRAM_BOT_TOKEN`
  - `DEEPGRAM_API_KEY`
  - `GROQ_API_KEY`
  - `SERVER_HOST`
  - `SERVER_PASSWORD`
- `gh`, авторизованный в GitHub
- SSH-доступ по alias `voice-inbox-server`
- deploy key сервера для чтения `vapecoding/voice-inbox`

## Текущая схема деплоя

### 1. Код на сервере

Если каталога нет:

```bash
ssh voice-inbox-server "git clone git@github.com:vapecoding/voice-inbox.git /root/voice-inbox"
```

Если каталог уже есть:

```bash
ssh voice-inbox-server "cd /root/voice-inbox && git fetch origin && git pull --ff-only"
```

### 2. Виртуальное окружение

Первичная установка:

```bash
ssh voice-inbox-server "cd /root/voice-inbox && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
```

При обновлениях:

```bash
ssh voice-inbox-server "cd /root/voice-inbox && .venv/bin/pip install -r requirements.txt"
```

### 3. Серверный `.env`

Файл: `/root/voice-inbox/.env`

Минимальный состав:

```env
TELEGRAM_BOT_TOKEN=
DEEPGRAM_API_KEY=
GROQ_API_KEY=
WEB_PASSWORD=
WEB_PORT=8080
PUBLIC_BASE_URL=http://<SERVER_HOST>:8080
```

Практика:
- создавать файл в UTF-8 без BOM
- использовать LF, если файл готовится локально на Windows и потом копируется на Linux

### 4. Systemd

Файл: `/etc/systemd/system/voice-inbox.service`

```ini
[Unit]
Description=Voice Inbox Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/voice-inbox
ExecStart=/root/voice-inbox/.venv/bin/python main.py
Restart=always
RestartSec=5
EnvironmentFile=/root/voice-inbox/.env

[Install]
WantedBy=multi-user.target
```

После изменения unit:

```bash
ssh voice-inbox-server "systemctl daemon-reload"
```

### 5. Запуск

```bash
ssh voice-inbox-server "systemctl enable --now voice-inbox"
```

Проверка:

```bash
ssh voice-inbox-server "systemctl is-active voice-inbox"
ssh voice-inbox-server "journalctl -u voice-inbox --no-pager -n 40"
```

### 6. Порт

Если `ufw` активен:

```bash
ssh voice-inbox-server "ufw allow 8080/tcp"
```

Если `ufw` не активен, отдельного действия не требуется.

## Проверки после деплоя

Минимум стоит проверить:

```bash
ssh voice-inbox-server "systemctl is-active voice-inbox"
ssh voice-inbox-server "journalctl -u voice-inbox --no-pager -n 40"
```

Снаружи:
- `GET /login` должен отвечать
- `GET /` без cookie должен редиректить на `/login`
- логин с `WEB_PASSWORD` должен открывать ленту

Полный чеклист — в [PLAN_V3.md](D:\vapecoding\intFinDop\PLAN_V3.md).

## Обновление проекта

Типовой сценарий обновления:

```bash
git add .
git commit -m "..."
git push
ssh voice-inbox-server "cd /root/voice-inbox && git pull --ff-only && .venv/bin/pip install -r requirements.txt && systemctl restart voice-inbox"
```

После этого:

```bash
ssh voice-inbox-server "systemctl is-active voice-inbox"
ssh voice-inbox-server "journalctl -u voice-inbox --no-pager -n 30"
```

## Частые проблемы

### Root-пароль истёк

Симптом:
- `paramiko` подключается, но команды не идут
- сервер требует немедленную смену пароля

Что делать:
- пройти forced password change через интерактивный shell
- обновить локальный `.env`
- после этого перейти на SSH-ключ и больше не зависеть от пароля

### OpenSSH на Windows ругается на `~/.ssh/config`

Симптом:
- `Bad owner or permissions on ...\\.ssh\\config`

Что делать:

```powershell
icacls "$HOME\.ssh\config" /inheritance:r /grant:r "$env:USERNAME:F" "SYSTEM:F" "Administrators:F"
```

### Ключ сгенерировался с не тем passphrase

Симптом:
- сервер принимает public key, но логин по ключу не проходит

Что делать:
- перегенерировать ключ с действительно пустым `-N ""`
- заново положить новый `.pub` в `authorized_keys`

## Связанная документация

- [PROJECT_OVERVIEW.md](D:\vapecoding\intFinDop\docs\PROJECT_OVERVIEW.md)
- [PLAN_V3.md](D:\vapecoding\intFinDop\PLAN_V3.md)
- [REPORT_TEMPLATE.md](D:\vapecoding\intFinDop\docs\REPORT_TEMPLATE.md)
