# Voice Inbox — План v2

**Цель:** Спецификация, достаточная чтобы один AI-агент за один проход создал и задеплоил проект с нуля.

**Идея проекта:** Telegram-бот для голосовых заметок с веб-интерфейсом. Принимает голосовые сообщения, транскрибирует через DeepGram, показывает на веб-панели, генерирует summary через Groq.

**Главное правило для агента:** после каждой фазы — выводи статус пользователю. Не работай молча больше 2-3 минут. Если что-то пошло не так — сразу сообщи, не пытайся починить молча.

---

## 0. Протокол пошагового выполнения

**Агент работает строго пошагово с подтверждением пользователя.**

### После завершения каждой фазы агент ОБЯЗАН:

1. **Сообщить итог** — что было сделано, что получилось, ключевые результаты
2. **Записать итог в отдельный Markdown-файл в папке `docs/`:**
   - Если папки `docs/` ещё нет — создать её в корне проекта
   - Для каждой фазы использовать отдельный файл: `docs/phase-0.md`, `docs/phase-1.md`, `docs/phase-2.md` и т.д.
   - Если файл для текущей фазы уже существует — обновить его, а не создавать дубликат
   - Формат записи: заголовок `# Фаза N — <название>` + дата/время + результат + статус (✅ / ❌)
3. **Объявить следующий шаг** — что будет делать дальше и зачем
4. **Ждать подтверждения** — НЕ переходить к следующей фазе, пока пользователь не даст согласие (любая форма: «да», «ок», «давай», «подтверждаю», «go», «+» и т.д.)

### Шаблон вывода после каждой фазы:

```
✅ Фаза N завершена: <краткое описание>
   Результат: <что конкретно сделано>

📝 Итог записан в `docs/phase-N.md`.

➡️ Следующий шаг — Фаза N+1: <название>
   Буду делать: <краткое описание действий>

⏳ Жду подтверждения для продолжения.
```

### Если фаза завершилась с ошибкой:

```
❌ Фаза N: ошибка
   Проблема: <описание>
   Что нужно: <что требуется от пользователя или что агент предлагает>

📝 Итог записан в `docs/phase-N.md`.

⏳ Жду указаний.
```

**ВАЖНО:** Агент НЕ имеет права самовольно переходить к следующей фазе. Каждый переход — только после явного согласия пользователя.

---

## 1. Входные данные

Агент получает **один локальный файл** `.env` в корне проекта:

```
TELEGRAM_BOT_TOKEN=...
DEEPGRAM_API_KEY=...
GROQ_API_KEY=...
SERVER_HOST=...
SERVER_PASSWORD=...
```

Это именно **локальный входной файл агента**. Его нельзя коммитить. Он **не равен** серверному `.env`, который агент позже создаёт на сервере по пути `/root/voice-inbox/.env`.

Из локального `.env` агент:
- Берёт 3 API-ключа → кладёт в серверный `.env`
- Берёт хост + пароль → подключается к серверу автоматически через paramiko
- Генерирует сам: `WEB_PASSWORD` (случайный, 16 символов), `WEB_PORT=8080`
- Выводит пользователю сгенерированный пароль от веб-интерфейса

Пользователь не выполняет никаких команд вручную. Агент делает всё сам.

---

## 2. Что делает агент (пошагово)

### Фаза 0: Pre-flight проверки

Перед началом работы агент проверяет, что на локальной машине всё готово. Если чего-то не хватает — сообщает пользователю и предлагает установить. **Не начинает работу, пока все проверки не пройдены.**

Проверки:
1. Локальный файл `.env` существует в корне проекта и содержит все 5 строк (непустые значения)
2. `gh` установлен и авторизован (`gh auth status`)
3. `ssh-keygen` доступен
4. Доступен рабочий Python-интерпретатор (`python` или `py`)
5. `paramiko` установлен в этом Python (`python -m pip install paramiko` или `py -m pip install paramiko` — если нет, предложить установить)

Вывод пользователю:
```
🔍 Проверяю готовность...
✅ .env — найден, 5/5 полей заполнены
✅ gh — установлен, авторизован как <username>
✅ ssh-keygen — доступен
✅ python/py — 3.12.x+
✅ paramiko — установлен
Всё готово, начинаю работу.
```

Или, если что-то не так:
```
❌ paramiko — не установлен.
   Выполните: python -m pip install paramiko
   Или на Windows: py -m pip install paramiko
   После этого запустите меня снова.
```

