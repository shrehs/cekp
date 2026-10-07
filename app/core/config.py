"""
Central configuration for CEKP.
All environment-driven settings live here so no module reaches
into os.environ directly.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CEKP_",
    )
    # App
    app_name: str = "CEKP - Connected Enterprise Knowledge Platform"
    environment: str = "local"

    # Query trace endpoint (/query/trace) -- unredacted internal debugging
    # view, real attack surface if left reachable. Enforced in code
    # (app/api/query.py), not just documentation. Explicit opt-in via env
    # var overrides the environment-based default below if set.
    enable_trace_endpoint: bool | None = None
    otlp_endpoint: str | None = None

    # Postgres (metadata / RBAC)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "cekp"
    postgres_user: str = "cekp"
    postgres_password: str = "cekp_dev_password"

    # Qdrant (vector store)
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "cekp_chunks"

    # Neo4j (code-structure graph -- see docs/graph-schema.md)
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "cekp_dev_password"

    # Timeouts
    qdrant_timeout_seconds: float = 5.0
    neo4j_connection_timeout_seconds: float = 5.0
    neo4j_max_transaction_retry_seconds: float = 10.0

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Ingestion
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 60
    github_api_base: str = "https://api.github.com"
    github_token: str | None = None  # Optional: GitHub personal access token for higher rate limits

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def trace_endpoint_enabled(self) -> bool:
        """
        Resolved value actually used by the endpoint. Explicit env var
        (CEKP_ENABLE_TRACE_ENDPOINT=true/false) always wins; otherwise
        defaults to enabled only in local/development, disabled everywhere
        else. Fails closed on unrecognized environments.
        """
        if self.enable_trace_endpoint is not None:
            return self.enable_trace_endpoint
        return self.environment.lower() in {"local", "development", "dev"}

settings = Settings()