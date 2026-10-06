"""Runtime configuration for the core profile.

Core must start with no GPU, no model, no dataset, no cloud credentials
and no laboratory connection (handoff §4, kickoff §4). Everything here
is environment-driven; secrets never have defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable core settings resolved from the environment."""

    bind_host: str = "127.0.0.1"
    port: int = 8787
    database_url: str = "postgresql://studio:studio@127.0.0.1:54329/studio"
    # Vault lives outside the repository and any web root (§5.2, §21.3).
    vault_root: Path = field(
        default_factory=lambda: (
            Path.home() / ".local" / "share" / "chemistry-studio" / "vault"
        ).resolve()
    )
    # Upload/archive limits enforced while streaming and at commit.
    artifact_max_bytes: int = 512 * 1024 * 1024
    artifact_max_archive_members: int = 10_000
    artifact_max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    artifact_max_compression_ratio: int = 100
    staging_ttl_seconds: int = 24 * 3600
    # Allowed Origin/Host values for the loopback deployment. Team/LAN
    # access is disabled until real auth+TLS is configured (E04, U07).
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    session_ttl_seconds: int = 60 * 60 * 12
    # Runtime profile switches. Only "core" is enabled unconditionally.
    profile_local_ai: bool = False
    profile_optimization: bool = False
    profile_quantum: bool = False
    profile_materials: bool = False
    profile_training: bool = False
    profile_design: bool = False
    profile_synthesis: bool = False

    @property
    def database_dsn_alembic(self) -> str:
        """Alembic/psycopg DSN."""
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = _env("STUDIO_ALLOWED_ORIGINS")
    return Settings(
        bind_host=_env("STUDIO_BIND_HOST", "127.0.0.1") or "127.0.0.1",
        port=int(_env("STUDIO_PORT", "8787") or "8787"),
        database_url=_env("STUDIO_DATABASE_URL") or Settings.database_url,
        vault_root=Path(_env("STUDIO_VAULT_ROOT") or str(Settings().vault_root)).resolve(),
        artifact_max_bytes=int(
            _env("STUDIO_ARTIFACT_MAX_BYTES", str(Settings.artifact_max_bytes))
            or str(Settings.artifact_max_bytes)
        ),
        allowed_origins=tuple(o.strip() for o in origins.split(","))
        if origins
        else Settings.allowed_origins,
        session_ttl_seconds=int(_env("STUDIO_SESSION_TTL_SECONDS", "43200") or "43200"),
        profile_local_ai=(_env("STUDIO_PROFILE_LOCAL_AI") or "").lower() in _TRUE,
        profile_optimization=(_env("STUDIO_PROFILE_OPTIMIZATION") or "").lower() in _TRUE,
        profile_quantum=(_env("STUDIO_PROFILE_QUANTUM") or "").lower() in _TRUE,
        profile_materials=(_env("STUDIO_PROFILE_MATERIALS") or "").lower() in _TRUE,
        profile_training=(_env("STUDIO_PROFILE_TRAINING") or "").lower() in _TRUE,
        profile_design=(_env("STUDIO_PROFILE_DESIGN") or "").lower() in _TRUE,
        profile_synthesis=(_env("STUDIO_PROFILE_SYNTHESIS") or "").lower() in _TRUE,
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