### Фаза 1: Код и GitHub

1. Прочитать локальный `.env`
2. Создать весь код проекта (см. разделы 4–9)
3. Инициализировать git-репозиторий, создать `.gitignore`, сделать первый коммит
4. Узнать GitHub username: `gh api user --jq .login`
5. Создать **приватный** репозиторий: `gh repo create voice-inbox --private`
6. Запушить код

Вывод пользователю:
```
📦 Фаза 1 завершена.
Код создан и запушен: https://github.com/<username>/voice-inbox
```

### Фаза 2: Подключение к серверу

Агент использует `paramiko` — Python-библиотеку для SSH, которая умеет подключаться с паролем программно. Это нужно один раз, чтобы настроить SSH-ключ. После этого paramiko больше не используется.

Шаги:

1. Сгенерировать SSH-ключ локально:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/voice-inbox-server -N ""
   ```

2. Подключиться к серверу через paramiko с паролем из локального `.env`:
   ```python
   import paramiko
   ssh = paramiko.SSHClient()
   ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
   ssh.connect(SERVER_HOST, username="root", password=SERVER_PASSWORD)
   ```

3. Через paramiko: закинуть публичный ключ на сервер в `~/.ssh/authorized_keys`

4. Через paramiko: сохранить host key сервера в локальный `~/.ssh/known_hosts` (чтобы обычный `ssh` потом не спрашивал "доверяете ли этому серверу?")

5. Добавить запись в локальный `~/.ssh/config`, чтобы дальше подключаться коротко:
   ```
   Host voice-inbox-server
       HostName <SERVER_HOST>
       User root
       IdentityFile ~/.ssh/voice-inbox-server
   ```

   После этого все SSH-команды выглядят просто:
   ```bash
   ssh voice-inbox-server "любая команда"
   ```

6. Проверить подключение: `ssh voice-inbox-server "echo ok"`

**⚠️ Примечание:** работаем под root для простоты учебного проекта. В production следует создать отдельного пользователя с sudo.

Вывод пользователю:
```
🔑 Фаза 2 завершена.
SSH-доступ к серверу <SERVER_HOST> настроен.
```

### Фаза 3: Настройка сервера

Все команды агент выполняет через `ssh voice-inbox-server "..."`.

1. Установить пакеты:
   ```bash
   ssh voice-inbox-server "apt update && apt install -y python3 python3-venv python3-pip git"
   ```

Вывод пользователю:
```
🖥️ Фаза 3 завершена.
Сервер готов: python3, git установлены.
```

### Фаза 4: Доступ сервера к GitHub (deploy key)

Серверу нужно склонировать приватный репо. Для этого агент создаёт на сервере SSH-ключ, привязанный к одному конкретному репозиторию (deploy key — доступ только на чтение, только к этому репо).

1. Сгенерировать ключ на сервере:
   ```bash
   ssh voice-inbox-server "ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ''"
   ```

2. Настроить SSH на сервере — при обращении к github.com использовать этот ключ:
   ```bash
   ssh voice-inbox-server "echo -e 'Host github.com\n  IdentityFile ~/.ssh/github_deploy' >> ~/.ssh/config"
   ```

3. Добавить github.com в known_hosts на сервере (чтобы SSH не спрашивал "доверяете ли github.com?" и не зависал):
   ```bash
   ssh voice-inbox-server "ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null"
   ```

4. Забрать публичный ключ с сервера:
   ```bash
   PUBKEY=$(ssh voice-inbox-server "cat ~/.ssh/github_deploy.pub")
   ```

5. Локально зарегистрировать его на GitHub:
   ```bash
   gh repo deploy-key add --repo <username>/voice-inbox --title "server" <<< "$PUBKEY"
   ```

Вывод пользователю:
```
🔗 Фаза 4 завершена.
Сервер получил доступ к репозиторию на GitHub.
```

### Фаза 5: Деплой

Все команды через `ssh voice-inbox-server "..."`.

1. Клонировать код:
   ```bash
   ssh voice-inbox-server "git clone git@github.com:<username>/voice-inbox.git /root/voice-inbox"
   ```

2. Создать venv и установить зависимости:
   ```bash
   ssh voice-inbox-server "cd /root/voice-inbox && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
   ```

3. Создать `.env` на сервере (записать файл через SSH):
   ```bash
   ssh voice-inbox-server "cat > /root/voice-inbox/.env << 'EOF'
   TELEGRAM_BOT_TOKEN=значение_из_secrets
   DEEPGRAM_API_KEY=значение_из_secrets
   GROQ_API_KEY=значение_из_secrets
   WEB_PASSWORD=сгенерированный_пароль
   WEB_PORT=8080
   EOF"
   ```

4. Создать systemd-сервис (см. раздел 10):
   ```bash
   ssh voice-inbox-server "cat > /etc/systemd/system/voice-inbox.service << 'EOF'
   ...содержимое из раздела 10...
   EOF"
   ```

5. Открыть порт (если ufw активен):
   ```bash
   ssh voice-inbox-server "ufw status | grep -q 'active' && ufw allow 8080/tcp || echo 'ufw не активен, пропускаем'"
   ```

6. Запустить:
   ```bash
   ssh voice-inbox-server "systemctl daemon-reload && systemctl enable --now voice-inbox"
   ```

7. Подождать 5 секунд, проверить что сервис работает:
   ```bash
   ssh voice-inbox-server "systemctl is-active voice-inbox"
   ```

8. Если сервис упал — показать логи:
   ```bash
   ssh voice-inbox-server "journalctl -u voice-inbox --no-pager -n 30"
   ```

Вывод пользователю:
```
🚀 Фаза 5 завершена. Всё работает!

