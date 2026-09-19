from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DD_", extra="ignore")

    app_name: str = "dd-context-engine"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://dd:dd@localhost:5432/dd_context"
    max_context_assertions: int = 20
    max_context_evidence: int = 8
    enable_graph: bool = False
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None


settings = Settings()
