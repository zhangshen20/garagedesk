"""Runtime configuration. Everything comes from environment variables so the same
image runs locally, in CI (mock LLM) and in production (Nebius Token Factory)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM: Nebius Token Factory (OpenAI-compatible) ---------------------------------
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    # Three Nemotron tiers. Nano for cheap classification turns, Super for the
    # tool-calling agents, Ultra for the end-of-day owner report.
    model_fast: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    model_main: str = "nvidia/nemotron-3-super-120b-a12b"
    model_deep: str = "nvidia/Nemotron-3-Ultra-550b-a55b"
    # Reads photos of handwritten job cards; Nemotron Super then does the reasoning.
    model_vision: str = "openbmb/MiniCPM-V-4_5"
    # "nebius" talks to Token Factory; "mock" is a deterministic stand-in used by
    # tests and by the demo when no key is configured.
    llm_mode: str = "auto"  # auto | nebius | mock

    # --- Optional integrations ---------------------------------------------------------
    tavily_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # When Twilio credentials are absent every outbound SMS/call is written to the
    # outbox table instead, so the whole product still works end to end.

    # --- Storage -----------------------------------------------------------------------
    database_url: str = "sqlite:///./garagedesk.db"
    files_dir: str = "./files"

    # --- The shop ----------------------------------------------------------------------
    shop_name: str = "Sunshine Auto Care"
    shop_trading_name: str = "Sunshine Auto Care"
    shop_abn: str = "12 345 678 901"
    shop_address: str = "Whitehill Ave, Sunshine North VIC 3020"
    shop_phone: str = "(03) 9000 0000"
    shop_email: str = "desk@sunshineautocare.example"
    shop_hours: str = "Mon-Sat 8:00am-5:30pm"
    shop_timezone: str = "Australia/Melbourne"
    gst_rate: float = 0.10
    bays: int = 3
    owner_name: str = "Shen"
    owner_phone: str = "+61400000000"
    # Whoever does the books (in the real shop, the owner's wife). Invoices the owner
    # speaks wait for her one-tap approval unless they are under the auto-send limit.
    approver_name: str = "the office"
    approver_phone: str = "+61400000009"
    auto_approve_invoice_under_cents: int = 0  # inc GST; 0 = she approves every invoice
    labour_rate_cents: int = 12000  # per hour, ex GST
    parts_markup_percent: float = 0  # added to supplier receipt prices when they go on a job

    # --- The voice the owner hears (app/voice/tts.py) -----------------------------------
    tts_mode: str = "auto"  # auto | kokoro | mock | off (off = the browser's own voice)
    tts_voice: str = "af_heart"  # Kokoro voice; bf_emma / bm_george for British
    tts_speed: float = 1.12
    tts_model_dir: str = "./models/kokoro"

    # Lets anyone put the demo back to its clean recording state (POST /api/demo/reset).
    # Turn off for a real shop.
    demo_reset_enabled: bool = True

    app_secret: str = "change-me"
    public_base_url: str = "http://localhost:8000"

    @property
    def effective_llm_mode(self) -> str:
        if self.llm_mode == "auto":
            return "nebius" if self.nebius_api_key else "mock"
        return self.llm_mode

    @property
    def twilio_enabled(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)


@lru_cache
def get_settings() -> Settings:
    return Settings()