Бот запущен — отправьте ему /start в Telegram.
Веб-панель: http://<SERVER_HOST>:8080
Пароль: <сгенерированный_пароль>
```

### Обновление кода в будущем

```
Локально:   git commit → git push
По SSH:     ssh voice-inbox-server "cd /root/voice-inbox && git pull && systemctl restart voice-inbox"
```

---

## 3. Стек технологий

| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| Язык | Python 3.12+ | Основной |
| Telegram Bot | python-telegram-bot 21.x | Async Bot API |
| Web | Flask + Waitress | Лёгкий, production-ready |
| HTTP Client | httpx | Async, для DeepGram/Groq API |
| Env | python-dotenv | Загрузка .env |
| Database | SQLite3 (WAL mode) | Встроен, zero-dependency |
| Speech-to-Text | DeepGram API (nova-2) | Русский язык |
| LLM | Groq API (llama-3.3-70b) | Генерация summary |
| SSH-клиент | paramiko (локально) | Первое подключение к серверу с паролем |

**paramiko** — зависимость только для локальной машины агента. В `requirements.txt` проекта НЕ попадает. Нужна один раз — чтобы подключиться к серверу с паролем и настроить SSH-ключ. После этого агент работает через обычный `ssh`.

### requirements.txt (проект, ставится на сервере)

```
python-telegram-bot==21.7
httpx==0.28.1
flask==3.1.0
python-dotenv==1.1.0
waitress==3.0.2
```

---

## 4. Структура файлов

```
voice-inbox/
├── .env.example              # Шаблон (без секретов)
├── .gitignore
├── requirements.txt
├── main.py                   # Точка входа: бот + веб
├── config.py                 # Загрузка env
├── db.py                     # SQLite: схема + CRUD
├── bot.py                    # Telegram-бот: хэндлеры
├── web.py                    # Flask: роуты + авторизация
└── templates/
    ├── login.html            # Форма ввода пароля
    ├── index.html            # Лента записей
    └── recording.html        # Детальная страница записи/темы
