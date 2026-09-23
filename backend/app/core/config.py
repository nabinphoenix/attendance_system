from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AntimBench API"
    database_url: str
    jwt_secret_key: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    auth_cookie_name: str = "antimbench_session"
    auth_cookie_secure: bool = False
    max_failed_login_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit: int = Field(default=60, ge=5)
    login_rate_window_seconds: int = Field(default=300, ge=1)
    reset_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    reset_request_ip_limit: int = Field(default=10, ge=1)
    reset_request_email_limit: int = Field(default=3, ge=1)
    reset_verify_rate_limit: int = Field(default=20, ge=1)
    reset_rate_window_seconds: int = Field(default=900, ge=1)
    reset_email_cooldown_seconds: int = Field(default=60, ge=1)
    trusted_proxy_cidrs: list[str] = [
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/16",
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    ]
    geofence_radius_meters: float = 150
    attendance_max_geofence_radius_meters: float = Field(default=2000, ge=10, le=5000)
    geolocation_max_accuracy_meters: float = 100
    attendance_window_minutes: int = 240
    attendance_self_checkin_window_minutes: int = Field(default=15, ge=1, le=240)
    attendance_challenge_rotation_seconds: int = Field(default=20, ge=1)
    attendance_code_length: int = Field(default=6, ge=6, le=6)
    attendance_verification_timeout_seconds: int = Field(default=12, ge=1)
    attendance_max_code_attempts: int = Field(default=3, ge=1)
    check_in_attempt_rate_limit_seconds: int = 5
    attendance_threshold_percent: float = 75
    minimum_observations: int = 4
    college_name: str = "Techspire College"
    academic_timezone: str = "Asia/Kathmandu"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "notifications@antimbench.local"
    notification_worker_poll_seconds: float = 5
    notification_worker_batch_size: int = 100
    profile_media_bucket: str | None = None
    profile_media_prefix: str = "profile-media"
    profile_media_region: str | None = None
    profile_media_local_directory: str | None = None
    frontend_url: str = "http://localhost:3000"
    invitation_expire_hours: int = 168
    cors_origins: list[str] = ["http://localhost:3000"]
    # AI assistant keys are deliberately server-only. Do not prefix them with
    # NEXT_PUBLIC_ or expose them through a frontend route.
    ai_enabled: bool = True
    ai_provider_order: str = "groq,openrouter,gemini"
    ai_groq_api_key: str | None = None
    ai_groq_model: str = "llama-3.1-8b-instant"
    ai_openrouter_api_key: str | None = None
    ai_openrouter_model: str | None = None
    ai_gemini_api_key: str | None = None
    ai_gemini_model: str = "gemini-2.5-flash"
    ai_request_timeout_seconds: float = Field(default=30, ge=5, le=120)
    ai_max_tool_rounds: int = Field(default=8, ge=1, le=8)
    ai_confirmation_expire_minutes: int = Field(default=10, ge=1, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
