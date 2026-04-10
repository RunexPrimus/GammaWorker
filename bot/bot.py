from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
import telegram.error
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import Settings
from logging_setup import setup_logging
from models import LANGUAGES, UserPreferences
from services.presenton_client import PresentonAPIError, PresentonClient, PresentonTask
from task_store import TaskStore

logger = logging.getLogger(__name__)

PREFS_KEY = "prefs"
WAITING_TOPIC_KEY = "waiting_topic"
WAITING_FILE_KEY = "waiting_file"
WAITING_LANG_KEY = "waiting_lang"

ACTIVE_STATUSES = {"pending", "processing", "queued", "running", "in_progress"}
SUCCESS_STATUSES = {"completed", "success", "succeeded", "done"}
FAIL_STATUSES = {"failed", "error", "cancelled", "canceled"}


# ── State helpers ──────────────────────────────────────────────────────────────

def _user_id(update: Update) -> int:
    user = update.effective_user
    return int(user.id) if user else 0


def _chat_id(update: Update) -> int:
    chat = update.effective_chat
    return int(chat.id) if chat else 0


def app_state(application: Application) -> dict[str, Any]:
    state = application.bot_data.get("state")
    if isinstance(state, dict):
        return state
    raise RuntimeError("Application state not initialized")


def get_settings(application: Application) -> Settings:
    return app_state(application)["settings"]


def get_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> UserPreferences:
    user = update.effective_user
    state = app_state(context.application)
    default_prefs: UserPreferences = state["default_prefs"]
    if user is None:
        return UserPreferences.from_any(default_prefs.to_dict())

    cached = context.user_data.get(PREFS_KEY)
    if cached is not None:
        prefs = UserPreferences.from_any(cached)
        context.user_data[PREFS_KEY] = prefs.to_dict()
        return prefs

    prefs = state["task_store"].get_user_preferences(user.id, default_prefs)
    context.user_data[PREFS_KEY] = prefs.to_dict()
    return prefs


def save_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE, prefs: UserPreferences) -> UserPreferences:
    prefs = prefs.normalize()
    context.user_data[PREFS_KEY] = prefs.to_dict()
    user = update.effective_user
    if user is not None:
        app_state(context.application)["task_store"].save_user_preferences(user.id, prefs)
    return prefs


# ── Menus ──────────────────────────────────────────────────────────────────────

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🆕 Yangi deck", callback_data="menu:new")],
            [InlineKeyboardButton("📎 Fayl yuklash", callback_data="menu:file")],
            [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="menu:settings")],
            [InlineKeyboardButton("📌 Oxirgi task", callback_data="menu:last")],
        ]
    )


