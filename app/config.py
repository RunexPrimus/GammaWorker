from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'Runex Presenton Worker'
    worker_id: str = 'worker-1'
    poll_interval_seconds: int = 5
    worker_run_once: bool = False

    web_internal_base_url: str = 'http://localhost:8000'
    internal_api_token: str = 'change-me-internal-token'
    bot_token: str = ''

    presenton_base_url: str = 'http://presenton:80'
    presenton_api_key: str = ''
    presenton_template: str = 'modern'
    presenton_theme: str = 'professional-blue'
    presenton_export_default: str = 'pptx'
    presenton_include_title_slide: bool = True
    presenton_include_toc: bool = False
    presenton_image_type: str = 'stock'
    presenton_content_generation: str = 'enhance'
    presenton_markdown_emphasis: bool = True
    presenton_web_search: bool = False

    @property
    def telegram_api_base(self) -> str:
        return f'https://api.telegram.org/bot{self.bot_token}'

    @property
    def web_base(self) -> str:
        return self.web_internal_base_url.rstrip('/')


settings = Settings()
