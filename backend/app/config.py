from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/financehome"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | development | production
    plaid_webhook_url: str = ""

    # Google Gemini (used for insights + transaction categorization)
    gemini_api_key: str = ""

    # Anthropic Claude (paid alternative for insights + categorization)
    anthropic_api_key: str = ""

    # Admin emails (comma-separated) — these users get Claude access
    admin_emails: str = ""

    # Encryption key for Plaid access tokens
    encryption_key: str = ""

    # Resend (email notifications)
    resend_api_key: str = ""
    alert_from_email: str = "FinanceHome <onboarding@resend.dev>"

    # Scheduler secret (authenticates Cloud Scheduler → digest endpoint)
    scheduler_secret: str = "change-me"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    @property
    def admin_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # CORS
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
