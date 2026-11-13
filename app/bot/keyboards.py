"""Inline-клавиатуры. Все callback_data собраны здесь, чтобы не разбегались по хендлерам.

Формат callback_data:
    menu | workout:start | workout:done | fb:<easy|normal|hard>
    catalog | mar:view:<id> | mar:pick:<id>
    ach | settings | push:toggle | push:time | push:set:<HHMM>
"""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import settings
from app.db.models import Marathon, UserProgress

BACK_TO_MENU = ("⬅️ В меню", "menu")


def _builder(rows: list[list[tuple[str, str]]], urls: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for row in rows:
        for text, data in row:
            b.button(text=text, callback_data=data)
    b.adjust(*[len(r) for r in rows])
    return b.as_markup()


def main_menu(has_marathon: bool, done_today: bool, finished: bool) -> InlineKeyboardMarkup:
    if not has_marathon:
        first = ("📚 Выбрать марафон", "catalog")
    elif finished:
        first = ("🏁 Марафон пройден — выбрать новый", "catalog")
    elif done_today:
        first = ("✅ Сегодня выполнено", "workout:start")
    else:
        first = ("▶️ Начать тренировку", "workout:start")
    return _builder([[first], [("📚 Каталог", "catalog"), ("🏆 Достижения", "ach")], [("⚙️ Настройки", "settings")]])


def onboarding() -> InlineKeyboardMarkup:
    return _builder([[("🚀 Выбрать марафон", "catalog")], [("🏠 Главное меню", "menu")]])


def only_menu() -> InlineKeyboardMarkup:
    return _builder([[BACK_TO_MENU]])


def menu_and_catalog() -> InlineKeyboardMarkup:
    return _builder([[("📚 Каталог", "catalog")], [BACK_TO_MENU]])


def workout(video_url: str | None) -> InlineKeyboardMarkup:
    """Экран тренировки: ссылка на видео (url-кнопка) + «Я выполнил»."""
    b = InlineKeyboardBuilder()
    if video_url:
        b.button(text="▶️ Смотреть видео", url=video_url)
    b.button(text="✅ Я выполнил", callback_data="workout:done")
    b.button(text=BACK_TO_MENU[0], callback_data=BACK_TO_MENU[1])
    b.adjust(1)
    return b.as_markup()


def feedback() -> InlineKeyboardMarkup:
    return _builder([[("😌 Легко", "fb:easy"), ("👌 Нормально", "fb:normal"), ("🥵 Тяжело", "fb:hard")]])


def catalog(marathons: list[Marathon], progress: dict[int, UserProgress], current_id: int | None) -> InlineKeyboardMarkup:
    rows = []
    for m in marathons:
        p = progress.get(m.id)
        pct = round(100 * p.completed_days / m.total_days) if p and m.total_days else 0
        mark = "▶️ " if m.id == current_id else ("🏁 " if p and p.is_finished else "")
        rows.append([(f"{mark}{m.title} · {pct}%", f"mar:view:{m.id}")])
    rows.append([BACK_TO_MENU])
    return _builder(rows)


def marathon_card(marathon_id: int, is_current: bool) -> InlineKeyboardMarkup:
    pick = ("✅ Продолжить", f"mar:pick:{marathon_id}") if is_current else ("🎯 Выбрать этот марафон", f"mar:pick:{marathon_id}")
    return _builder([[pick], [("⬅️ К каталогу", "catalog")]])


def achievements() -> InlineKeyboardMarkup:
    return _builder([[BACK_TO_MENU]])


def settings_kb(push_enabled: bool) -> InlineKeyboardMarkup:
    toggle = "🔕 Выключить напоминания" if push_enabled else "🔔 Включить напоминания"
    rows = [[(toggle, "push:toggle")]]
    if push_enabled:
        rows.append([("⏰ Изменить время", "push:time")])
    rows.append([BACK_TO_MENU])
    b = InlineKeyboardBuilder()
    for row in rows:
        for text, data in row:
            b.button(text=text, callback_data=data)
    b.button(text="🔄 Продлить подписку", url=settings.SITE_URL)
    b.adjust(*[len(r) for r in rows], 1)
    return b.as_markup()


PUSH_TIMES = ["06:00", "07:00", "08:00", "09:00", "10:00", "12:00", "15:00", "18:00", "19:00", "20:00", "21:00", "22:00"]


def push_times() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in PUSH_TIMES:
        b.button(text=t, callback_data=f"push:set:{t.replace(':', '')}")
    b.button(text="⬅️ Назад", callback_data="settings")
    b.adjust(3, 3, 3, 3, 1)
    return b.as_markup()


def push_start() -> InlineKeyboardMarkup:
    """Клавиатура под пуш-уведомлением."""
    return _builder([[("▶️ Начать тренировку", "workout:start")], [BACK_TO_MENU]])


def no_access(expired: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Продлить подписку" if expired else "💳 Оформить подписку", url=settings.SITE_URL)
    return b.as_markup()
