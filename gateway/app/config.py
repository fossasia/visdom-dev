# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Loads configuration settings from environment variables or a local .env file.
Manages database paths, JWT encryption secrets, and token expiration times.
"""

import datetime

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    ADMIN_ENABLED: bool = False
    ADMIN_SECRET: str = ""
    DB_MAX_OVERFLOW: int = 5
    COOKIE_SECURE: bool = False
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    API_KEY_PREFIX: str = "visdom_live"
    PORT: int = 8085
    FRONTEND_URL: str = "http://localhost:5173"
    VISDOM_SERVERS: str = ""
    ADMIN_ENVIRONMENT: str = ""
    VISDOM_ACTIVITY_TIMEOUT: float = 1.0
    VISDOM_INTERNAL_PORT: int = 8098
    VISDOM_INTERNAL_READ_KEY: str = ""
    VISDOM_INTERNAL_ADMIN_KEY: str = ""
    VISDOM_INTERNAL_CA: str = ""
    USAGE_SAMPLE_SECONDS: int = 60
    RETENTION_SWEEP_HOURS: int = 24
    RETENTION_ENFORCE: bool = False
    RETENTION_TIMEOUT: float = 15.0
    RETENTION_STARTS: datetime.date | None = None
    RETENTION_WARN_DAYS: int = 3
    ACCOUNT_DELETION_HOURS: int = 6
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    SUPPORT_CONTACT: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_FROM_NAME: str = "Visdom"

    model_config = SettingsConfigDict(env_file=".env")

    @field_validator("RETENTION_STARTS", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        return value or None

settings = Settings()
