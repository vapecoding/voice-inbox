# Voice Inbox — Обзор проекта

## Что это такое

`Voice Inbox` — это Telegram-бот для голосовых заметок с веб-панелью.

Пользователь отправляет боту голосовое сообщение, бот:
- скачивает аудио из Telegram,
- отправляет его в Deepgram на распознавание речи,
- сохраняет транскрипцию в SQLite,
- по запросу генерирует краткий summary через Groq,
- показывает записи и темы в веб-интерфейсе.

Проект рассчитан на простой самостоятельный деплой на один Linux-сервер без внешней базы данных и без отдельного reverse proxy.

## Основные сценарии

- Обычная голосовая заметка:
  - бот сохраняет запись;
  - возвращает кнопки `Summary`, `Текстом`, `Файлом`.
- Поиск:
  - обычное текстовое сообщение в боте считается поисковым запросом;
  - поиск идёт по полю `transcript`.
- Режим темы:
  - команда `/topic` открывает пакет голосовых;
  - все следующие voice привязываются к одной теме;
  - после закрытия темы можно получить общий summary или весь текст темы.
- Веб-панель:
  - показывает ленту записей и тем;
  - даёт детальные страницы;
  - позволяет удалять записи и темы.

## Архитектура

Проект монолитный. Один Python-процесс запускает:
- Telegram-бот в основном потоке;
- Flask + Waitress в отдельном daemon thread;
- SQLite как локальную файловую БД.

Внешние зависимости:
- Telegram Bot API
- Deepgram API
- Groq API

## Структура кода

- [main.py](D:\vapecoding\intFinDop\main.py)
  - точка входа;
  - загружает конфиг;
  - инициализирует БД;
  - закрывает незавершённые темы после рестарта;
  - запускает веб и бота.
- [config.py](D:\vapecoding\intFinDop\config.py)
  - читает `.env`;
  - валидирует обязательные переменные;
  - формирует `Config`.
- [db.py](D:\vapecoding\intFinDop\db.py)
  - создаёт схему SQLite;
  - хранит записи, темы и summary;
  - даёт CRUD и агрегирующие функции для ленты.
- [bot.py](D:\vapecoding\intFinDop\bot.py)
  - команды `/start`, `/help`, `/topic`;
  - обработка `voice`;
  - поиск по тексту;
  - inline-кнопки для summary/текста/файла;
  - тема как in-memory `active_topics`.
- [web.py](D:\vapecoding\intFinDop\web.py)
  - Flask routes;
  - простая cookie-аутентификация по одному паролю;
  - список записей, темы, удаление;
  - `robots.txt` и `X-Robots-Tag`.
- [templates/login.html](D:\vapecoding\intFinDop\templates\login.html)
  - форма логина.
- [templates/index.html](D:\vapecoding\intFinDop\templates\index.html)
  - лента записей и тем.
- [templates/recording.html](D:\vapecoding\intFinDop\templates\recording.html)
  - детальная страница записи или темы.

## Данные и хранение

SQLite-файл по умолчанию: `voice_inbox.db`.

Таблицы:
- `recordings`
  - одна строка = одна голосовая запись;
  - защита от дублей по `(telegram_chat_id, telegram_message_id)`.
- `topics`
  - объединяют несколько голосовых в одну тему.
- `summaries`
  - summary для одной записи или для темы.

БД работает с:
- `PRAGMA journal_mode=WAL`
- `PRAGMA foreign_keys=ON`

## Переменные окружения

Локальный входной `.env` для агента:
- `TELEGRAM_BOT_TOKEN`
- `DEEPGRAM_API_KEY`
- `GROQ_API_KEY`
- `SERVER_HOST`
- `SERVER_PASSWORD`

Серверный `.env` для приложения:
- `TELEGRAM_BOT_TOKEN`
- `DEEPGRAM_API_KEY`
- `GROQ_API_KEY`
- `WEB_PASSWORD`
- `WEB_PORT`
- `PUBLIC_BASE_URL`
- опционально `DATABASE_PATH`

## Как работает запуск

При старте приложение:
1. Загружает конфиг.
2. Проверяет обязательные env-переменные.
3. Инициализирует SQLite.
4. Закрывает незавершённые темы.
5. Запускает Waitress на `0.0.0.0:WEB_PORT`.
6. Запускает Telegram polling.

## Текущий production-layout

На сервере используются пути:
- код: `/root/voice-inbox`
- venv: `/root/voice-inbox/.venv`
- env: `/root/voice-inbox/.env`
- systemd unit: `/etc/systemd/system/voice-inbox.service`

## Ограничения текущей версии

- Только `voice`, без `video_note`.
- Без HTTPS.
- Без ограничения доступа к боту по user id.
- Без FTS и полнотекстового индекса.
- Сессии веба хранятся в памяти процесса и сбрасываются после рестарта.
- Активные темы между рестартами не продолжаются, а закрываются на старте.

## Связанная документация

- [PLAN_V3.md](D:\vapecoding\intFinDop\PLAN_V3.md)
  - план реализации и практические нюансы.
- [DEPLOYMENT.md](D:\vapecoding\intFinDop\docs\DEPLOYMENT.md)
  - как деплоить и обновлять проект.
- [REPORT_TEMPLATE.md](D:\vapecoding\intFinDop\docs\REPORT_TEMPLATE.md)
  - шаблон отчёта по фазам.
