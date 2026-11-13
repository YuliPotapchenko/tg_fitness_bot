"""Онбординг: /start с deep-link токеном (после оплаты) и обычный /start.

Deep-link вида https://t.me/<bot>?start=<token> приходит в Telegram как «/start <token>».
Токен однозначно указывает на запись users, созданную вебхуком Tilda, — так мы привязываем
telegram_id покупателя к его подписке.
"""
import datetime as dt
import logging

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.screens import show_main_menu, show_no_access
from app.bot.utils import show
from app.db.models import User
from app.services import progress as svc

log = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def start_with_token(message: Message, command: CommandObject, session: AsyncSession, user: User | None) -> None:
    token = (command.args or "").strip()
    owner = (await session.execute(select(User).where(User.start_token == token))).scalar_one_or_none()

    if owner is None:
        await show(message, texts.link_invalid(), None, user)
        return

    tg = message.from_user
    # Ссылка уже использована другим Telegram-аккаунтом
    if owner.telegram_id is not None and owner.telegram_id != tg.id:
        await show(message, texts.link_used(), None, user)
        return
    # Этот Telegram уже привязан к ДРУГОЙ подписке
    if user is not None and user.id != owner.id:
        await show(message, texts.account_conflict(), None, user)
        return

    first_time = owner.activated_at is None
    if owner.telegram_id is None:
        owner.telegram_id = tg.id
        owner.first_name = tg.first_name
        owner.activated_at = dt.datetime.now(dt.timezone.utc)
        # Назначаем первый марафон по умолчанию — меню сразу будет «живым»
        marathons = await svc.list_marathons(session)
        if marathons and owner.current_marathon_id is None:
            owner.current_marathon_id = marathons[0].id
            await svc.get_progress(session, owner.id, marathons[0].id)
        await session.flush()
        log.info("Пользователь %s привязан к Telegram %s", owner.email, tg.id)

    if not svc.subscription_active(owner):
        await show_no_access(message, owner)
    elif first_time:
        await show(message, texts.onboarding(owner), keyboards.onboarding(), owner)
    else:
        await show_main_menu(message, session, owner)


@router.message(CommandStart())
async def start_plain(message: Message, session: AsyncSession, user: User | None) -> None:
    """/start без токена: известным подписчикам — меню, остальным — «нет доступа»."""
    if user is not None and svc.subscription_active(user):
        await show_main_menu(message, session, user)
    else:
        await show_no_access(message, user)
