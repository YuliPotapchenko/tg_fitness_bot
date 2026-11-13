"""Начальное наполнение БД: ачивки и демо-марафоны.

Идемпотентно: запускается при каждом старте и добавляет только то, чего ещё нет.
Видео-ссылки ниже — заглушки. Замените их на реальные (YouTube/Vimeo/Telegram-ссылки)
прямо в таблице workouts или поправьте этот файл до первого запуска.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Achievement, Marathon, Workout

log = logging.getLogger(__name__)

# (code, icon, title, description)
ACHIEVEMENTS = [
    ("first_workout", "🥇", "Первый шаг", "Выполнить первую тренировку"),
    ("streak_3", "🔥", "Разогрев", "3 дня подряд"),
    ("streak_7", "⚡", "Неделя силы", "7 дней подряд"),
    ("streak_14", "💎", "Железная воля", "14 дней подряд"),
    ("workouts_10", "💪", "Десятка", "Выполнить 10 тренировок"),
    ("workouts_30", "🏅", "Тридцатник", "Выполнить 30 тренировок"),
    ("marathon_finished", "🏁", "Финишер", "Завершить марафон целиком"),
]

_DEMO_VIDEO = "https://example.com/video"

MARATHONS = [
    {
        "slug": "base-1-0",
        "title": "База 1.0",
        "description": "Стартовая программа: учимся двигаться правильно и выстраиваем привычку тренироваться.",
        "days": [
            ("Знакомство и разминка", "Суставная разминка 5 минут, затем 3 круга: приседания 15, отжимания от колен 10, планка 30 сек."),
            ("Ноги и ягодицы", "4 круга: выпады 12 на ногу, ягодичный мостик 20, приседания 15. Отдых между кругами 60 сек."),
            ("Верх тела", "4 круга: отжимания 10, тяга резинки к поясу 15, обратные отжимания от стула 12."),
            ("Кор и пресс", "3 круга: скручивания 20, подъём ног 15, «велосипед» 30 сек, планка 40 сек."),
            ("Кардио-интервалы", "8 раундов: 30 сек работа (бёрпи/прыжки) / 30 сек отдых. Затем заминка и растяжка."),
            ("Всё тело", "Круговая: приседания, отжимания, выпады, планка — 4 круга по 40 сек работы / 20 сек отдыха."),
            ("Итоговый тест недели", "Максимум повторов за 1 минуту: приседания, отжимания, пресс. Запишите результаты!"),
        ],
    },
    {
        "slug": "steel-grip",
        "title": "Стальные тиски",
        "description": "Силовой марафон на хват, предплечья и кор. Для тех, кто хочет крепкую хватку и устойчивое тело.",
        "days": [
            ("Хват: основа", "Вис на турнике 3×30 сек, сжимание эспандера 3×20, ферма-уок 3×20 м."),
            ("Предплечья", "Сгибания кисти 4×15, разгибания 4×15, «молот» с гантелью 3×12."),
            ("Тяга", "Подтягивания (или негативы) 5×5, тяга гантели 4×10, вис на одной руке 3×10 сек."),
            ("Кор-стабилизация", "Планка 3×60 сек, боковая планка 3×40 сек, «мёртвый жук» 3×15."),
            ("Статический хват", "Вис 4×max, удержание блина щипком 4×20 сек, ферма-уок 4×30 м."),
            ("Силовая круговая", "5 кругов: подтягивания 5, отжимания 15, выпады 12, вис 20 сек."),
            ("Контрольный день", "Максимальный вис на турнике, максимум подтягиваний, планка на максимум."),
        ],
    },
]


async def seed_database(session: AsyncSession) -> None:
    # --- ачивки ---
    existing_codes = set((await session.execute(select(Achievement.code))).scalars())
    for order, (code, icon, title, desc) in enumerate(ACHIEVEMENTS, start=1):
        if code not in existing_codes:
            session.add(Achievement(code=code, icon=icon, title=title, description=desc, sort_order=order))

    # --- марафоны ---
    existing_slugs = set((await session.execute(select(Marathon.slug))).scalars())
    for order, data in enumerate(MARATHONS, start=1):
        if data["slug"] in existing_slugs:
            continue
        marathon = Marathon(
            slug=data["slug"],
            title=data["title"],
            description=data["description"],
            total_days=len(data["days"]),
            sort_order=order,
        )
        session.add(marathon)
        await session.flush()
        for day, (title, text) in enumerate(data["days"], start=1):
            session.add(
                Workout(marathon_id=marathon.id, day_number=day, title=title, text=text, video_url=_DEMO_VIDEO)
            )
        log.info("Добавлен демо-марафон: %s", data["title"])

    await session.commit()
