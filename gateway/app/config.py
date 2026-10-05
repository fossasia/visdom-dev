# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Loads configuration settings from environment variables or a local .env file.
Manages database paths, JWT encryption secrets, and token expiration times.
"""

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

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
