from __future__ import annotations

import asyncio

from app.config import settings
from app.services.internal_client import complete_job, fail_job, fetch_next_job, update_job_status
from app.services.presenton_client import PresentonClient
from app.services.telegram_api import edit_message, send_document_by_url


def _progress(topic: str, phase: str) -> str:
    return f"<b>Presentation yaratilmoqda</b>\n• Mavzu: {topic}\n\n{phase}"


async def _safe_edit(chat_id: int, message_id: int, text: str) -> None:
    try:
        await edit_message(chat_id, message_id, text)
    except Exception:
        pass


async def process_one_job() -> bool:
    job = await fetch_next_job()
    if not job:
        return False

    job_id = int(job["id"])
    chat_id = int(job["chat_id"])
    progress_message_id = int(job.get("progress_message_id") or 0)
    payload = job["payload"]
    topic = payload["topic"]
    client = PresentonClient()

    try:
        await update_job_status(job_id, status="processing", worker_id=settings.worker_id, note="Generating")
        if progress_message_id:
            await _safe_edit(chat_id, progress_message_id, _progress(topic, "2/4 Worker presentation tayyorlayapti..."))
        created = await client.generate(payload)
        if created["mode"] == "sync":
            data = created["data"]
            file_url = data.get("download_url") or data.get("url") or data.get("file_url")
            presentation_id = data.get("presentation_id") or data.get("id")
            if not file_url and presentation_id:
                exported = await client.export(presentation_id, payload.get("export_as", settings.presenton_export_default))
                file_url = exported.get("download_url") or exported.get("url")
            await complete_job(job_id, worker_id=settings.worker_id, provider_task_id=None, presentation_id=presentation_id, file_url=file_url, edit_url=None, note="Completed sync")
            if progress_message_id:
                await _safe_edit(chat_id, progress_message_id, _progress(topic, "4/4 Tayyor! Fayl yuborildi."))
            if file_url:
                await send_document_by_url(chat_id, file_url, f"Tayyor presentation: {topic}")
            return True

        task_id = created["data"].get("id") or created["data"].get("task_id")
        await update_job_status(job_id, status="processing", worker_id=settings.worker_id, provider_task_id=task_id, note="Queued in Presenton")

        for _ in range(90):
            status_data = await client.get_status(task_id)
            status = status_data.get("status", "pending")
            if status in {"pending", "queued"}:
                if progress_message_id:
                    await _safe_edit(chat_id, progress_message_id, _progress(topic, "2/4 Navbatda..."))
            elif status in {"processing", "running"}:
                if progress_message_id:
                    await _safe_edit(chat_id, progress_message_id, _progress(topic, "3/4 Slaydlar yaratilmoqda..."))
            elif status == "completed":
                data = status_data.get("data", {})
                presentation_id = data.get("presentation_id") or data.get("id")
                exported = await client.export(presentation_id, payload.get("export_as", settings.presenton_export_default))
                file_url = exported.get("download_url") or exported.get("url")
                await complete_job(job_id, worker_id=settings.worker_id, provider_task_id=task_id, presentation_id=presentation_id, file_url=file_url, edit_url=None, note="Completed async")
                if progress_message_id:
                    await _safe_edit(chat_id, progress_message_id, _progress(topic, "4/4 Tayyor! Fayl yuborildi."))
                if file_url:
                    await send_document_by_url(chat_id, file_url, f"Tayyor presentation: {topic}")
                return True
            elif status == "failed":
                raise RuntimeError(f"Presenton task failed: {status_data}")
            await asyncio.sleep(4)

        raise RuntimeError("Presenton task timeout")
    except Exception as exc:  # noqa: BLE001
        await fail_job(job_id, worker_id=settings.worker_id, error=str(exc))
        if progress_message_id:
            await _safe_edit(chat_id, progress_message_id, _progress(topic, f"❌ Worker xatoligi: {exc}"))
        return True


async def worker_forever() -> None:
    while True:
        processed = await process_one_job()
        if settings.worker_run_once:
            return
        if not processed:
            await asyncio.sleep(settings.poll_interval_seconds)