```

---

## 5. Переменные окружения (.env на сервере)

```
TELEGRAM_BOT_TOKEN=           # Обязательный — токен от @BotFather
DEEPGRAM_API_KEY=             # Обязательный — транскрипция голосовых
GROQ_API_KEY=                 # Обязательный — LLM для summary
WEB_PASSWORD=                 # Генерируется агентом — пароль веб-панели
WEB_PORT=8080                 # Порт веб-панели
```

**Безопасность токенов:**
- `.env` в `.gitignore` — **никогда** не попадает в git
- На GitHub лежит только `.env.example` с пустыми значениями
- `.env` создаётся агентом **непосредственно на сервере** через SSH
- `SERVER_HOST` и `SERVER_PASSWORD` остаются только в локальном `.env`

---

## 6. База данных (SQLite)

### Настройки

```python
sqlite3.connect("voice_inbox.db", timeout=10)
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
```

### Таблица `recordings`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| topic_id | INTEGER NULL | FK → topics.id (NULL = одиночная запись) |
| telegram_message_id | INTEGER | Для дедупликации |
| telegram_chat_id | INTEGER | Для дедупликации |
| telegram_file_id | TEXT | Для скачивания аудио |
| duration | INTEGER | Длительность в секундах |
| transcript | TEXT | Расшифровка от DeepGram |
| forward_from | TEXT NULL | Имя отправителя (если переслано) |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**UNIQUE**(telegram_chat_id, telegram_message_id) — защита от дублей.

### Таблица `topics`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| title | TEXT NULL | Название (опционально) |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |
| closed_at | TIMESTAMP NULL | Когда тема закрыта |

### Таблица `summaries`

| Колонка | Тип | Описание |
|---------|-----|----------|
| id | INTEGER PK | Автоинкремент |
| recording_id | INTEGER NULL | FK → recordings.id (ON DELETE CASCADE) |
| topic_id | INTEGER NULL | FK → topics.id (ON DELETE CASCADE) |
| summary | TEXT | Текст summary |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

### Функции CRUD

```python
init_db()                                    # CREATE TABLE IF NOT EXISTS
save_recording(**kwargs) → id                # INSERT OR IGNORE
get_recordings(page, per_page=20) → (rows, total)  # Вся лента, сортировка по дате DESC
get_recording(id) → row
delete_recording(id)                         # CASCADE удаляет summaries
search_recordings(query) → rows              # WHERE transcript LIKE '%query%'

create_topic() → id
close_topic(id)
get_topic_with_recordings(id) → (topic, recordings)
delete_topic(id)                             # CASCADE удаляет recordings и summaries

save_summary(recording_id=None, topic_id=None, text) → id
get_summaries_for_recording(recording_id) → rows
get_summaries_for_topic(topic_id) → rows
```

---

## 7. Telegram-бот (bot.py)

### Команды

| Команда | Действие |
|---------|----------|
| `/start` | Приветствие + краткая инструкция |
| `/help` | Список команд и возможностей |
| `/topic` | Начать тему (пачку голосовых) |

### Обработка голосовых

**Хэндлер** `handle_voice()` — срабатывает **только на `voice`** (видео-кружочки не обрабатываем):

1. Проверить `chat.type == "private"`
2. Скачать аудио через Bot API → байты в памяти
3. POST на DeepGram API:
   ```
   URL: https://api.deepgram.com/v1/listen?model=nova-2&language=ru
   Header: Authorization: Token <DEEPGRAM_API_KEY>
   Body: аудио-байты
   Content-Type: audio/ogg
   ```
4. Парсинг ответа: `response["results"]["channels"][0]["alternatives"][0]["transcript"]`
5. Определить `forward_from` (если пересланное сообщение)
6. Если активна тема → присвоить `topic_id`
7. `save_recording(...)` в БД
8. Ответить подтверждением + inline-кнопками

**Ответ бота после голосового:**

```
✅ Сохранено (0:42)
```

Inline-кнопки под сообщением:
```
[ 📝 Summary ]  [ 📄 Текстом ]  [ 📁 Файлом ]
```

- **📝 Summary** → Groq генерирует краткий пересказ → бот отправляет новым сообщением
- **📄 Текстом** → бот отправляет полную транскрипцию текстовым сообщением (если > 4096 символов — разбить на несколько сообщений)
- **📁 Файлом** → бот отправляет `.txt` файл с транскрипцией

### Поиск по записям

**Текстовое сообщение** = поисковый запрос. Бот ищет по полю `transcript` (SQL `LIKE`).

Ответ:
```
🔍 Найдено 3 записи по "встреча":

1. 7 апреля, 14:32 (1:23)
   "...обсудили встречу с клиентом..."
   → http://<IP>:8080/r/42

2. 5 апреля, 09:15 (0:45)
   "...перенести встречу на пятницу..."
   → http://<IP>:8080/r/38
