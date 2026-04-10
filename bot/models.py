from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ── Presenton v3 valid values ────────────────────────────────────────────────
ALLOWED_TONES = {"default", "casual", "professional", "funny", "educational", "sales_pitch"}
ALLOWED_VERBOSITY = {"concise", "standard", "text-heavy"}
ALLOWED_FORMATS = {"pptx", "pdf"}
ALLOWED_IMAGE_TYPES = {"stock", "ai-generated"}
ALLOWED_TEMPLATES = {
    # Neo series
    "neo-standard", "neo-general", "neo-modern", "neo-swift",
    # Classic series
    "standard", "general", "modern", "swift",
}
ALLOWED_THEMES = {
    "professional-blue", "professional-dark",
    "edge-yellow", "light-rose", "mint-blue",
}

LANGUAGES = [
    "English", "Russian", "Uzbek", "Arabic", "Chinese",
    "French", "German", "Spanish", "Turkish", "Hindi",
]


@dataclass(slots=True)
class UserPreferences:
    n_slides: int = 12
    tone: str = "professional"
    verbosity: str = "text-heavy"
    language: str = "English"
    theme: str = "professional-blue"
    standard_template: str = "neo-standard"
    export_as: str = "pptx"
    image_type: str = "stock"
    content_generation: str = "enhance"
    include_table_of_contents: bool = True
    include_title_slide: bool = True
    web_search: bool = False
    markdown_emphasis: bool = True

    def normalize(self) -> "UserPreferences":
        self.n_slides = max(5, min(30, int(self.n_slides or 12)))
        if self.tone not in ALLOWED_TONES:
            self.tone = "professional"
        if self.verbosity not in ALLOWED_VERBOSITY:
            self.verbosity = "text-heavy"
        if self.export_as not in ALLOWED_FORMATS:
            self.export_as = "pptx"
        if self.image_type not in ALLOWED_IMAGE_TYPES:
            self.image_type = "stock"
        if self.standard_template not in ALLOWED_TEMPLATES:
            self.standard_template = "neo-standard"
        if self.theme not in ALLOWED_THEMES:
            self.theme = "professional-blue"
        self.language = (self.language or "English").strip() or "English"
        self.content_generation = (self.content_generation or "enhance").strip() or "enhance"
        self.include_table_of_contents = bool(self.include_table_of_contents)
        self.include_title_slide = bool(self.include_title_slide)
        self.web_search = bool(self.web_search)
        self.markdown_emphasis = bool(self.markdown_emphasis)
        return self

    def to_dict(self) -> dict[str, Any]:
        self.normalize()
        return asdict(self)

    @classmethod
    def from_any(cls, raw: Any) -> "UserPreferences":
        if isinstance(raw, cls):
            return raw.normalize()
        if isinstance(raw, dict):
            allowed = {k: raw[k] for k in cls.__dataclass_fields__.keys() if k in raw}
            return cls(**allowed).normalize()
        return cls().normalize()

    @classmethod
    def from_settings(cls, settings: Any) -> "UserPreferences":
        return cls(
            n_slides=getattr(settings, "default_slides", 12),
            tone=getattr(settings, "default_tone", "professional"),
            verbosity=getattr(settings, "default_verbosity", "text-heavy"),
            language=getattr(settings, "default_language", "English"),
            theme=getattr(settings, "default_theme", "professional-blue"),
            standard_template=getattr(settings, "default_template", "neo-standard"),
            export_as=getattr(settings, "default_export_as", "pptx"),
            image_type=getattr(settings, "default_image_type", "stock"),
            content_generation=getattr(settings, "default_content_generation", "enhance"),
            include_table_of_contents=getattr(settings, "default_include_toc", True),
            include_title_slide=getattr(settings, "default_include_title", True),
            web_search=getattr(settings, "default_web_search", False),
            markdown_emphasis=getattr(settings, "default_markdown_emphasis", True),
        ).normalize()


@dataclass(slots=True)
class PresentonTask:
    task_id: str
    status: str
    message: str
    data: dict[str, Any]
    error: dict[str, Any]
    raw: Any = None


@dataclass(slots=True)
class UploadResult:
    file_ids: list[str]
    raw: Any
