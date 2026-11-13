"""Middleware: сессия БД, загрузка пользователя и проверка подписки.

Для каждого входящего сообщения/нажатия кнопки:
  1. открывается сессия SQLAlchemy (data["session"]) — одна транзакция на апдейт;
  2. по telegram_id загружается пользователь (data["user"], может быть None);
  3. если подписки нет/истекла — хендлер НЕ вызывается, показывается экран «нет доступа»
     (исключение: команда /start, через неё пользователь привязывает аккаунт по deep-link);
  4. после успешной обработки — commit, при исключении — rollback.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.screens import show_no_access
from app.db.session import session_maker
from app.services import progress as svc

log = logging.getLogger(__name__)


class DbAndAccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Сразу «гасим» индикатор загрузки на кнопке
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except TelegramAPIError:
                pass  # запрос мог устареть (бот «просыпался» после простоя) — не критично

        # Работаем только в личных чатах (группы и каналы игнорируем)
        chat = event.chat if isinstance(event, Message) else getattr(event.message, "chat", None)
        if chat is None or chat.type != "private":
            return None

        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return None

        async with session_maker() as session:
            user = await svc.get_user_by_tg(session, tg_user.id)
            data["session"] = session
            data["user"] = user

            is_start = isinstance(event, Message) and (event.text or "").startswith("/start")
            has_access = user is not None and svc.subscription_active(user)

            try:
                if is_start or has_access:
                    result = await handler(event, data)
                else:
                    await show_no_access(event, user)  # type: ignore[arg-type]
                    result = None
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