```

Если ничего не найдено: "🔍 Ничего не найдено по запросу «...»"

Показывать до 10 результатов. Каждый результат: дата, время, длительность, фрагмент транскрипции с совпадением (±50 символов вокруг), ссылка на веб.

### Режим "Тема" (пачка голосовых)

**Команда** `/topic` — начать тему:

1. Бот создаёт запись в `topics`, запоминает `topic_id` в user context
2. Отвечает: "📂 Тема начата. Отправляйте голосовые — они будут объединены."
3. Все последующие голосовые получают этот `topic_id`
4. Показывает inline-кнопку: `[ ✅ Завершить тему ]`

**Завершение темы:**

1. Закрывает тему (`closed_at = now`)
2. Отвечает итогом: "📂 Тема закрыта. N голосовых, общая длительность X:XX"
3. Inline-кнопки:
   ```
   [ 📝 Summary темы ]  [ 📄 Вся тема текстом ]  [ 📁 Файлом ]
   ```
4. Summary темы = Groq получает все транскрипции темы одним промптом

**Хранение состояния темы:** `active_topics: dict[int, int]` (user_id → topic_id) в памяти. При перезапуске бота незакрытые темы автоматически закрываются (`close_topic`).

### Groq API вызов (для summary)

```python
POST https://api.groq.com/openai/v1/chat/completions
Headers:
    Authorization: Bearer <GROQ_API_KEY>
    Content-Type: application/json
Body:
{
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "system", "content": "Сделай краткий пересказ голосовой заметки на русском языке. 2-3 предложения, только суть."},
        {"role": "user", "content": "<транскрипция>"}
    ],
    "temperature": 0.3,
    "max_tokens": 500
}
```

Парсинг: `response["choices"][0]["message"]["content"]`

### Остальные сообщения

Фото, видео, файлы, стикеры → бот отвечает:
"Я принимаю только голосовые сообщения. Текст = поиск по записям."

---

## 8. Веб-интерфейс (web.py)

### Авторизация

**Простой пароль с cookie-сессией:**

1. Middleware: на каждый запрос (кроме `/login`, `/robots.txt`) проверить cookie `session_token`
2. Если нет или невалидный → redirect на `/login`
3. `POST /login` — сверить пароль с `WEB_PASSWORD` из env
4. Если верный → установить cookie `session_token` (случайный токен, `httponly=True`, `max_age=30 дней`)
5. Хранение валидных токенов: `set()` в памяти (при перезапуске сервиса — перелогин, это нормально)

### Защита от поисковиков

- `GET /robots.txt` → `User-agent: *\nDisallow: /`
- Заголовок `X-Robots-Tag: noindex, nofollow` на **всех** ответах (через `@app.after_request`)

### Роуты

| Метод | URL | Действие |
|-------|-----|----------|
| GET | `/` | Лента всех записей с пагинацией |
| GET | `/r/<id>` | Детальная страница одной записи |
| GET | `/r/topic/<id>` | Детальная страница темы (все записи) |
| GET | `/login` | Форма ввода пароля |
| POST | `/login` | Проверка пароля |
| POST | `/logout` | Удаление cookie, redirect на `/login` |
| POST | `/delete/<id>` | Удалить запись |
| POST | `/delete-topic/<id>` | Удалить тему + все её записи |
| GET | `/robots.txt` | Disallow all |

### Лента записей (GET /)

**Query-параметры:**
- `page=1` — пагинация (по 20 записей)

Лента отображает **все записи**, сгруппированные по дням. Дни разделены заголовками-отбивками.

**Отображение:**

```
┌─────────────────────────────────────────────┐
│  🎙 Voice Inbox                  [Выйти]   │
│                                             │
│  ── 7 апреля 2026 ─────────────────────── │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 14:32  ⏱ 1:23                  🗑️  │    │
│  │ ↩️ Переслано от: Иван              │    │
│  │ ▶ Показать транскрипцию            │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 📂 Тема (3 голосовых) ⏱ 4:15  🗑️  │    │
│  │ ▶ Показать транскрипции            │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ── 6 апреля 2026 ─────────────────────── │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 18:05  ⏱ 0:33                  🗑️  │    │
│  │ ▶ Показать транскрипцию            │    │
│  └─────────────────────────────────────┘    │
│                                             │
│            ◀ Назад    Вперёд ▶              │
└─────────────────────────────────────────────┘
```

**Ключевые моменты UI:**
- Записи сортируются по дате — **новые сверху**
- Дни разделены заголовками-отбивками с датой
- Транскрипции **скрыты по умолчанию** (`<details><summary>`)
- Темы отображаются как одна карточка с общей длительностью
- Каждая карточка — ссылка на детальную страницу
- Кнопка удаления с подтверждением (`confirm()`)
- Время записи + длительность
- Пометка "переслано от" если есть `forward_from`

### Детальная страница записи (GET /r/<id>)

```
┌─────────────────────────────────────────────┐
│  ← Назад к ленте                           │
│                                             │
│  7 апреля 2026, 14:32                      │
│  Длительность: 1:23                        │
│  ↩️ Переслано от: Иван                     │
│                                             │
│  ── Транскрипция ────────────────────────  │
│  Полный текст транскрипции без             │
│  сворачивания, целиком.                    │
│                                             │
│  ── Summary ─────────────────────────────  │
│  Краткий пересказ (если был сгенерирован   │
│  ранее через бота).                        │
│                                             │
│  [🗑️ Удалить запись]                       │
└─────────────────────────────────────────────┘
```

### Детальная страница темы (GET /r/topic/<id>)

```
┌─────────────────────────────────────────────┐
│  ← Назад к ленте                           │
│                                             │
│  📂 Тема — 7 апреля 2026                  │
│  3 голосовых, общая длительность: 4:15     │
│                                             │
│  ── Запись 1 (14:32, 0:42) ──────────────  │
│  Полный текст первой записи...             │
│                                             │
│  ── Запись 2 (14:35, 1:33) ──────────────  │
│  Полный текст второй записи...             │
│                                             │
│  ── Запись 3 (14:40, 2:00) ──────────────  │
│  Полный текст третьей записи...            │
│                                             │
│  ── Summary темы ────────────────────────  │
│  Общий пересказ (если есть).               │
│                                             │
│  [🗑️ Удалить тему]                         │
└─────────────────────────────────────────────┘
```

### Дизайн

- **Тёмная тема** (CSS variables: `--bg: #111113`, `--card-bg: #1c1c1f`, `--text: #e0e0e0`, `--accent: #5b5bff`)
- Адаптивная вёрстка (мобильный + десктоп, `@media` 480px)
- Vanilla CSS, без фреймворков
- Минимальный JS: collapsible `<details>` (нативный) + `confirm()` на удаление

