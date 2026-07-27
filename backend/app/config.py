from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str = "change-me-dev-key"
    database_url: str = "sqlite:///./promptguard.db"
    # Comma-separated list of allowed CORS origins. The Chrome extension's
    # background service worker fetch is NOT subject to this (MV3 background
    # workers with host_permissions bypass page-level CORS entirely) - this
    # setting only matters for browser-context requests, e.g. a page's own JS
    # trying to call the API directly. Defaults to no allowed origins rather
    # than "*"; add the dashboard's origin or a specific chrome-extension://
    # id here if you need direct browser-side calls.
    allowed_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
