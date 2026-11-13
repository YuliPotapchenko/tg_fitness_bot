"""Каталог марафонов. Смена марафона не удаляет прогресс: у каждого марафона своя строка user_progress."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, texts
from app.bot.screens import show_catalog, show_main_menu
from app.bot.utils import show
from app.db.models import Marathon, User
from app.services import progress as svc

router = Router(name="catalog")


def _parse_id(data: str | None) -> int | None:
    try:
        return int((data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


@router.callback_query(F.data == "catalog")
async def catalog(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    await show_catalog(cb, session, user)


@router.callback_query(F.data.startswith("mar:view:"))
async def marathon_view(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    marathon = await _get_active(session, _parse_id(cb.data))
    if marathon is None:
        await show_catalog(cb, session, user)
        return
    progress = (await svc.progress_map(session, user.id)).get(marathon.id)
    is_current = user.current_marathon_id == marathon.id
    await show(
        cb, texts.marathon_card(marathon, progress, is_current), keyboards.marathon_card(marathon.id, is_current), user
    )


@router.callback_query(F.data.startswith("mar:pick:"))
async def marathon_pick(cb: CallbackQuery, session: AsyncSession, user: User) -> None:
    marathon = await _get_active(session, _parse_id(cb.data))
    if marathon is None:
        await show_catalog(cb, session, user)
        return
    # Если прогресс уже есть — он просто «подхватывается»; иначе создаётся с 1-го дня
    await svc.get_progress(session, user.id, marathon.id)
    user.current_marathon_id = marathon.id
    await show_main_menu(cb, session, user)


async def _get_active(session: AsyncSession, marathon_id: int | None) -> Marathon | None:
    if marathon_id is None:
        return None
    marathon = await session.get(Marathon, marathon_id)
    return marathon if marathon and marathon.is_active else None
