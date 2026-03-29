from __future__ import annotations

import httpx
from app.config import settings


class WebClient:
    def __init__(self) -> None:
        self.base = settings.web_base
        self.headers = {'x-internal-token': settings.internal_api_token}

    async def next_job(self) -> dict | None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(f"{self.base}/internal/jobs/next", params={'worker_id': settings.worker_id}, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get('job')

    async def update_status(self, job_id: int, **payload) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base}/internal/jobs/{job_id}/status", json=payload, headers=self.headers)
            resp.raise_for_status()

    async def complete(self, job_id: int, **payload) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base}/internal/jobs/{job_id}/complete", json=payload, headers=self.headers)
            resp.raise_for_status()

    async def fail(self, job_id: int, error: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base}/internal/jobs/{job_id}/fail", json={'worker_id': settings.worker_id, 'error': error}, headers=self.headers)
            resp.raise_for_status()
