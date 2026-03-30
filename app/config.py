from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Runex Presenton")
    app_role: str = os.getenv("APP_ROLE", "web").strip().lower() or "web"
    app_base_url: str = os.getenv("APP_BASE_URL", "").strip()
    port: int = int(os.getenv("PORT", "8000"))

    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    bot_username: str = os.getenv("BOT_USERNAME", "").strip()
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "123456").strip()

    app_db_path: str = os.getenv("APP_DB_PATH", "/tmp/presenton_web.db").strip()
    internal_api_token: str = os.getenv("INTERNAL_API_TOKEN", "change-me").strip()
    job_claim_ttl_seconds: int = int(os.getenv("JOB_CLAIM_TTL_SECONDS", "900"))

    worker_id: str = os.getenv("WORKER_ID", "worker-1").strip()
    worker_run_once: bool = _as_bool(os.getenv("WORKER_RUN_ONCE"), False)
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
    web_internal_base_url: str = os.getenv("WEB_INTERNAL_BASE_URL", "").strip()

    presenton_base_url: str = os.getenv("PRESENTON_BASE_URL", "").strip()
    presenton_api_key: str = os.getenv("PRESENTON_API_KEY", "").strip()
    presenton_template: str = os.getenv("PRESENTON_TEMPLATE", "modern").strip() or "modern"
    presenton_theme: str = os.getenv("PRESENTON_THEME", "professional-blue").strip() or "professional-blue"
    presenton_export_default: str = os.getenv("PRESENTON_EXPORT_DEFAULT", "pptx").strip() or "pptx"
    presenton_image_type: str = os.getenv("PRESENTON_IMAGE_TYPE", "stock").strip() or "stock"
    presenton_content_generation: str = os.getenv("PRESENTON_CONTENT_GENERATION", "enhance").strip() or "enhance"
    presenton_markdown_emphasis: bool = _as_bool(os.getenv("PRESENTON_MARKDOWN_EMPHASIS"), True)
    presenton_web_search: bool = _as_bool(os.getenv("PRESENTON_WEB_SEARCH"), False)
    presenton_include_title_slide: bool = _as_bool(os.getenv("PRESENTON_INCLUDE_TITLE_SLIDE"), True)
    presenton_include_toc: bool = _as_bool(os.getenv("PRESENTON_INCLUDE_TOC"), False)

    default_theme: str = os.getenv("DEFAULT_THEME", "professional-blue").strip() or "professional-blue"
    default_export: str = os.getenv("DEFAULT_EXPORT", "pptx").strip() or "pptx"

    @property
    def telegram_api_base(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def normalized_app_base_url(self) -> str:
        base = self.app_base_url.strip().rstrip("/")
        if not base:
            return ""
        if not base.startswith(("https://", "http://")):
            base = f"https://{base}"
        return base


settings = Settings()
