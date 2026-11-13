"""Сборка Bot и Dispatcher: роутеры, middleware, глобальный обработчик ошибок."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent

from app.bot.handlers import achievements, catalog, menu, settings, start, workout
from app.bot.middlewares import DbAndAccessMiddleware
from app.config import settings as cfg

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(token=cfg.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _on_error(event: ErrorEvent) -> bool:
    """Любая необработанная ошибка: пишем в лог, пользователю показываем всплывающее сообщение."""
    log.exception("Ошибка при обработке апдейта", exc_info=event.exception)
    cb = event.update.callback_query
    if cb is not None:
        try:
            await cb.answer("Что-то пошло не так, попробуйте ещё раз 🙏", show_alert=True)
        except Exception:  # noqa: BLE001
            pass
    return True


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Проверка «только личные чаты» и подписки выполняется в middleware
    mw = DbAndAccessMiddleware()
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)

    # Порядок важен: menu (с fallback) — последним
    dp.include_routers(
        start.router,
        workout.router,
        catalog.router,
        achievements.router,
        settings.router,
        menu.router,
    )
    dp.errors.register(_on_error)
    return dp
