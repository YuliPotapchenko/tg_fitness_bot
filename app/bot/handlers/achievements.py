"""Экран «Мои достижения»: статистика, серия, ачивки."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.utils import show
from app.db.models import User
from app.services import progress as svc

router = Router(name="achievements")


@router.callback_query(F.data == "ach")
async def achievements(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    stats = await svc.get_stats(session, user)
    await show(cb, texts.achievements(stats), keyboards.achievements(), user)
