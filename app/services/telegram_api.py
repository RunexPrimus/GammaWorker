from __future__ import annotations

import contextlib
import httpx
from app.config import settings


async def tg_request(method: str, payload: dict | None = None) -> dict:
    url = f"{settings.telegram_api_base}/{method}"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, data=payload)
    try:
        data = response.json()
    except Exception:
        raise RuntimeError(f'Telegram raw error: status={response.status_code}, body={response.text}')
    if response.status_code >= 400 or not data.get('ok'):
        desc = (data.get('description') or '').lower()
        if response.status_code == 403 and 'blocked by the user' in desc:
            return {'ok': False, 'blocked': True, 'description': data.get('description')}
        raise RuntimeError(f'Telegram API error: status={response.status_code}, body={data}')
    return data['result']


async def edit_message(chat_id: int, message_id: int, text: str) -> dict | None:
    with contextlib.suppress(Exception):
        return await tg_request('editMessageText', {
            'chat_id': str(chat_id),
            'message_id': str(message_id),
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': 'true',
        })
    return None


async def send_document_by_url(chat_id: int, url: str, caption: str) -> dict | None:
    with contextlib.suppress(Exception):
        return await tg_request('sendDocument', {
            'chat_id': str(chat_id),
            'document': url,
            'caption': caption,
            'parse_mode': 'HTML',
        })
    return None
