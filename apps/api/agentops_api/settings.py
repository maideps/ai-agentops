"""Environment settings. ``LLM_MODE=mock`` is the default whatever keys the machine holds."""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMMode = Literal["mock", "replay", "hosted_free", "live_paid"]
_LIVE_MODES: frozenset[str] = frozenset({"hosted_free", "live_paid"})


class Settings(BaseSettings):
    """Typed runtime configuration, read from environment variables only."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    llm_mode: LLMMode = "mock"
    enable_live_llm: bool = False
    llm_provider: str = "mock"
    llm_model: str = "mock-deterministic-v1"
    max_llm_calls_per_run: int = Field(default=6, ge=0)
    max_tool_calls_per_run: int = Field(default=8, ge=0)
    max_graph_steps: int = Field(default=16, ge=1)
    max_run_seconds: int = Field(default=90, ge=1)
    max_output_tokens: int = Field(default=500, ge=1)
    max_requests_per_demo_user: int = Field(default=5, ge=0)
    database_url: SecretStr | None = None
    langfuse_enabled: bool = False

    @model_validator(mode="after")
    def _live_modes_require_opt_in(self) -> Self:
        if self.llm_mode in _LIVE_MODES and not self.enable_live_llm:
            msg = f"LLM_MODE={self.llm_mode} requires ENABLE_LIVE_LLM=true"
            raise ValueError(msg)
        return self
