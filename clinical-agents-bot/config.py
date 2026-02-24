import os
from dataclasses import dataclass


@dataclass
class AgentConfig:
    base_url: str
    api_key: str = "not-needed"


@dataclass
class AuthConfig:
    username: str
    password: str
    default_staff: str


@dataclass
class LineBotConfig:
    secret: str
    access_token: str


@dataclass
class Config:
    line_bot: LineBotConfig
    agent: AgentConfig
    auth_manager: AuthConfig

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            line_bot=LineBotConfig(
                secret=os.getenv("LINE_CHANNEL_SECRET", ""),
                access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
            ),
            agent=AgentConfig(
                base_url=os.getenv("AGENT_URL", "http://localhost:8080/")
            ),
            auth_manager=AuthConfig(
                username=os.getenv("ADMIN_USERNAME", "admin"),
                password=os.getenv("ADMIN_PASSWORD", "admin"),
                default_staff=os.getenv("DEFAULT_STAFF", ""),
            ),
        )


config = Config.from_env()
