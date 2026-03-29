from __future__ import annotations

import asyncio
import contextlib

from app.config import settings
from app.services.presenton_client import PresentonClient
from app.services.telegram_api import edit_message, send_document_by_url
from app.services.web_client import WebClient


def build_progress_text(topic: str, phase: str) -> str:
    return (
        "<b>Presentation yaratilmoqda</b>\n"
        f"• Mavzu: {topic}\n\n"
        f"{phase}"
    )


async def process_job(job: dict, web: WebClient, presenton: PresentonClient) -> None:
    job_id = int(job['id'])
    payload = job.get('payload') or {}
    chat_id = int(job['chat_id'])
    progress_message_id = int(job['progress_message_id']) if job.get('progress_message_id') else None
    topic = payload.get('topic') or job['topic']
    export_as = payload.get('export_as') or job.get('export_as') or settings.presenton_export_default

    async def safe_edit(text: str):
        if progress_message_id:
            with contextlib.suppress(Exception):
                await edit_message(chat_id, progress_message_id, text)

    try:
        await web.update_status(job_id, status='processing', worker_id=settings.worker_id, note='Worker picked up the job')
        await safe_edit(build_progress_text(topic, '2/4 Worker briefni deckka aylantiryapti...'))

        created = await presenton.generate_async(
            topic=topic,
            goal=payload.get('goal', 'general'),
            audience=payload.get('audience', 'general'),
            length=payload.get('length', 'standard'),
            language=payload.get('language', 'en'),
            tone=payload.get('tone', 'professional'),
            density=payload.get('density', 'balanced'),
            image_mode=payload.get('image_mode', 'balanced'),
            export_as=export_as,
            theme=payload.get('theme'),
            instructions=payload.get('instructions'),
        )
        task_id = created['id']
        await web.update_status(job_id, status='processing', worker_id=settings.worker_id, provider_task_id=task_id, note='Presenton task started')

        last_status = None
        for _ in range(120):
            data = await presenton.get_status(task_id)
            status = data.get('status', 'pending')
            if status != last_status:
                last_status = status
                phase = {
                    'pending': '2/4 Outline va tarkib tayyorlanmoqda...',
                    'processing': '3/4 Slaydlar yig‘ilyapti...',
                    'completed': '4/4 Export tayyorlanmoqda...',
                    'failed': '❌ Presenton xatolik qaytardi.',
                }.get(status, 'Jarayon davom etmoqda...')
                await safe_edit(build_progress_text(topic, phase))
                await web.update_status(job_id, status='processing', worker_id=settings.worker_id, provider_task_id=task_id, note=phase)

            if status == 'completed':
                status_payload = data.get('data', {}) or {}
                presentation_id = status_payload.get('presentation_id') or status_payload.get('id')
                export_data = await presenton.export(presentation_id, export_as)
                file_url = export_data.get('download_url') or export_data.get('path') or export_data.get('url')
                edit_url = export_data.get('edit_path')
                await safe_edit(build_progress_text(topic, '✅ Tayyor. Fayl quyida yuborildi.'))
                if file_url:
                    caption = f"<b>Tayyor presentation</b>\n• {topic}"
                    if edit_url:
                        caption += f"\n• Edit: {edit_url}"
                    await send_document_by_url(chat_id, file_url, caption)
                await web.complete(job_id, worker_id=settings.worker_id, provider_task_id=task_id, presentation_id=presentation_id, file_url=file_url, edit_url=edit_url, note='Completed')
                return

            if status == 'failed':
                await safe_edit(build_progress_text(topic, '❌ Presenton deck yaratishda xatolik berdi.'))
                await web.fail(job_id, 'Presenton returned failed status')
                return

            await asyncio.sleep(4)

        await safe_edit(build_progress_text(topic, "⌛ Jarayon cho'zildi."))
        await web.fail(job_id, 'Timed out while waiting for Presenton task')
    except Exception as exc:
        await safe_edit(build_progress_text(topic, f'❌ Worker xatoligi: {exc}'))
        with contextlib.suppress(Exception):
            await web.fail(job_id, str(exc))


async def run_once() -> bool:
    web = WebClient()
    presenton = PresentonClient()
    job = await web.next_job()
    if not job:
        return False
    await process_job(job, web, presenton)
    return True


async def run_forever() -> None:
    while True:
        found = await run_once()
        if settings.worker_run_once:
            return
        await asyncio.sleep(0 if found else settings.poll_interval_seconds)


if __name__ == '__main__':
    asyncio.run(run_forever())