def settings_menu(prefs: UserPreferences) -> InlineKeyboardMarkup:
    c = "✅"

    def _t(val: str, label: str, cb: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(f"{label}{' ' + c if prefs.standard_template == val else ''}", callback_data=cb)

    def _th(val: str, label: str, cb: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(f"{label}{' ' + c if prefs.theme == val else ''}", callback_data=cb)

    image_label = "Stock 🖼" if prefs.image_type == "stock" else "AI 🤖"
    toc_label = f"TOC {'ON ✅' if prefs.include_table_of_contents else 'OFF'}"
    ws_label = f"Web 🔍{'✅' if prefs.web_search else ''}"

    return InlineKeyboardMarkup(
        [
            # Slides
            [
                InlineKeyboardButton(f"10{' ' + c if prefs.n_slides == 10 else ''}", callback_data="slides:10"),
                InlineKeyboardButton(f"12{' ' + c if prefs.n_slides == 12 else ''}", callback_data="slides:12"),
                InlineKeyboardButton(f"15{' ' + c if prefs.n_slides == 15 else ''}", callback_data="slides:15"),
                InlineKeyboardButton(f"20{' ' + c if prefs.n_slides == 20 else ''}", callback_data="slides:20"),
            ],
            # Tone
            [
                InlineKeyboardButton(f"Prof{' ' + c if prefs.tone == 'professional' else ''}", callback_data="tone:professional"),
                InlineKeyboardButton(f"Edu{' ' + c if prefs.tone == 'educational' else ''}", callback_data="tone:educational"),
                InlineKeyboardButton(f"Sales{' ' + c if prefs.tone == 'sales_pitch' else ''}", callback_data="tone:sales_pitch"),
                InlineKeyboardButton(f"Fun{' ' + c if prefs.tone == 'funny' else ''}", callback_data="tone:funny"),
            ],
            # Verbosity
            [
                InlineKeyboardButton(f"Qisqa{' ' + c if prefs.verbosity == 'concise' else ''}", callback_data="verbosity:concise"),
                InlineKeyboardButton(f"Standart{' ' + c if prefs.verbosity == 'standard' else ''}", callback_data="verbosity:standard"),
                InlineKeyboardButton(f"To'liq{' ' + c if prefs.verbosity == 'text-heavy' else ''}", callback_data="verbosity:text-heavy"),
            ],
            # Template row 1
            [
                _t("neo-standard", "Neo-Std", "template:neo-standard"),
                _t("neo-general", "Neo-Gen", "template:neo-general"),
                _t("neo-modern", "Neo-Mod", "template:neo-modern"),
                _t("neo-swift", "Neo-Swift", "template:neo-swift"),
            ],
            # Template row 2
            [
                _t("standard", "Standard", "template:standard"),
                _t("general", "General", "template:general"),
                _t("modern", "Modern", "template:modern"),
                _t("swift", "Swift", "template:swift"),
            ],
            # Theme row 1
            [
                _th("professional-blue", "🔵Blue", "theme:professional-blue"),
                _th("professional-dark", "⚫Dark", "theme:professional-dark"),
                _th("mint-blue", "🩵Mint", "theme:mint-blue"),
            ],
            # Theme row 2
            [
                _th("edge-yellow", "🟡Yellow", "theme:edge-yellow"),
                _th("light-rose", "🌹Rose", "theme:light-rose"),
            ],
            # Format
            [
                InlineKeyboardButton(f"PPTX{' ' + c if prefs.export_as == 'pptx' else ''}", callback_data="format:pptx"),
                InlineKeyboardButton(f"PDF{' ' + c if prefs.export_as == 'pdf' else ''}", callback_data="format:pdf"),
            ],
            # Toggles
            [
                InlineKeyboardButton(image_label, callback_data="images:toggle"),
                InlineKeyboardButton(toc_label, callback_data="toc:toggle"),
                InlineKeyboardButton(ws_label, callback_data="websearch:toggle"),
            ],
            # Language
            [InlineKeyboardButton(f"🌐 Til: {prefs.language}", callback_data="menu:lang")],
            # Back
            [InlineKeyboardButton("🔙 Bosh menyu", callback_data="menu:main")],
        ]
    )


def language_menu() -> InlineKeyboardMarkup:
    rows = []
    chunk = []
    for lang in LANGUAGES:
        chunk.append(InlineKeyboardButton(lang, callback_data=f"lang:{lang}"))
        if len(chunk) == 3:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    rows.append([InlineKeyboardButton("🔙 Sozlamalar", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


# ── Command handlers ───────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prefs = get_prefs(update, context)
    settings = get_settings(context.application)
    text = (
        "🎞 <b>Presenton Telegram Bot</b>\n\n"
        "Mavzu yuboring yoki fayl yuboring — men <b>Presenton</b> orqali professional PPTX/PDF tayyorlayman.\n\n"
        f"🔗 API: <code>{settings.presenton_api_root}</code>\n"
        f"📊 Hozirgi sozlamalar: {prefs.n_slides} slides · {prefs.tone} · {prefs.verbosity} · "
        f"{prefs.standard_template} · {prefs.theme} · {prefs.language}"
    )
    await update.effective_message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📖 <b>Buyruqlar:</b>\n\n"
        "/start — bosh menyu\n"
        "/new — mavzu bilan yangi deck\n"
        "/file — fayl yuborib deck yaratish\n"
        "/settings — deck parametrlari\n"
        "/status — oxirgi task holati\n"
        "/last — oxirgi task tafsiloti\n"
        "/cancel — kutish holatini bekor qilish\n\n"
        "💡 <b>Misol:</b>\n"
        "/new → <i>AI in healthcare: trends & opportunities 2025</i>\n\n"
        "📎 Yoki /file → PDF/DOCX/PPTX yuboring\n\n"
        "⚙️ Barcha parametrlar (slides soni, tema, til va boshqalar) "
        "/settings orqali o'rnatiladi.",
        parse_mode="HTML",
    )


async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[WAITING_TOPIC_KEY] = True
    context.user_data[WAITING_FILE_KEY] = False
    context.user_data[WAITING_LANG_KEY] = False
    prefs = get_prefs(update, context)
    await update.effective_message.reply_text(
        "✍️ Mavzuni yuboring. Masalan:\n\n"
        "<i>AI in healthcare: trends, opportunities, risks</i>\n"
        "<i>2025 yil marketing strategiyasi</i>\n\n"
        f"📋 Hozirgi sozlamalar: {prefs.n_slides} slides · {prefs.tone} · {prefs.language}",
        parse_mode="HTML",
    )


async def file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[WAITING_FILE_KEY] = True
    context.user_data[WAITING_TOPIC_KEY] = False
    context.user_data[WAITING_LANG_KEY] = False
    await update.effective_message.reply_text(
        "📎 Fayl yuboring (PDF, DOCX, TXT, MD, PPTX).\n\n"
        "💬 Xohlasangiz caption'da qo'shimcha ko'rsatma yozing."
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[WAITING_TOPIC_KEY] = False
    context.user_data[WAITING_FILE_KEY] = False
    context.user_data[WAITING_LANG_KEY] = False
    await update.effective_message.reply_text("❌ Bekor qilindi.", reply_markup=main_menu())


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prefs = get_prefs(update, context)
    await update.effective_message.reply_text(
        "⚙️ <b>Sozlamalar</b>\n\nKerakli parametrni tanlang:",
        reply_markup=settings_menu(prefs),
        parse_mode="HTML",
    )


async def last_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: TaskStore = app_state(context.application)["task_store"]
    last = store.get_latest_for_user(_user_id(update))
    if not last:
        await update.effective_message.reply_text("Hali task yo'q.", reply_markup=main_menu())
        return
    text = _format_stored_task(last)
    await update.effective_message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = app_state(context.application)
    store: TaskStore = state["task_store"]
    client: PresentonClient = state["presenton_client"]
    user_id = _user_id(update)
    last = store.get_latest_for_user(user_id)
    if not last:
        await update.effective_message.reply_text("Hali task yo'q.", reply_markup=main_menu())
        return
    try:
        task = await client.get_task_status(last.task_id)
        data = _extract_task_payload(task)
        store.upsert_task(
            task_id=task.task_id or last.task_id,
            user_id=user_id,
            chat_id=last.chat_id,
            topic=last.topic,
            status=task.status,
            output_url=data.get("path"),
            edit_url=data.get("edit_path"),
            file_format=_infer_format(data.get("path")),
            updated_at=data.get("updated_at"),
            raw_json=json.dumps(task.raw, ensure_ascii=False),
        )
        await update.effective_message.reply_text(
            _format_status_message(last.topic, task),
            reply_markup=main_menu(),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.exception("Status lookup failed", extra={"user_id": user_id, "stage": "status", "job_id": None})
        await update.effective_message.reply_text(f"⚠️ Status tekshirib bo'lmadi.\n<code>{_exc_summary(exc)}</code>", parse_mode="HTML")


# ── Callback router ────────────────────────────────────────────────────────────

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    prefs = get_prefs(update, context)
    store: TaskStore = app_state(context.application)["task_store"]
    user_id = _user_id(update)
    data = query.data or ""

    # ── Menu actions ──────────────────────────────────────────────────────────
    if data == "menu:new":
        context.user_data[WAITING_TOPIC_KEY] = True
        context.user_data[WAITING_FILE_KEY] = False
        context.user_data[WAITING_LANG_KEY] = False
        await query.message.reply_text(
            "✍️ Mavzuni yuboring. Misol:\n<i>AI in healthcare: trends, risks, future outlook</i>",
            parse_mode="HTML",
        )
        return

    if data == "menu:file":
        context.user_data[WAITING_FILE_KEY] = True
        context.user_data[WAITING_TOPIC_KEY] = False
        context.user_data[WAITING_LANG_KEY] = False
        await query.message.reply_text("📎 Fayl yuboring (PDF, DOCX, TXT, MD, PPTX).")
        return

    if data == "menu:settings":
        await query.message.edit_text(
            "⚙️ <b>Sozlamalar</b>",
            reply_markup=settings_menu(prefs),
            parse_mode="HTML",
        )
        return

    if data == "menu:main":
        await query.message.edit_text("🏠 Bosh menyu", reply_markup=main_menu())
        return

    if data == "menu:lang":
        await query.message.edit_text(
            "🌐 <b>Til tanlang:</b>",
            reply_markup=language_menu(),
            parse_mode="HTML",
        )
        return

    if data == "menu:last":
        last = store.get_latest_for_user(user_id)
        if not last:
            await query.message.reply_text("Hali task yo'q.")
            return
        await query.message.reply_text(_format_stored_task(last), parse_mode="HTML")
        return

    # ── Language selection ────────────────────────────────────────────────────
    if data.startswith("lang:"):
        prefs.language = data.split(":", 1)[1]
        save_prefs(update, context, prefs)
        await query.message.edit_text(
            f"✅ Til o'zgartirildi: <b>{prefs.language}</b>",
            reply_markup=settings_menu(prefs),
            parse_mode="HTML",
        )
        return

    # ── Settings toggles ──────────────────────────────────────────────────────
    if data.startswith("slides:"):
        prefs.n_slides = int(data.split(":", 1)[1])
    elif data.startswith("tone:"):
        prefs.tone = data.split(":", 1)[1]
    elif data.startswith("verbosity:"):
        prefs.verbosity = data.split(":", 1)[1]
    elif data.startswith("template:"):
        prefs.standard_template = data.split(":", 1)[1]
    elif data.startswith("theme:"):
        prefs.theme = data.split(":", 1)[1]
    elif data.startswith("format:"):
        prefs.export_as = data.split(":", 1)[1]
    elif data == "images:toggle":
        prefs.image_type = "ai-generated" if prefs.image_type == "stock" else "stock"
    elif data == "toc:toggle":
        prefs.include_table_of_contents = not prefs.include_table_of_contents
    elif data == "websearch:toggle":
        prefs.web_search = not prefs.web_search
    else:
        return

    save_prefs(update, context, prefs)
    try:
        await query.message.edit_text(
            "⚙️ <b>Sozlamalar saqlandi</b>",
            reply_markup=settings_menu(prefs),
            parse_mode="HTML",
        )
    except telegram.error.BadRequest:
        pass


# ── Message handlers ───────────────────────────────────────────────────────────

async def topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text or text.startswith("/"):
        return

    if not context.user_data.get(WAITING_TOPIC_KEY):
        await update.effective_message.reply_text(
            "Avval /new bosing yoki menyudan «🆕 Yangi deck» tanlang.",
            reply_markup=main_menu(),
        )
        return

    context.user_data[WAITING_TOPIC_KEY] = False
    await _start_generation_from_topic(update, context, topic=text)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.effective_message.document
    if not document:
        return

    if not context.user_data.get(WAITING_FILE_KEY):
        await update.effective_message.reply_text(
            "Avval /file bosing yoki menyudan «📎 Fayl yuklash» tanlang.",
            reply_markup=main_menu(),
        )
        return

    context.user_data[WAITING_FILE_KEY] = False
    settings = get_settings(context.application)
    user_id = _user_id(update)

    if document.file_size and document.file_size > settings.max_upload_size_bytes:
        await update.effective_message.reply_text(
            f"⚠️ Fayl juda katta. Limit: {settings.max_upload_size_mb} MB."
        )
        return

    suffix = Path(document.file_name or "upload.bin").suffix.lower()
    allowed = {".pdf", ".docx", ".txt", ".md", ".pptx"}
    if suffix not in allowed:
        await update.effective_message.reply_text(
            "⚠️ Hozircha PDF, DOCX, TXT, MD yoki PPTX yuboring."
        )
        return

    topic = (update.effective_message.caption or document.file_name or "Uploaded file presentation").strip()
    progress = await update.effective_message.reply_text("📥 Fayl yuklab olinmoqda...")
    tmp_dir = Path(settings.tmp_dir)
    tmp_path = tmp_dir / f"tg_{user_id}_{uuid.uuid4().hex[:8]}{suffix}"

    try:
        tg_file = await context.bot.get_file(document.file_id)
        await tg_file.download_to_drive(custom_path=str(tmp_path))
        await _start_generation_from_topic(
            update, context,
            topic=topic,
            local_files=[tmp_path],
            progress_message=progress,
        )
    except Exception as exc:
        logger.exception("Telegram file handling failed", extra={"user_id": user_id, "stage": "download", "job_id": None})
        await _safe_edit(progress, f"❌ Faylni tayyorlab bo'lmadi.\n<code>{_exc_summary(exc)}</code>", parse_mode="HTML")
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── Core generation flow ───────────────────────────────────────────────────────

async def _start_generation_from_topic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    topic: str,
    local_files: list[Path] | None = None,
    progress_message=None,
) -> None:
    prefs = get_prefs(update, context)
    user_id = _user_id(update)
    chat_id = _chat_id(update)
    job_id = uuid.uuid4().hex[:8]
    progress = progress_message or await update.effective_message.reply_text("⏳ Ish boshlandi...")

    state = app_state(context.application)
    semaphore: asyncio.Semaphore = state["generation_semaphore"]

    async with semaphore:
        client: PresentonClient = state["presenton_client"]
        store: TaskStore = state["task_store"]
        settings = get_settings(context.application)

        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

            files_ids: list[str] = []
            if local_files:
                await _safe_edit(progress, "📤 Presenton'ga fayl yuklanmoqda...")
                upload_result = await client.upload_files(local_files)
                files_ids = upload_result.file_ids
                logger.info(
                    "Files uploaded: %s", files_ids,
                    extra={"job_id": job_id, "user_id": user_id, "stage": "upload"},
                )

            await _safe_edit(
                progress,
                f"🧠 Task yaratilmoqda...\n📌 Mavzu: <i>{_truncate(topic, 80)}</i>",
                parse_mode="HTML",
            )

            payload = build_presenton_payload(topic, prefs, settings, files_ids=files_ids)
            task = await client.generate_async(payload)

            if not task.task_id:
                raise RuntimeError(f"Presenton task id yo'q. Response: {str(task.raw)[:300]}")

            logger.info(
                "Task created: %s", task.task_id,
                extra={"job_id": job_id, "user_id": user_id, "stage": "create_task"},
            )
            data = _extract_task_payload(task)
            store.upsert_task(
                task_id=task.task_id,
                user_id=user_id,
                chat_id=chat_id,
                topic=topic,
                status=task.status,
                output_url=data.get("path"),
                edit_url=data.get("edit_path"),
                file_format=_infer_format(data.get("path")),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                raw_json=json.dumps(task.raw, ensure_ascii=False),
            )

            await _safe_edit(
                progress,
                f"🛠 Task yaratildi!\n"
                f"🆔 ID: <code>{task.task_id}</code>\n"
                f"⏳ Presenton deck tayyorlayapti...",
                parse_mode="HTML",
            )

            await poll_until_done(
                context=context,
                progress_message=progress,
                task_id=task.task_id,
                topic=topic,
                chat_id=chat_id,
                user_id=user_id,
                job_id=job_id,
            )

        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.error(
                "Network error connecting to Presenton: %s", exc,
                extra={"job_id": job_id, "user_id": user_id, "stage": "network_error"},
            )
            settings_str = get_settings(context.application).presenton_api_root
            await _safe_edit(
                progress,
                f"❌ <b>Presenton serveriga ulanib bo'lmadi</b>\n\n"
                f"URL: <code>{settings_str}</code>\n\n"
                f"Tekshiring:\n"
                f"• <code>PRESENTON_BASE_URL</code> to'g'ri o'rnatilganmi?\n"
                f"• Server ishlab turibdimi?\n"
                f"• Cloud uchun: <code>https://api.presenton.ai</code>\n"
                f"• Self-hosted: server IP/URL to'g'rimi?",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )

        except PresentonAPIError as exc:
            logger.error(
                "Presenton API error %s", exc.status_code,
                extra={"job_id": job_id, "user_id": user_id, "stage": "api_error"},
            )
            await _safe_edit(
                progress,
                f"❌ <b>Presenton API xato: {exc.status_code}</b>\n\n"
                f"<code>{exc.body[:400]}</code>",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )

        except Exception as exc:
            logger.exception(
                "Generation failed", exc_info=exc,
                extra={"job_id": job_id, "user_id": user_id, "stage": "error"},
            )
            await _safe_edit(
                progress,
                f"❌ Deck yaratishda xato: <code>{_exc_summary(exc)}</code>\n\n"
                "/status bilan keyinroq tekshirib ko'ring.",
                parse_mode="HTML",
                reply_markup=main_menu(),
            )

        finally:
            for path in local_files or []:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass


async def poll_until_done(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    progress_message,
    task_id: str,
    topic: str,
    chat_id: int,
    user_id: int,
    job_id: str,
) -> None:
    settings = get_settings(context.application)
    state = app_state(context.application)
    client: PresentonClient = state["presenton_client"]
    store: TaskStore = state["task_store"]

    for attempt in range(1, settings.max_poll_attempts + 1):
        await asyncio.sleep(settings.poll_interval_seconds)

        try:
            task = await client.get_task_status(task_id)
        except Exception as exc:
            logger.warning(
                "Poll attempt %d failed: %s", attempt, exc,
                extra={"job_id": job_id, "user_id": user_id, "stage": "poll_error"},
            )
            if attempt >= settings.max_poll_attempts:
                await _safe_edit(
                    progress_message,
                    f"⌛ Timeout. Task ID: <code>{task_id}</code>\n/status bilan keyinroq tekshiring.",
                    parse_mode="HTML",
                    reply_markup=main_menu(),
                )
                return
            continue

        data = _extract_task_payload(task)
        logger.info(
            "Poll %d: status=%s", attempt, task.status,
            extra={"job_id": job_id, "user_id": user_id, "stage": "poll"},
        )

        store.upsert_task(
            task_id=task_id,
            user_id=user_id,
            chat_id=chat_id,
            topic=topic,
            status=task.status,
            output_url=data.get("path"),
            edit_url=data.get("edit_path"),
            file_format=_infer_format(data.get("path")),
            updated_at=data.get("updated_at"),
            raw_json=json.dumps(task.raw, ensure_ascii=False),
        )

        normalized = _normalize_status(task.status)

        if normalized in ACTIVE_STATUSES:
            elapsed = attempt * settings.poll_interval_seconds
            if attempt in {1, 4, 10, 20, 40}:
                await _safe_edit(
                    progress_message,
                    f"⏳ Deck tayyorlanmoqda... ({elapsed}s)\n"
                    f"🆔 Task: <code>{task_id}</code>\n"
                    f"📊 Status: {task.status}",
                    parse_mode="HTML",
                )
            continue

        if normalized in SUCCESS_STATUSES:
            await deliver_completed_task(
                context=context,
                progress_message=progress_message,
                task=task,
                topic=topic,
                chat_id=chat_id,
                user_id=user_id,
                job_id=job_id,
            )
            return

        if normalized in FAIL_STATUSES or normalized not in ACTIVE_STATUSES:
            await _safe_edit(
                progress_message,
                f"❌ Task xato bilan tugadi.\n\n{_format_error(task)}",
                reply_markup=main_menu(),
            )
            return

    await _safe_edit(
        progress_message,
        f"⌛ Timeout ({settings.max_poll_attempts * settings.poll_interval_seconds}s).\n"
        f"Task ID: <code>{task_id}</code>\n"
        "/status orqali keyinroq tekshiring.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def deliver_completed_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    progress_message,
    task: PresentonTask,
    topic: str,
    chat_id: int,
    user_id: int,
    job_id: str,
) -> None:
    settings = get_settings(context.application)
    client: PresentonClient = app_state(context.application)["presenton_client"]
    data = _extract_task_payload(task)

    output_url = str(data.get("path") or data.get("output_url") or data.get("url") or "").strip()
    edit_url = str(data.get("edit_path") or "").strip()

    if not output_url:
        await _safe_edit(
            progress_message,
            "❌ Task tugadi, lekin fayl URL topilmadi.\n"
            f"Raw: <code>{str(task.raw)[:300]}</code>",
            parse_mode="HTML",
        )
        return

    # Build full URL if relative
    if output_url.startswith("/"):
        output_url = settings.presenton_api_root + output_url
    if edit_url.startswith("/"):
        edit_url = settings.presenton_api_root + edit_url

    suffix = ".pdf" if output_url.lower().endswith(".pdf") else ".pptx"
    safe_name = _slugify(topic)[:60] or "presentation"
    destination = Path(settings.tmp_dir) / f"{safe_name}_{task.task_id}{suffix}"

    await _safe_edit(progress_message, "📥 Tayyor fayl yuklab olinmoqda...")

    try:
        local_path = await client.download_file(output_url, destination)
    except Exception as exc:
        logger.exception(
            "Download failed: %s", output_url,
            extra={"job_id": job_id, "user_id": user_id, "stage": "download"},
        )
        caption = (
            f"✅ <b>Deck tayyor!</b>\n\n"
            f"🆔 Task: <code>{task.task_id}</code>\n"
            f"📌 Mavzu: {_truncate(topic, 60)}\n"
            f"🔗 <a href='{output_url}'>Yuklab olish</a>"
        )
        if edit_url:
            caption += f"\n✏️ <a href='{edit_url}'>Presenton'da tahrirlash</a>"
        await _safe_edit(progress_message, caption, parse_mode="HTML", reply_markup=main_menu())
        return

    caption = (
        f"✅ <b>Deck tayyor!</b>\n\n"
        f"🆔 Task: <code>{task.task_id}</code>\n"
        f"📌 Mavzu: {_truncate(topic, 80)}\n"
        f"📄 Format: {suffix.lstrip('.').upper()}"
    )
    if edit_url:
        caption += f"\n✏️ <a href='{edit_url}'>Presenton'da tahrirlash</a>"

    with local_path.open("rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=local_path.name,
            caption=caption,
            parse_mode="HTML",
        )

    await _safe_edit(progress_message, "✅ Deck yuborildi!", reply_markup=main_menu())
    logger.info("Delivered", extra={"job_id": job_id, "user_id": user_id, "stage": "deliver"})

    try:
        local_path.unlink(missing_ok=True)
    except Exception:
        pass


# ── Error handler ──────────────────────────────────────────────────────────────

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, telegram.error.Conflict):
        logger.error(
            "Telegram polling conflict: faqat bitta bot instansiyasi ishlashi kerak. "
            "Koyeb replicas=1 ga o'rnating.",
            extra={"stage": "polling_conflict", "job_id": None, "user_id": None},
        )
        try:
            context.application.stop_running()
        except Exception:
            pass
        return
    logger.exception("Unhandled error", exc_info=err, extra={"job_id": None, "user_id": None, "stage": "error"})


# ── Utilities ──────────────────────────────────────────────────────────────────

async def _safe_edit(message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except telegram.error.BadRequest:
        try:
            await message.reply_text(text, **kwargs)
        except Exception:
            pass
    except Exception:
        pass


def build_presenton_payload(
    topic: str,
    prefs: UserPreferences,
    settings: Settings,
    *,
    files_ids: list[str],
) -> dict[str, Any]:
    instructions = (
        "Create a presentation that feels spacious, wide, and comfortable to read. "
        "Use richer explanatory text than a minimal deck, but keep slides presentation-friendly. "
        "Prefer broader slide compositions, clearer sectioning, and fuller bullet explanations. "
        "Avoid overly sparse slides. Make the deck look polished, structured, and executive-ready."
    )
    if files_ids:
        instructions += " Use uploaded files as primary source material and preserve important details."

    payload: dict[str, Any] = {
        "content": topic,
        "n_slides": prefs.n_slides,
        "instructions": instructions,
        "tone": prefs.tone,
        "verbosity": prefs.verbosity,
        "content_generation": prefs.content_generation,
        "markdown_emphasis": prefs.markdown_emphasis,
        "web_search": prefs.web_search,
        "image_type": prefs.image_type,
        "theme": prefs.theme,
        "language": prefs.language,
        "standard_template": prefs.standard_template,
        "include_table_of_contents": prefs.include_table_of_contents,
        "include_title_slide": prefs.include_title_slide,
        "files": files_ids if files_ids else None,
        "export_as": prefs.export_as,
        "trigger_webhook": False,
    }
    return {k: v for k, v in payload.items() if v is not None}


def _format_stored_task(task) -> str:
    lines = [
        f"📋 <b>Oxirgi task</b>",
        f"🆔 ID: <code>{task.task_id}</code>",
        f"📊 Status: {task.status}",
        f"📌 Mavzu: {_truncate(task.topic, 80)}",
    ]
    if task.output_url:
        lines.append(f"🔗 <a href='{task.output_url}'>Yuklab olish</a>")
    if task.edit_url:
        lines.append(f"✏️ <a href='{task.edit_url}'>Tahrirlash</a>")
    return "\n".join(lines)


def _format_status_message(topic: str, task: PresentonTask) -> str:
    data = _extract_task_payload(task)
    lines = [
        f"📊 <b>Task holati</b>",
        f"🆔 ID: <code>{task.task_id}</code>",
        f"📊 Status: {task.status}",
        f"📌 Mavzu: {_truncate(topic, 80)}",
    ]
    if data.get("path"):
        lines.append(f"🔗 Output: {data['path']}")
    if data.get("edit_path"):
        lines.append(f"✏️ Editor: {data['edit_path']}")
    if task.error:
        lines.append(f"❌ Xato: <code>{json.dumps(task.error, ensure_ascii=False)[:400]}</code>")
    return "\n".join(lines)


def _format_error(task: PresentonTask) -> str:
    if task.error:
        try:
            return f"<code>{json.dumps(task.error, ensure_ascii=False, indent=2)[:600]}</code>"
        except Exception:
            return f"<code>{str(task.error)[:600]}</code>"
    return (task.message or "Unknown error")[:600]


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _infer_format(path: str | None) -> str | None:
    if not path:
        return None
    p = path.lower()
    if p.endswith(".pdf"):
        return "pdf"
    if p.endswith(".pptx"):
        return "pptx"
    if p.endswith(".png"):
        return "png"
    return None


def _normalize_status(status: str | None) -> str:
    return (status or "unknown").strip().lower().replace(" ", "_").replace("-", "_")


def _extract_task_payload(task: PresentonTask) -> dict[str, Any]:
    data = dict(task.data or {})
    raw = task.raw if isinstance(task.raw, dict) else {}
    if not data and isinstance(raw, dict):
        for key in ("data", "result", "presentation", "task", "output"):
            value = raw.get(key)
            if isinstance(value, dict):
                data.update(value)
                break
    for key in ("path", "edit_path", "presentation_id", "output_url", "url", "updated_at", "created_at"):
        if key not in data and isinstance(raw, dict) and key in raw:
            data[key] = raw[key]
    return data


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _exc_summary(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:200]}"


# ── Application builder ────────────────────────────────────────────────────────

def build_application(settings: Settings) -> Application:
    state = {
        "settings": settings,
        "presenton_client": PresentonClient(settings),
        "task_store": TaskStore(settings.task_store_path),
        "generation_semaphore": asyncio.Semaphore(settings.max_concurrent_jobs),
        "default_prefs": UserPreferences.from_settings(settings),
    }

    builder = Application.builder().token(settings.bot_token)
    if settings.telegram_base_url:
        builder = builder.base_url(settings.telegram_base_url)
    builder = (
        builder
        .read_timeout(settings.telegram_read_timeout)
        .write_timeout(settings.telegram_write_timeout)
        .connect_timeout(settings.telegram_connect_timeout)
        .pool_timeout(settings.telegram_pool_timeout)
    )
    app = builder.build()
    app.bot_data["state"] = state

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("file", file_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("last", last_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, topic_handler))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    settings = Settings()
    settings.validate()
    setup_logging(settings.log_dir, settings.log_level)
    app = build_application(settings)
    logger.info(
        "Bot starting. Presenton: %s",
        settings.presenton_api_root,
        extra={"stage": "startup", "user_id": None, "job_id": None},
    )
    app.run_polling(
        close_loop=False,
        drop_pending_updates=settings.drop_pending_updates_on_startup,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
