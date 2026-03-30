from __future__ import annotations

import httpx
from app.config import settings


class InternalWebClient:
    def __init__(self) -> None:
        self.base = settings.web_base
        self.token = settings.internal_api_token

    async def fetch_next_job(self) -> dict | None:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f'{self.base}/internal/jobs/next',
                params={'worker_id': settings.worker_id, 'token': self.token},
            )
            try:
                data = response.json()
            except Exception:
                data = {'raw_text': response.text}
            if response.status_code >= 400:
                raise RuntimeError(f'Web internal next-job error: status={response.status_code}, body={data}')
            return data.get('job')

    async def update_status(self, job_id: int, status: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f'{self.base}/internal/jobs/{job_id}/status',
                params={'status': status, 'token': self.token},
            )
            response.raise_for_status()

    async def mark_done(self, job_id: int, file_url: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f'{self.base}/internal/jobs/{job_id}/done',
                params={'file_url': file_url, 'token': self.token},
            )
            response.raise_for_status()

    async def mark_failed(self, job_id: int, error: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f'{self.base}/internal/jobs/{job_id}/fail',
                params={'error': error, 'token': self.token},
            )
            response.raise_for_status()
