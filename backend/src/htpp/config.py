"""Runtime settings. Credentials come from the environment only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_prefix="HTPP_",
        extra="ignore",
    )

    panel_base_url: str = "https://panel.htpp.in"
    panel_username: str = ""
    panel_password: str = ""
    session_cookie: str = ""
    machine_ids: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [1093, 1094, 1146])
    request_min_interval_s: float = 2.0
    request_timeout_s: float = 30.0
    backfill_chunk_days: int = 3
    history_floor_date: date = date(2026, 8, 1)
    db_path: str = "data/htpp.duckdb"
    excel_drop_dir: str = "data/excel_drop"
    artifact_dir: str = "backend/artifacts"
    incremental_cron_minutes: int = 4
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_workspace_id: str = ""
    api_cors_origins: str = "http://localhost:3000"
    plant_label: str = "Plant Floor"
    # "1093:R1 Unit 1,1094:R2 Unit 2,1146:R3 Unit 3"
    machine_labels: str = "1093:R1 Unit 1,1094:R2 Unit 2,1146:R3 Unit 3"
    # Excel / panel alias → id, "Unit 1:1093,R1:1093,..."
    machine_aliases: str = "R1:1093,Reactor 1:1093,Unit 1:1093,R2:1094,Reactor 2:1094,Unit 2:1094,R3:1146,Reactor 3:1146,Unit 3:1146"

    @field_validator("machine_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        return value

    def machine_label_map(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for part in self.machine_labels.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            mid, label = part.split(":", 1)
            try:
                out[int(mid.strip())] = label.strip()
            except ValueError:
                continue
        return out

    def machine_alias_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for part in self.machine_aliases.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            name, mid = part.split(":", 1)
            try:
                out[name.strip()] = int(mid.strip())
            except ValueError:
                continue
        return out

    def path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute():
            return candidate
        return ROOT / candidate

    @property
    def db_file(self) -> Path:
        return self.path(self.db_path)

    @property
    def excel_dir(self) -> Path:
        return self.path(self.excel_drop_dir)

    @property
    def artifacts(self) -> Path:
        return self.path(self.artifact_dir)

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]


settings = Settings()
