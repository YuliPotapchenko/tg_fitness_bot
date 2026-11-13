"""Эндпоинт /tilda-webhook — приём данных об оплате с сайта Tilda.

Настройка в Tilda: Настройки сайта -> Формы -> Webhook:
    https://<ваш-сервис>.onrender.com/tilda-webhook?secret=<TILDA_SECRET>

Tilda шлёт POST (обычно application/x-www-form-urlencoded) с полями формы. Ожидаем:
    email              — обязательно
    phone              — необязательно
    subscription_end   — дата окончания (2026-12-31 / 31.12.2026)
    days               — альтернатива subscription_end: «сколько дней подписки от сегодня»
    tariff             — название тарифа (необязательно)
Названия полей регистронезависимы (Email/EMAIL тоже подойдут).

Ответ: JSON {"ok": true, "deeplink": "https://t.me/<bot>?start=<token>", ...}.
ВАЖНО: Tilda не показывает ответ вебхука покупателю, поэтому ссылку дополнительно отправляем на email
(если настроен EMAIL_API_KEY) и пишем в лог.
"""
import hmac
import logging

from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db.session import session_maker
from app.services import mailer, subscriptions as subs

log = logging.getLogger(__name__)
router = APIRouter()


async def _read_payload(request: Request) -> dict[str, str]:
    """Читает тело как JSON или form-data и приводит ключи к нижнему регистру."""
    ctype = request.headers.get("content-type", "")
    try:
        if "application/json" in ctype:
            raw = await request.json()
            if not isinstance(raw, dict):
                raise ValueError("JSON должен быть объектом")
        else:
            raw = dict(await request.form())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Не удалось разобрать тело запроса: {exc}") from exc
    return {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if v is not None}


def _pick(data: dict[str, str], *names: str) -> str | None:
    for name in names:
        if data.get(name):
            return data[name]
    return None


@router.post("/tilda-webhook")
async def tilda_webhook(
    request: Request,
    secret: str | None = Query(default=None),
    x_tilda_secret: str | None = Header(default=None),
):
    data = await _read_payload(request)

    # 1. Проверка секрета (query, заголовок или скрытое поле формы)
    provided = secret or x_tilda_secret or data.get("secret") or ""
    if not hmac.compare_digest(provided.encode(), settings.TILDA_SECRET.encode()):
        log.warning("Tilda webhook: неверный секрет с IP %s", request.client.host if request.client else "?")
        raise HTTPException(status_code=403, detail="Forbidden")

    # 2. Тестовый запрос из интерфейса Tilda («test=test») — просто отвечаем OK
    if data.get("test") == "test":
        return {"ok": True, "test": True}

    # 3. Валидация полей
    email = _pick(data, "email", "e-mail", "mail")
    if not email or not subs.EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Поле email отсутствует или некорректно")

    end_raw = _pick(data, "subscription_end", "end_date", "date_end", "expires")
    days_raw = _pick(data, "days")
    try:
        if end_raw:
            end_date = subs.parse_date(end_raw)
        elif days_raw:
            end_date = subs.default_end_from_days(int(days_raw))
        else:
            raise ValueError("Передайте subscription_end или days")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    phone = subs.normalize_phone(_pick(data, "phone", "телефон"))
    tariff = _pick(data, "tariff", "тариф")

    # 4. Запись в БД
    try:
        async with session_maker() as session:
            user, created = await subs.upsert_subscription(
                session, email=email, phone=phone, subscription_end=end_date, tariff=tariff
            )
            await session.commit()
            token, telegram_id = user.start_token, user.telegram_id
    except SQLAlchemyError:
        log.exception("Ошибка БД в tilda-webhook")
        # 503 => Tilda может повторить запрос позже
        raise HTTPException(status_code=503, detail="Database error") from None

    deeplink = subs.make_deeplink(token)

    # 5. Уведомления (ошибки здесь не должны ломать ответ вебхука)
    if created or telegram_id is None:
        await mailer.send_deeplink_email(subs.normalize_email(email), deeplink)
    else:
        try:
            await request.app.state.bot.send_message(
                telegram_id, f"✅ Подписка продлена до <b>{end_date.strftime('%d.%m.%Y')}</b>. Спасибо, что с нами! 💪"
            )
        except TelegramAPIError as exc:
            log.warning("Не удалось уведомить о продлении %s: %s", telegram_id, exc)

    return {"ok": True, "status": "created" if created else "updated", "deeplink": deeplink}
