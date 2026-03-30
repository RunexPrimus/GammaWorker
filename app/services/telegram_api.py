from __future__ import annotations

import json
import httpx

from app.config import settings


async def tg_request(method: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{settings.telegram_api_base}/{method}", data=payload)
    try:
        data = response.json()
    except Exception:
        raise RuntimeError(f"Telegram raw error: status={response.status_code}, body={response.text}")
    if response.status_code >= 400 or not data.get("ok"):
        desc = str(data.get("description", ""))
        if response.status_code == 403 and "blocked by the user" in desc.lower():
            return {"ok": False, "blocked": True, "description": desc}
        raise RuntimeError(f"Telegram API error: status={response.status_code}, body={data}")
    return data["result"]


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": str(chat_id), "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return await tg_request("sendMessage", payload)


async def edit_message(chat_id: int, message_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": str(chat_id), "message_id": str(message_id), "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return await tg_request("editMessageText", payload)


async def send_document_by_url(chat_id: int, url: str, caption: str) -> dict:
    payload = {"chat_id": str(chat_id), "document": url, "caption": caption, "parse_mode": "HTML"}
    return await tg_request("sendDocument", payload)


async def answer_callback(callback_query_id: str, text: str = "") -> dict:
    return await tg_request("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})


def _miniapp_url() -> str | None:
    base = settings.normalized_app_base_url
    if not base or "localhost" in base:
        return None
    if not base.startswith("https://"):
        return None
    return f"{base}/miniapp"


def home_keyboard() -> dict:
    rows: list[list[dict]] = [[{"text": "⚡ Bir prompt bilan", "callback_data": "home:fast"}]]
    miniapp_url = _miniapp_url()
    if miniapp_url:
        rows.append([{"text": "🎛 Studio", "web_app": {"url": miniapp_url}}])
    rows.append([{"text": "📦 Presetlar", "callback_data": "home:presets"}])
    return {"inline_keyboard": rows}


def presets_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🧠 Investor", "callback_data": "preset:investor"}],
            [{"text": "📈 Sales", "callback_data": "preset:sales"}],
            [{"text": "🎓 Lesson", "callback_data": "preset:lesson"}],
            [{"text": "📊 Report", "callback_data": "preset:report"}],
            [{"text": "⬅️ Orqaga", "callback_data": "home:back"}],
        ]
    }


def confirm_brief_keyboard() -> dict:
    rows: list[list[dict]] = [
        [{"text": "✅ Ha, boshlash", "callback_data": "confirm:start"}],
        [{"text": "✏️ Qayta yozaman", "callback_data": "confirm:rewrite"}],
    ]
    miniapp_url = _miniapp_url()
    if miniapp_url:
        rows.append([{"text": "🎛 Studio", "web_app": {"url": miniapp_url}}])
    rows.append([{"text": "❌ Bekor", "callback_data": "wizard:cancel:cancel"}])
    return {"inline_keyboard": rows}
