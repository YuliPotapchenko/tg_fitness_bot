"""Отправка письма покупателю со ссылкой на бота (через HTTP API Resend).

Почему не SMTP: на бесплатных тарифах хостингов исходящий SMTP часто закрыт, а HTTP работает всегда.
Если EMAIL_API_KEY не задан — функция ничего не делает (ссылку всё равно можно взять из ответа вебхука/логов).
"""
import logging

import httpx

from app.config import settings

log = logging.getLogger(__name__)


async def send_deeplink_email(to_email: str, deeplink: str) -> bool:
    if not settings.EMAIL_API_KEY or not settings.EMAIL_FROM:
        log.info("Email не настроен, письмо для %s не отправлено. Deep-link: %s", to_email, deeplink)
        return False

    html = (
        "<p>Спасибо за покупку! 💪</p>"
        f'<p>Чтобы открыть тренировки, нажмите: <a href="{deeplink}">Открыть бота в Telegram</a></p>'
        f"<p>Если кнопка не работает, скопируйте ссылку: {deeplink}</p>"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
                json={"from": settings.EMAIL_FROM, "to": [to_email], "subject": "Ваш доступ к тренировкам", "html": html},
            )
        if resp.status_code >= 300:
            log.error("Resend вернул %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except httpx.HTTPError:
        log.exception("Не удалось отправить письмо на %s", to_email)
        return False
