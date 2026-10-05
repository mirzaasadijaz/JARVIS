"""
Loads every value from .env into a single typed, validated Settings object.

Usage:
    from config import settings
    settings.anthropic_api_key          # -> str | None
    settings.require("deepgram_api_key", "elevenlabs_api_key")

Every field is Optional at the type level, on purpose: which keys you
actually need depends on which phase you've reached — see
Jarvis_Build_Workflow.md. The one thing that's always required, in every
phase, is at least one LLM "brain" key — that's the sole check that runs
automatically when Settings() is constructed. Everything else is checked
lazily: call settings.require(...) at the top of whichever tool needs it,
so a missing key fails immediately and clearly, at the moment it's
actually needed — not eagerly for phases you haven't built yet.
"""

from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # don't choke on unrelated env vars already in the shell
    )

    # ---------------- Phase 1 — the brain (pick at least one) ----------------
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

    # ---------------- Phase 1 — weather, your first tool ----------------
    openweathermap_api_key: Optional[str] = None

    # ---------------- Phase 2 — voice in, voice out ----------------
    deepgram_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None

    # ---------------- Phase 3 — voice lock (wake word + PIN) ----------------
    jarvis_pin: Optional[str] = None

    # ---------------- Phase 5 — WhatsApp (Evolution API) ----------------
    whatsapp_bridge_url: str = "http://localhost:3001"
    webhook_secret: Optional[str] = None
    jarvis_owner_number: Optional[str] = None
    cloudflare_tunnel_token: Optional[str] = None

    # ---------------- Phase 6 — email ----------------
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    gmail_refresh_token: Optional[str] = None

    # ---------------- Phase 6 — memory / embeddings ----------------
    voyage_api_key: Optional[str] = None

    # ---------------- Phase 6 — social media ----------------
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None
    meta_page_access_token: Optional[str] = None
    instagram_business_account_id: Optional[str] = None

    # ---------------- Phase 6 — research & maps ----------------
    serpapi_api_key: Optional[str] = None
    google_maps_api_key: Optional[str] = None

    # ---------------- Phase 8 — reliability & observability ----------------
    langsmith_api_key: Optional[str] = None
    langchain_tracing_v2: bool = True
    langchain_project: str = "jarvis"

    # ---------------- general app config ----------------
    environment: str = "development"
    log_level: str = "INFO"
    timezone: str = "Asia/Karachi"
    daily_cost_cap_usd: float = 5.0

    # -----------------------------------------------------------------
    # Cross-field validation & helpers
    # -----------------------------------------------------------------

    @model_validator(mode="after")
    def _check_brain_key_present(self) -> "Settings":
        """The one thing every phase needs: at least one LLM key."""
        brain_keys = (
            self.anthropic_api_key,
            self.openai_api_key,
            self.google_api_key,
            self.groq_api_key,
        )
        if not any(brain_keys):
            raise ValueError(
                "No brain configured. Set exactly one of ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, GOOGLE_API_KEY, or GROQ_API_KEY in .env — "
                "see the 'PICK ONE' section in .env.example."
            )
        return self

    @property
    def active_brain(self) -> tuple[str, str]:
        """(provider_name, key) for whichever brain key is set — checked in
        the order the Tech Stack Guide recommends them. agent.py uses this
        to pick the model without caring which one you configured."""
        for provider, key in (
            ("anthropic", self.anthropic_api_key),
            ("openai", self.openai_api_key),
            ("google", self.google_api_key),
            ("groq", self.groq_api_key),
        ):
            if key:
                return provider, key
        raise RuntimeError("unreachable — _check_brain_key_present already guarantees one exists")

    def require(self, *field_names: str) -> None:
        """Call at the top of a tool/module that needs specific keys, e.g.:
            settings.require("deepgram_api_key", "elevenlabs_api_key")
        Fails immediately with a clear message naming exactly what's missing,
        instead of a confusing error three calls deep into a live conversation.
        """
        missing = [name for name in field_names if not getattr(self, name, None)]
        if missing:
            raise ValueError(
                f"Missing required setting(s): {', '.join(missing)}. "
                f"Add them to .env — see .env.example for what each one is and where to get it."
            )


settings = Settings()