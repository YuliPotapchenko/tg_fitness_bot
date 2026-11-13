"""Точка входа: FastAPI + aiogram в одном процессе.

  POST /telegram-webhook  <- Telegram присылает апдейты (режим webhook, если известен публичный URL)
  POST /tilda-webhook     <- Tilda присылает данные об оплате
  GET|HEAD /health        <- для UptimeRobot / Render

Почему webhook, а не polling, на бесплатном Render: сервис «засыпает» без входящих HTTP-запросов.
Polling в этот момент замирает, а входящий webhook Telegram сам разбудит сервис. UptimeRobot (пинг раз в
5 минут) не даёт сервису заснуть вовсе. Если публичного URL нет (локальная разработка) — включается polling.

Запуск: uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import hmac
import logging
from contextlib import asynccontextmanager, suppress

from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request

from app.api import health, tilda
from app.bot.setup import create_bot, create_dispatcher
from app.config import settings
from app.db.seed import seed_database
from app.db.session import engine, init_db, session_maker
from app.services.scheduler import push_loop

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")

WEBHOOK_PATH = "/telegram-webhook"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. БД: таблицы + начальные данные (Neon может «просыпаться» — init_db повторяет попытки)
    await init_db()
    async with session_maker() as session:
        await seed_database(session)

    # 2. Бот
    bot = create_bot()
    dp = create_dispatcher()
    app.state.bot, app.state.dp = bot, dp
    tasks: list[asyncio.Task] = []

    if settings.base_url:
        await bot.set_webhook(
            url=f"{settings.base_url}{WEBHOOK_PATH}",
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=dp.resolve_used_update_types(),
        )
        log.info("Webhook установлен: %s%s", settings.base_url, WEBHOOK_PATH)
    else:
        await bot.delete_webhook()
        tasks.append(asyncio.create_task(dp.start_polling(bot, handle_signals=False)))
        log.warning("PUBLIC_URL не задан — бот работает в режиме polling (только для разработки)")

    # 3. Фоновые пуши
    tasks.append(asyncio.create_task(push_loop(bot)))

    yield

    # Остановка. Webhook НЕ удаляем: при деплое новая версия уже могла его выставить.
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError, Exception):
            await task
    await bot.session.close()
    await engine.dispose()


app = FastAPI(title="Fitness bot", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(health.router)
app.include_router(tilda.router)


@app.post(WEBHOOK_PATH, include_in_schema=False)
async def telegram_webhook(request: Request) -> dict:
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(token.encode(), settings.TELEGRAM_WEBHOOK_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")

    bot, dp = request.app.state.bot, request.app.state.dp
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:  # noqa: BLE001
        # Всегда отвечаем 200: иначе Telegram будет бесконечно повторять «проблемный» апдейт
        log.exception("Ошибка обработки апдейта Telegram")
    return {"ok": True}
