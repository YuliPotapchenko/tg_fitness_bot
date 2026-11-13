# Фитнес-бот Дениса Вовка (Telegram + Tilda)

Покупатель оплачивает подписку на Tilda → Tilda шлёт webhook → бэкенд создаёт подписку и deep-link →
покупатель переходит по ссылке в Telegram-бота и получает доступ к тренировкам.

Стек: Python 3.11+, aiogram 3, FastAPI, SQLAlchemy 2 (async) + asyncpg, PostgreSQL (Neon), хостинг Render (free).

---

## 1. Архитектура

```
 Tilda (оплата) ──POST /tilda-webhook?secret=…──┐
                                                ▼
 Telegram ──POST /telegram-webhook──►  ┌─────────────────────────────┐
 (секретный заголовок)                 │  ОДИН процесс (uvicorn)     │
                                       │  FastAPI  ──►  aiogram      │
 UptimeRobot ──HEAD /health──────────► │     │            │          │
                                       │     └─ services ─┘          │
                                       │   (подписки, прогресс,      │
                                       │    серии, ачивки, пуши)     │
                                       │  + фоновая задача push_loop │
                                       └──────────────┬──────────────┘
                                                      ▼ SQLAlchemy + asyncpg (SSL)
                                              PostgreSQL на Neon
```

**Как взаимодействуют части**

1. **FastAPI** — единственная «входная дверь»: принимает webhook Tilda, webhook Telegram и health-пинги.
2. **aiogram** не опрашивает Telegram сам: FastAPI-эндпоинт `/telegram-webhook` получает апдейт и передаёт его в
   `dp.feed_update()`. Бот и API живут в одном event loop и делят один пул соединений с БД.
3. **PostgreSQL** хранит всё состояние (бот «stateless»: после перезапуска или засыпания ничего не теряется).
4. **Связка Tilda → Telegram**: вебхук создаёт `users` с уникальным `start_token`. Ссылка
   `https://t.me/<bot>?start=<token>` приходит боту как `/start <token>`; по токену мы привязываем `telegram_id`.

**Почему webhook, а не polling.** Бесплатный Render усыпляет сервис через ~15 минут без входящих HTTP-запросов.
При polling бот в этот момент «глохнет». Входящий webhook Telegram сам разбудит сервис, а пинг UptimeRobot
раз в 5 минут не даёт ему заснуть совсем. Polling включается автоматически только если публичный URL не задан
(локальная разработка).

**Single Message.** Каждый экран — это редактирование одного и того же сообщения (`edit_message_text`,
см. `app/bot/utils.py`). Если пользователь пишет текст или жмёт `/start`, мы удаляем его сообщение и старое
сообщение бота и отправляем одно новое. Нажатие на кнопку никогда не создаёт новых сообщений.

**Правила тренировок** (`app/services/progress.py`)
- Выдаётся только `current_day` текущего марафона; выбрать день вручную нельзя.
- «Я выполнил» фиксирует дату; до завтра экран тренировки закрыт. Одна тренировка в день.
- Двойной клик безопасен (блокировка строки пользователя `SELECT … FOR UPDATE`).
- Серия (streak) растёт, если вчера была тренировка, иначе начинается с 1.
- Прогресс хранится отдельной строкой `user_progress` на каждый марафон — при смене марафона ничего не теряется.
- «Заморозки/паузы» нет.

---

## 2. Структура проекта и ответственность модулей

