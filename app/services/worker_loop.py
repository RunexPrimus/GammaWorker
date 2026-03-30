from __future__ import annotations

import asyncio
from app.config import settings
from app.services.internal_client import InternalWebClient
from app.services.presenton_client import PresentonClient
from app.services.telegram_api import edit_message, send_document_by_url


def progress_text(topic: str, phase: str) -> str:
    return f"<b>Presentation yaratilmoqda</b>\n• Mavzu: {topic}\n\n{phase}"


async def process_one_job() -> bool:
    web = InternalWebClient()
    presenton = PresentonClient()
    job = await web.fetch_next_job()
    if not job:
        return False

    job_id = int(job['id'])
    payload = job.get('payload') or {}
    chat_id = int(job['chat_id'])
    topic = payload.get('topic') or job.get('topic') or 'Untitled'
    progress_message_id = job.get('progress_message_id')
    export_as = payload.get('export_as') or settings.presenton_export_default

    async def safe_edit(text: str):
        if progress_message_id:
            await edit_message(chat_id, int(progress_message_id), text)

    try:
        await web.update_status(job_id, 'processing')
        await safe_edit(progress_text(topic, '2/4 Worker deck yaratishni boshladi...'))

        try:
            data = await presenton.generate_sync(
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

            file_url = data.get('download_url') or data.get('url') or data.get('path')
            if file_url:
                await safe_edit(progress_text(topic, '✅ Tayyor. Fayl quyida yuborildi.'))
                await send_document_by_url(chat_id, file_url, f'<b>Tayyor presentation</b>\n• {topic}')
                await web.mark_done(job_id, file_url)
                return True
        except Exception:
            pass

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

        for _ in range(120):
            data = await presenton.get_status(task_id)
            status = data.get('status', 'pending')
            if status == 'pending':
                await safe_edit(progress_text(topic, '2/4 Outline va tarkib tayyorlanmoqda...'))
            elif status == 'processing':
                await safe_edit(progress_text(topic, '3/4 Slaydlar yig‘ilyapti...'))
            elif status == 'completed':
                status_data = data.get('data', {}) or {}
                presentation_id = status_data.get('presentation_id') or status_data.get('id')
                export = await presenton.export(presentation_id, export_as)
                file_url = export.get('download_url') or export.get('url') or export.get('path')
                if file_url:
                    await safe_edit(progress_text(topic, '✅ Tayyor. Fayl quyida yuborildi.'))
                    await send_document_by_url(chat_id, file_url, f'<b>Tayyor presentation</b>\n• {topic}')
                    await web.mark_done(job_id, file_url)
                    return True
                raise RuntimeError('Export URL not found')
            elif status == 'failed':
                raise RuntimeError('Presenton returned failed status')
            await asyncio.sleep(4)

        raise RuntimeError('Timed out while waiting for Presenton task')
    except Exception as exc:
        await safe_edit(progress_text(topic, f'❌ Worker xatoligi: {exc}'))
        await web.mark_failed(job_id, str(exc))
        return True


async def worker_forever() -> None:
    while True:
        try:
            found = await process_one_job()
        except Exception:
            found = False
        if settings.worker_run_once:
            return
        await asyncio.sleep(0 if found else settings.poll_interval_seconds)
