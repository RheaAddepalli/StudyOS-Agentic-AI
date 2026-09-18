"""Central configuration. Everything here is read from the environment so the
same code runs the same way locally, in CI, and in whatever host eventually
runs the MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    model: str = os.getenv("STUDYOS_MODEL", "openai/gpt-oss-120b")
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    db_path: str = os.getenv("STUDYOS_DB_PATH", "./studyos_state.db")
    # If set (e.g. a Neon connection string), state persists to Postgres.
    # If unset, falls back to the local SQLite file at db_path — this keeps
    # `pytest` and local CLI use working with zero setup.
    database_url: str | None = os.getenv("DATABASE_URL")
    allowed_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    )

    # Hard caps so a bad research node can't burn the whole search budget
    # on one node, and so no single tool call can hang forever.
    max_resources_per_concept: int = 6
    tool_timeout_seconds: float = 20.0
    code_exec_timeout_seconds: float = 8.0


settings = Settings()