```
tg_fitness_bot/
├── app/
│   ├── main.py                  # Точка входа: lifespan (БД, seed, webhook/polling, пуши), /telegram-webhook
│   ├── config.py                # Настройки из переменных окружения (pydantic-settings)
│   ├── api/
│   │   ├── tilda.py             # POST /tilda-webhook: валидация, создание подписки, deep-link, email
│   │   └── health.py            # /health (для UptimeRobot, без БД) и /health/db
│   ├── bot/
│   │   ├── setup.py             # Создание Bot и Dispatcher, подключение роутеров, обработчик ошибок
│   │   ├── middlewares.py       # Сессия БД на апдейт, загрузка пользователя, проверка подписки
│   │   ├── utils.py             # show(): механика Single Message (edit_message_text)
│   │   ├── screens.py           # Экраны, вызываемые из нескольких мест (меню, каталог, нет доступа)
│   │   ├── keyboards.py         # Все inline-клавиатуры и callback_data
│   │   ├── texts.py             # Все тексты экранов (чистые функции)
│   │   └── handlers/
│   │       ├── start.py         # Экран 1: онбординг по deep-link
│   │       ├── menu.py          # Экран 2: главное меню (+ fallback на любой текст)
│   │       ├── workout.py       # Экраны 3–4: тренировка, «Я выполнил», обратная связь
│   │       ├── catalog.py       # Экран 5: каталог марафонов
│   │       ├── achievements.py  # Экран 6: достижения
│   │       └── settings.py      # Экран 7: настройки и время пушей
│   ├── services/
│   │   ├── subscriptions.py     # Создание/продление подписки, генерация токена и deep-link
│   │   ├── progress.py          # Прогресс, серии, обратная связь, ачивки, статистика
│   │   ├── scheduler.py         # Фоновая рассылка пуш-напоминаний
│   │   └── mailer.py            # Письмо покупателю со ссылкой (Resend HTTP API)
│   └── db/
│       ├── base.py              # DeclarativeBase
│       ├── session.py           # Engine для Neon (SSL, pre_ping, retry при «пробуждении»), init_db
│       ├── models.py            # User, Marathon, Workout, UserProgress, WorkoutLog, Achievement, UserAchievement
│       └── seed.py              # Ачивки и 2 демо-марафона («База 1.0», «Стальные тиски»)
├── requirements.txt
├── render.yaml                  # Blueprint для Render
├── .env.example
└── README.md
```

---

## 3. Модели БД (`app/db/models.py`)

| Таблица | Назначение |
|---|---|
| `users` | Подписчик: email, телефон, `telegram_id` (NULL до привязки), `start_token`, `subscription_end`, тариф, серия, время пуша |
| `marathons` | Программы (название, описание, число дней) |
| `workouts` | Тренировка дня: текст + ссылка на видео, уникальна по (марафон, день) |
| `user_progress` | Прогресс пользователя в КАЖДОМ марафоне (`current_day`, `completed_days`, `is_finished`) |
| `workout_logs` | Журнал выполненных дней + обратная связь `easy/normal/hard` |
| `achievements` / `user_achievements` | Справочник ачивок и полученные пользователем |

Таблицы создаются автоматически при старте (`create_all`). Для дальнейших изменений схемы подключите Alembic.

---

## 4. Webhook Tilda

**URL:** `https://<ваш-сервис>.onrender.com/tilda-webhook?secret=<TILDA_SECRET>`

Принимает `application/x-www-form-urlencoded` (так шлёт Tilda) и JSON. Поля (регистр не важен):

| Поле | Обязательно | Описание |
|---|---|---|
| `email` | да | Идентификатор покупателя |
| `phone` | нет | Телефон |
| `subscription_end` | да* | Дата окончания: `2026-12-31` или `31.12.2026` |
| `days` | да* | Альтернатива: «сколько дней подписки от сегодня» |
| `tariff` | нет | Название тарифа |

\* нужно одно из двух.

Ответ: `{"ok": true, "status": "created|updated", "deeplink": "https://t.me/<bot>?start=<token>"}`.
Повторный вебхук с тем же email **продлевает** подписку (токен остаётся прежним) и пишет пользователю в бот.

> ⚠️ **Tilda не показывает ответ вебхука покупателю.** Поэтому ссылку нужно доставить отдельно: сервис отправляет её
> на email через Resend (если задан `EMAIL_API_KEY`) и пишет в логи Render. Дату окончания (или `days`) передавайте
> скрытым полем формы / параметром оплаты — Tilda сама её не вычисляет.

---

## 5. Бесплатный деплой: Render + Neon + UptimeRobot

### Шаг 1. Telegram-бот
1. В Telegram откройте **@BotFather** → `/newbot` → получите `BOT_TOKEN`.
2. Запомните username бота (без `@`) — это `BOT_USERNAME`.
3. Сгенерируйте два секрета (команда ниже) — `TELEGRAM_WEBHOOK_SECRET` и `TILDA_SECRET`:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Шаг 2. База данных на Neon
1. Зарегистрируйтесь на https://neon.tech → **Create project** (регион ближе к Render, например Frankfurt).
2. На странице проекта нажмите **Connect** и скопируйте строку подключения вида
   `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   Подойдёт как прямая, так и «pooled» строка: приложение само вырезает `sslmode`/`channel_binding`
   и отключает кэш prepared statements.
3. Это и есть `DATABASE_URL`. Таблицы создадутся сами при первом запуске.

> Neon «засыпает» после нескольких минут без запросов и просыпается за 1–3 секунды — приложение это учитывает
> (`pool_pre_ping`, повторные попытки при старте). Эндпоинт `/health` специально **не** ходит в БД, чтобы
> пинги UptimeRobot не держали Neon проснувшимся и не расходовали бесплатные часы вычислений.

### Шаг 3. Код на GitHub
```bash
cd tg_fitness_bot
git init && git add . && git commit -m "Initial commit"
# создайте пустой репозиторий на GitHub и выполните:
git remote add origin https://github.com/<вы>/<репозиторий>.git
git push -u origin main
```
Файл `.env` в репозиторий не попадает (он в `.gitignore`).

### Шаг 4. Сервис на Render
1. https://render.com → **New → Web Service** → подключите репозиторий.
2. Настройки:
   - **Runtime:** Python 3, **Instance Type:** Free
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
   (Либо **New → Blueprint** — Render прочитает `render.yaml`.)
3. Вкладка **Environment** — добавьте переменные (таблица ниже) и `PYTHON_VERSION=3.11.9`.
4. **Create Web Service.** После деплоя URL будет вида `https://fitness-bot-xxxx.onrender.com`.
   Render сам задаёт `RENDER_EXTERNAL_URL`, и бот при старте автоматически ставит Telegram webhook на этот адрес.
