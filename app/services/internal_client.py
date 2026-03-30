from __future__ import annotations

import httpx

from app.config import settings


def _headers() -> dict:
    return {"x-internal-token": settings.internal_api_token}


async def fetch_next_job() -> dict | None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{settings.web_internal_base_url.rstrip('/')}/internal/jobs/next",
            headers=_headers(),
            params={"worker_id": settings.worker_id},
        )
    response.raise_for_status()
    data = response.json()
    return data.get("job")


async def update_job_status(job_id: int, *, status: str, worker_id: str, provider_task_id: str | None = None, presentation_id: str | None = None, note: str | None = None) -> None:
    payload = {
        "status": status,
        "worker_id": worker_id,
        "provider_task_id": provider_task_id,
        "presentation_id": presentation_id,
        "note": note,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{settings.web_internal_base_url.rstrip('/')}/internal/jobs/{job_id}/status", headers=_headers(), json=payload)
    response.raise_for_status()


async def complete_job(job_id: int, *, worker_id: str, provider_task_id: str | None, presentation_id: str | None, file_url: str | None, edit_url: str | None, note: str | None = None) -> None:
    payload = {
        "worker_id": worker_id,
        "provider_task_id": provider_task_id,
        "presentation_id": presentation_id,
        "file_url": file_url,
        "edit_url": edit_url,
        "note": note,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{settings.web_internal_base_url.rstrip('/')}/internal/jobs/{job_id}/complete", headers=_headers(), json=payload)
    response.raise_for_status()


async def fail_job(job_id: int, *, worker_id: str, error: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.web_internal_base_url.rstrip('/')}/internal/jobs/{job_id}/fail",
            headers=_headers(),
            json={"worker_id": worker_id, "error": error},
        )
    response.raise_for_status()
