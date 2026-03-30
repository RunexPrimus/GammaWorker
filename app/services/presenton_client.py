from __future__ import annotations

import httpx

from app.config import settings


class PresentonClient:
    def __init__(self) -> None:
        self.base_url = settings.presenton_base_url.strip().rstrip("/")

    def headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if settings.presenton_api_key:
            headers["Authorization"] = f"Bearer {settings.presenton_api_key}"
        return headers

    def _map_tone(self, tone: str | None) -> str:
        mapping = {
            "professional": "professional",
            "premium": "professional",
            "formal": "professional",
            "friendly": "casual",
            "casual": "casual",
            "educational": "educational",
            "sales": "sales_pitch",
            "confident": "sales_pitch",
            "funny": "funny",
            "default": "default",
        }
        return mapping.get((tone or "").strip().lower(), "professional")

    def _map_verbosity(self, density: str | None) -> str:
        mapping = {"minimal": "concise", "balanced": "standard", "detailed": "text-heavy", "data-heavy": "text-heavy"}
        return mapping.get((density or "").strip().lower(), "standard")

    def _map_language(self, language: str | None) -> str:
        mapping = {"en": "English", "uz": "Uzbek", "ru": "Russian", "tr": "Turkish"}
        return mapping.get((language or "").strip().lower(), "English")

    def _n_slides(self, length: str | None) -> int:
        mapping = {"short": 6, "standard": 8, "detailed": 12, "custom": 10}
        return mapping.get((length or "").strip().lower(), 8)

    def _body(self, payload: dict) -> dict:
        return {
            "content": payload["topic"],
            "n_slides": self._n_slides(payload.get("length")),
            "instructions": payload.get("instructions") or f"Create a {payload.get('goal', 'general')} presentation for {payload.get('audience', 'general')}.",
            "tone": self._map_tone(payload.get("tone")),
            "verbosity": self._map_verbosity(payload.get("density")),
            "content_generation": settings.presenton_content_generation,
            "markdown_emphasis": settings.presenton_markdown_emphasis,
            "web_search": settings.presenton_web_search,
            "image_type": settings.presenton_image_type,
            "theme": payload.get("theme") or settings.presenton_theme,
            "language": self._map_language(payload.get("language")),
            "template": settings.presenton_template,
            "include_table_of_contents": settings.presenton_include_toc,
            "include_title_slide": settings.presenton_include_title_slide,
            "allow_access_to_user_info": True,
            "export_as": payload.get("export_as") or settings.presenton_export_default,
            "trigger_webhook": False,
        }

    async def _post(self, url: str, body: dict) -> tuple[int, dict]:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=self.headers(), json=body)
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        return response.status_code, data

    async def generate(self, payload: dict) -> dict:
        if not self.base_url:
            raise RuntimeError("Presenton base URL is empty")
        body = self._body(payload)
        sync_url = f"{self.base_url}/api/v1/ppt/presentation/generate"
        sync_status, sync_data = await self._post(sync_url, body)
        if sync_status < 400:
            return {"mode": "sync", "data": sync_data}
        async_url = f"{self.base_url}/api/v1/ppt/presentation/generate/async"
        async_status, async_data = await self._post(async_url, body)
        if async_status < 400:
            return {"mode": "async", "data": async_data}
        raise RuntimeError(f"Presenton API error: sync_url={sync_url}, sync_status={sync_status}, sync_body={sync_data}, async_url={async_url}, async_status={async_status}, async_body={async_data}, payload={body}")

    async def get_status(self, task_id: str) -> dict:
        url = f"{self.base_url}/api/v1/ppt/presentation/status/{task_id}"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, headers=self.headers())
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        if response.status_code >= 400:
            raise RuntimeError(f"Presenton status error: url={url}, status={response.status_code}, body={data}")
        return data

    async def export(self, presentation_id: str, export_as: str) -> dict:
        url = f"{self.base_url}/api/v1/ppt/presentation/export"
        body = {"id": presentation_id, "export_as": export_as}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=self.headers(), json=body)
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        if response.status_code >= 400:
            raise RuntimeError(f"Presenton export error: url={url}, status={response.status_code}, body={data}")
        return data
