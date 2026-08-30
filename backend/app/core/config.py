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
    geofence_radius_meters: float = 150
    geolocation_max_accuracy_meters: float = 100
    attendance_window_minutes: int = 240
    attendance_self_checkin_window_minutes: int = 5
    attendance_challenge_rotation_seconds: int = Field(default=20, ge=1)
    attendance_code_length: int = Field(default=5, ge=5, le=5)
    attendance_verification_timeout_seconds: int = Field(default=12, ge=1)
    attendance_max_code_attempts: int = Field(default=3, ge=1)
    check_in_attempt_rate_limit_seconds: int = 5
    attendance_threshold_percent: float = 75
    minimum_observations: int = 4
    college_name: str = "AntimBench College"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
