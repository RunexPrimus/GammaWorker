from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
TMP_DIR = BASE_DIR / "tmp"

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

for _p in (DATA_DIR, LOG_DIR, TMP_DIR):
    _p.mkdir(parents=True, exist_ok=True)


def _get_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    # ── Required ─────────────────────────────────────────────────────────────
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", "").strip())

    # ── Presenton ─────────────────────────────────────────────────────────────
    # IMPORTANT: For Presenton Cloud use https://api.presenton.ai
    # For self-hosted Docker use your server URL e.g. http://your-server:5000
    presenton_base_url: str = field(
        default_factory=lambda: os.getenv("PRESENTON_BASE_URL", "https://api.presenton.ai").strip()
    )
    presenton_api_key: str = field(default_factory=lambda: os.getenv("PRESENTON_API_KEY", "").strip())

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_base_url: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BASE_URL") or None)

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    # ── Timeouts & polling ───────────────────────────────────────────────────
    request_timeout_seconds: int = field(default_factory=lambda: _get_int("REQUEST_TIMEOUT_SECONDS", 180, minimum=10))
    connect_timeout_seconds: int = field(default_factory=lambda: _get_int("CONNECT_TIMEOUT_SECONDS", 20, minimum=3))
    poll_interval_seconds: int = field(default_factory=lambda: _get_int("POLL_INTERVAL_SECONDS", 8, minimum=2))
    max_poll_attempts: int = field(default_factory=lambda: _get_int("MAX_POLL_ATTEMPTS", 90, minimum=10))

    # ── Concurrency & uploads ─────────────────────────────────────────────────
    max_concurrent_jobs: int = field(default_factory=lambda: _get_int("MAX_CONCURRENT_JOBS", 3, minimum=1, maximum=10))
    max_upload_size_mb: int = field(default_factory=lambda: _get_int("MAX_UPLOAD_SIZE_MB", 20, minimum=1, maximum=100))

    # ── Telegram timeouts ─────────────────────────────────────────────────────
    telegram_read_timeout: int = field(default_factory=lambda: _get_int("TELEGRAM_READ_TIMEOUT", 30, minimum=5))
    telegram_write_timeout: int = field(default_factory=lambda: _get_int("TELEGRAM_WRITE_TIMEOUT", 30, minimum=5))
    telegram_connect_timeout: int = field(default_factory=lambda: _get_int("TELEGRAM_CONNECT_TIMEOUT", 20, minimum=3))
    telegram_pool_timeout: int = field(default_factory=lambda: _get_int("TELEGRAM_POOL_TIMEOUT", 20, minimum=3))
    drop_pending_updates_on_startup: bool = field(
        default_factory=lambda: _get_bool("DROP_PENDING_UPDATES_ON_STARTUP", True)
    )

    # ── Default presentation settings ────────────────────────────────────────
    default_slides: int = field(default_factory=lambda: _get_int("DEFAULT_SLIDES", 12, minimum=5, maximum=30))
    default_tone: str = field(default_factory=lambda: os.getenv("DEFAULT_TONE", "professional").strip() or "professional")
    default_verbosity: str = field(
        default_factory=lambda: os.getenv("DEFAULT_VERBOSITY", "text-heavy").strip() or "text-heavy"
    )
    default_language: str = field(
        default_factory=lambda: os.getenv("DEFAULT_LANGUAGE", "English").strip() or "English"
    )
    default_theme: str = field(
        default_factory=lambda: os.getenv("DEFAULT_THEME", "professional-blue").strip() or "professional-blue"
    )
    default_template: str = field(
        default_factory=lambda: os.getenv("DEFAULT_TEMPLATE", "neo-standard").strip() or "neo-standard"
    )
    default_export_as: str = field(
        default_factory=lambda: os.getenv("DEFAULT_EXPORT_AS", "pptx").strip() or "pptx"
    )
    default_image_type: str = field(
        default_factory=lambda: os.getenv("DEFAULT_IMAGE_TYPE", "stock").strip() or "stock"
    )
    default_content_generation: str = field(
        default_factory=lambda: os.getenv("DEFAULT_CONTENT_GENERATION", "enhance").strip() or "enhance"
    )
    default_include_toc: bool = field(default_factory=lambda: _get_bool("DEFAULT_INCLUDE_TOC", True))
    default_include_title: bool = field(default_factory=lambda: _get_bool("DEFAULT_INCLUDE_TITLE", True))
    default_web_search: bool = field(default_factory=lambda: _get_bool("DEFAULT_WEB_SEARCH", False))
    default_markdown_emphasis: bool = field(default_factory=lambda: _get_bool("DEFAULT_MARKDOWN_EMPHASIS", True))

    # ── Paths ──────────────────────────────────────────────────────────────────
    task_store_path: str = field(default_factory=lambda: str(DATA_DIR / "bot.sqlite3"))
    tmp_dir: str = field(default_factory=lambda: str(TMP_DIR))
    log_dir: str = field(default_factory=lambda: str(LOG_DIR))

    # ── Retry ─────────────────────────────────────────────────────────────────
    api_max_retries: int = field(default_factory=lambda: _get_int("API_MAX_RETRIES", 3, minimum=0, maximum=10))
    api_retry_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("API_RETRY_DELAY_SECONDS", "2.0"))
    )

    def validate(self) -> None:
        missing: list[str] = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.presenton_base_url:
            missing.append("PRESENTON_BASE_URL")
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))

        Path(self.tmp_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)
        Path(self.task_store_path).parent.mkdir(parents=True, exist_ok=True)

    @property
    def presenton_api_root(self) -> str:
        return self.presenton_base_url.rstrip("/")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024
