from __future__ import annotations

import httpx

from app.config import settings


class PresentonClient:
    def __init__(self) -> None:
        self.base_url = settings.presenton_base_url.rstrip("/")
        self.api_key = settings.presenton_api_key.strip()

    def headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def absolute_url(self, path_or_url: str | None) -> str | None:
        if not path_or_url:
            return None
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = f"/{path_or_url}"
        return f"{self.base_url}{path_or_url}"

    def _map_tone(self, tone: str | None) -> str:
        mapping = {
            "professional": "professional",
            "premium": "professional",
            "formal": "professional",
            "confident": "sales_pitch",
            "sales": "sales_pitch",
            "friendly": "casual",
            "casual": "casual",
            "funny": "funny",
            "educational": "educational",
            "default": "default",
        }
        return mapping.get((tone or "").strip().lower(), "professional")

    def _map_verbosity(self, density: str | None) -> str:
        mapping = {
            "minimal": "concise",
            "balanced": "standard",
            "detailed": "text-heavy",
            "data-heavy": "text-heavy",
        }
        return mapping.get((density or "").strip().lower(), "standard")

    def _map_image_type(self, image_mode: str | None) -> str:
        mapping = {
            "none": "stock",
            "minimal": "stock",
            "balanced": "stock",
            "visual-heavy": "ai-generated",
        }
        return mapping.get((image_mode or "").strip().lower(), settings.presenton_image_type)

    def _map_language(self, language: str | None) -> str:
        mapping = {
            "en": "English",
            "uz": "Uzbek",
            "ru": "Russian",
            "tr": "Turkish",
            "english": "English",
            "uzbek": "Uzbek",
            "russian": "Russian",
            "turkish": "Turkish",
        }
        return mapping.get((language or "").strip().lower(), "English")

    def _map_template(self, template: str | None) -> str:
        allowed = {"general", "modern", "standard", "swift", "neo-general", "neo-modern", "neo-standard", "neo-swift"}
        value = (template or settings.presenton_template or "modern").strip()
        return value if value in allowed else "modern"

    def _map_theme(self, theme: str | None) -> str:
        allowed = {"edge-yellow", "mint-blue", "light-rose", "professional-blue", "professional-dark"}
        value = (theme or settings.presenton_theme or "professional-blue").strip()
        return value if value in allowed else "professional-blue"

    async def generate_async(
        self,
        *,
        topic: str,
        goal: str,
        audience: str,
        length: str,
        language: str,
        tone: str,
        density: str,
        image_mode: str,
        export_as: str,
        theme: str | None = None,
        instructions: str | None = None,
    ) -> dict:
        slide_count = {"short": 6, "standard": 8, "detailed": 12}.get(length, 8)
        payload = {
            "content": topic,
            "n_slides": slide_count,
            "instructions": instructions or f"Create a {goal} presentation for {audience}.",
            "tone": self._map_tone(tone),
            "verbosity": self._map_verbosity(density),
            "content_generation": settings.presenton_content_generation,
            "markdown_emphasis": settings.presenton_markdown_emphasis,
            "web_search": settings.presenton_web_search,
            "image_type": self._map_image_type(image_mode),
            "theme": self._map_theme(theme),
            "language": self._map_language(language),
            "template": self._map_template(settings.presenton_template),
            "include_table_of_contents": settings.presenton_include_toc,
            "include_title_slide": settings.presenton_include_title_slide,
            "allow_access_to_user_info": True,
            "export_as": export_as if export_as in {"pptx", "pdf", "png"} else settings.presenton_export_default,
            "trigger_webhook": False,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/ppt/presentation/generate/async",
                headers=self.headers(),
                json=payload,
            )
            try:
                data = response.json()
            except Exception:
                data = {"raw_text": response.text}
            if response.status_code >= 400:
                raise RuntimeError(f"Presenton API error: status={response.status_code}, payload={payload}, body={data}")
            return data

    async def get_status(self, task_id: str) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/ppt/presentation/status/{task_id}",
                headers=self.headers(),
            )
            response.raise_for_status()
            return response.json()

    async def export(self, presentation_id: str, export_as: str) -> dict:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/ppt/presentation/export",
                headers=self.headers(),
                json={"id": presentation_id, "export_as": export_as},
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if "path" in data:
                    data["path"] = self.absolute_url(data.get("path"))
                if "download_url" in data:
                    data["download_url"] = self.absolute_url(data.get("download_url"))
                if "edit_path" in data:
                    data["edit_path"] = self.absolute_url(data.get("edit_path"))
            return data