5. Проверьте: откройте `https://<url>/health` → `{"status":"ok"}`, затем в боте отправьте `/start`.

### Шаг 5. UptimeRobot (чтобы Render не засыпал)
1. https://uptimerobot.com → **Add New Monitor**.
2. **Monitor Type:** HTTP(s), **URL:** `https://<ваш-сервис>.onrender.com/health`.
3. **Monitoring Interval:** 5 минут (минимум на бесплатном тарифе; сон наступает через 15 минут простоя).
4. Сохраните. Бесплатный UptimeRobot шлёт HEAD-запросы — эндпоинт `/health` их поддерживает.

### Шаг 6. Подключение Tilda
1. Tilda → **Настройки сайта → Формы → Webhook** (или «Другие сервисы → Webhook»).
2. URL: `https://<сервис>.onrender.com/tilda-webhook?secret=<TILDA_SECRET>` → сохраните; Tilda отправит тестовый
   запрос (`test=test`), ответ должен быть `ok: true`.
3. В форме оплаты добавьте поля с именами переменных `email`, `phone` и скрытое `subscription_end` (или `days`).

### Переменные окружения

| Переменная | Обяз. | Описание |
|---|---|---|
| `BOT_TOKEN` | да | Токен от @BotFather |
| `BOT_USERNAME` | да | Username бота без `@` (для deep-link) |
| `DATABASE_URL` | да | Строка подключения Neon |
| `TELEGRAM_WEBHOOK_SECRET` | да | Секрет заголовка Telegram webhook (`A-Za-z0-9_-`) |
| `TILDA_SECRET` | да | Секрет для `/tilda-webhook` |
| `SITE_URL` | нет | Ссылка на сайт (кнопка «Продлить подписку») |
| `TIMEZONE` | нет | По умолчанию `Europe/Moscow` («завтра» и время пушей считаются по нему) |
| `PUBLIC_URL` | нет | Свой домен, если не Render. Пусто на Render и локально |
| `EMAIL_API_KEY`, `EMAIL_FROM` | нет | Resend: отправка deep-link покупателю на email |
| `LOG_LEVEL` | нет | `INFO` по умолчанию |

### Локальный запуск
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # заполните значения; PUBLIC_URL оставьте пустым => polling
uvicorn app.main:app --reload
```
Проверка вебхука Tilda:
```bash
curl -X POST "http://localhost:8000/tilda-webhook?secret=<TILDA_SECRET>" \
  -d "email=test@example.com&phone=+79990000000&subscription_end=31.12.2026"
```

---

## 6. Ограничения бесплатных тарифов (учтите заранее)

- **Render free:** сервис спит без запросов (лечит UptimeRobot), есть месячный лимит бесплатных часов
  (одного сервиса 24/7 хватает). Исходящий SMTP на бесплатном тарифе, насколько мне известно, закрыт — поэтому
  письма уходят через HTTP API (Resend). Первый запрос после холодного старта может занять до минуты.
- **Neon free:** лимит часов вычислений и объёма. Актуальные цифры смотрите на странице тарифов.
- **Пуши** работают только пока сервис бодрствует; планировщик обращается к БД лишь в минуты, на которые
  назначены уведомления (чтобы не будить Neon зря).
- Контент тренировок (демо-данные в `app/db/seed.py`) замените на реальный: тексты и ссылки на видео
  (YouTube/Vimeo/Telegram) хранятся в таблице `workouts`. Видео открывается кнопкой-ссылкой, т.к. текстовое
  сообщение нельзя «отредактировать» в видео.
