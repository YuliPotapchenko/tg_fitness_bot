"""Общие экраны, которые вызываются из нескольких хендлеров (главное меню, каталог, «нет доступа»)."""
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.utils import show
from app.db.models import Marathon, User
from app.services import progress as svc


async def show_main_menu(event: Message | CallbackQuery, session: AsyncSession, user: User) -> None:
    marathon = progress = None
    if user.current_marathon_id:
        marathon = await session.get(Marathon, user.current_marathon_id)
        if marathon:
            progress = await svc.get_progress(session, user.id, marathon.id)

    kb = keyboards.main_menu(
        has_marathon=marathon is not None,
        done_today=svc.done_today(user),
        finished=bool(progress and progress.is_finished),
    )
    await show(event, texts.main_menu(user, marathon, progress), kb, user)


async def show_catalog(event: Message | CallbackQuery, session: AsyncSession, user: User) -> None:
    marathons = await svc.list_marathons(session)
    progress = await svc.progress_map(session, user.id)
    await show(event, texts.catalog(), keyboards.catalog(marathons, progress, user.current_marathon_id), user)


async def show_no_access(event: Message | CallbackQuery, user: User | None) -> None:
    """Нет подписки / подписка истекла."""
    expired = user is not None
    text = texts.no_access_expired(user) if user else texts.NO_ACCESS_UNKNOWN
    await show(event, text, keyboards.no_access(expired), user)