---

## 9. Точка входа (main.py)

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voice-inbox")

# 1. init_db()
# 2. Закрыть незавершённые темы (WHERE closed_at IS NULL → SET closed_at = now)
# 3. Запустить Flask + Waitress в daemon thread (host="0.0.0.0", port=WEB_PORT)
# 4. Запустить бота run_polling() в main thread
# 5. logger.info("Bot started, web panel on port %s", WEB_PORT)
```

---

## 10. Конфигурация сервера

### systemd-сервис

Файл `/etc/systemd/system/voice-inbox.service`:

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

### .gitignore

```
.env
*.db
__pycache__/
.venv/
```

### .env.example

```
TELEGRAM_BOT_TOKEN=
DEEPGRAM_API_KEY=
GROQ_API_KEY=
WEB_PASSWORD=
WEB_PORT=8080
```

---

## 11. Логирование

Единый формат через стандартный `logging` Python.

### Что логируем

| Событие | Уровень | Пример |
|---------|---------|--------|
| Запуск бота и веб-сервера | INFO | `Bot started, web panel on port 8080` |
| Получено голосовое | INFO | `Voice received: duration=42s, message_id=456` |
| DeepGram вызов | INFO | `DeepGram request: 42s audio, 15234 bytes` |
| DeepGram ответ | INFO | `DeepGram response: 350 chars transcript` |
| DeepGram ошибка | ERROR | `DeepGram error: 401 Unauthorized` |
| Groq вызов | INFO | `Groq request: 350 chars input` |
| Groq ответ | INFO | `Groq response: 120 chars summary` |
| Groq ошибка | ERROR | `Groq error: 429 Rate limit exceeded` |
| Запись сохранена | INFO | `Recording saved: id=12, topic_id=None` |
| Тема создана/закрыта | INFO | `Topic created: id=3` / `Topic closed: id=3, 5 recordings` |
| Поиск | INFO | `Search: query="встреча", found=3` |
| Веб: логин | INFO | `Web login: success` / `Web login: wrong password` |
| Веб: удаление | INFO | `Web delete: recording id=12` |
| Неожиданная ошибка | ERROR | Полный traceback |

### Куда пишем

- **stdout** — systemd автоматически перенаправляет в `journalctl`
- Просмотр логов: `journalctl -u voice-inbox -f`
- Никаких файлов логов — systemd управляет ротацией

---

## 12. Обработка ошибок

### Принцип

Бот **не должен падать** из-за ошибки в одном сообщении. Каждый хэндлер обёрнут в try/except. При ошибке:
1. Логируем полный traceback (`logger.error(..., exc_info=True)`)
2. Отвечаем пользователю понятным сообщением
3. Продолжаем работу

### Ошибки DeepGram

| Ситуация | Действие |
|----------|----------|
| HTTP 401 (неверный ключ) | Ответ: "❌ Ошибка транскрипции. Проверьте DEEPGRAM_API_KEY в логах." |
| HTTP 429 (rate limit) | Ответ: "⏳ Сервис транскрипции перегружен. Попробуйте через минуту." |
| Таймаут / сетевая ошибка | Ответ: "❌ Не удалось связаться с сервисом транскрипции." |
| Пустая транскрипция | Сохранить запись с `transcript = "(нет речи)"`. Ответ: "✅ Сохранено (0:42)\n⚠️ Речь не распознана." |

### Ошибки Groq

| Ситуация | Действие |
|----------|----------|
| HTTP 401 / 429 / таймаут | Ответ: "❌ Не удалось сгенерировать summary. Попробуйте позже." |
| Любая ошибка | Summary не сохраняется. Запись остаётся без summary. |

### Ошибки веб-интерфейса

| Ситуация | Действие |
|----------|----------|
| Запись не найдена (GET /r/<id>) | Страница 404 с текстом "Запись не найдена" |
| Ошибка БД | Страница 500 с текстом "Внутренняя ошибка" + лог |
| Неверный пароль | Форма логина с сообщением "Неверный пароль" |

### Ошибки при запуске

| Ситуация | Действие |
|----------|----------|
| Нет `TELEGRAM_BOT_TOKEN` | `sys.exit("TELEGRAM_BOT_TOKEN не задан в .env")` |
| Нет `DEEPGRAM_API_KEY` | `sys.exit("DEEPGRAM_API_KEY не задан в .env")` |
| Нет `GROQ_API_KEY` | Запуск без summary. Лог: `WARNING: GROQ_API_KEY не задан, summary отключены` |
| Нет `WEB_PASSWORD` | `sys.exit("WEB_PASSWORD не задан в .env")` |
| Порт занят | Waitress сам выдаст ошибку → лог + exit |

### Таймауты API-запросов

- DeepGram: **30 секунд** (длинные голосовые)
- Groq: **15 секунд**
- Настраиваются через `httpx.AsyncClient(timeout=...)`

---

## 13. Верификация

После деплоя агент проверяет:

- [ ] systemd-сервис запущен (`systemctl status voice-inbox`)
- [ ] Логи чистые (`journalctl -u voice-inbox --no-pager -n 20`)
- [ ] Бот отвечает на `/start`
- [ ] Веб-панель доступна по `http://<IP>:8080`
- [ ] Без пароля → redirect на `/login`
- [ ] Пароль принимается → лента
- [ ] Отправить голосовое → бот отвечает "✅ Сохранено" + кнопки
- [ ] Кнопка "Summary" → Groq возвращает пересказ
- [ ] Кнопка "Текстом" → полная транскрипция
- [ ] Кнопка "Файлом" → .txt документ
- [ ] Текстовое сообщение → поиск по записям с результатами
- [ ] Пересланное голосовое → сохраняется с пометкой "переслано от"
- [ ] `/topic` → несколько голосовых → завершить → объединено
- [ ] Детальная страница записи открывается по ссылке
- [ ] Удаление записи через веб
- [ ] Удаление темы через веб (каскадное)
- [ ] `robots.txt` отдаёт `Disallow: /`
- [ ] Лента разбита по дням отбивками

---

## 14. Что НЕ входит в scope

- Текстовые, фото, видео, файловые сообщения — только голосовые
- Видео-кружочки (video_note) — только voice
- HTTPS / SSL — учебный проект, HTTP
- Отдельный пользователь для Linux — root (с пометкой)
- Ограничение доступа к боту по user ID — бот открыт для всех
- Бэкапы БД
- Rate limiting
- Мультиязычность
- Полнотекстовый поиск (FTS) — используем простой LIKE

---

## docs/ — Отчёты по фазам

- В этом файле встроенные отчёты не ведутся.
- Отчёт каждой фазы хранится отдельно в `docs/phase-N.md`.
- Перед записью первого отчёта агент обязан создать папку `docs/`, если её ещё нет.
