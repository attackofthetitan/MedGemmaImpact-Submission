import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    base_url: str
    model_name: str
    api_key: str = "not-needed"
    temperature: float = 0.1
    max_tokens: int = 2048


@dataclass
class EmbeddingConfig:
    base_url: str
    model_name: str
    api_key: str = "not-needed"


@dataclass
class AuthConfig:
    jwt_secret: str = "test-secret"
    jwt_algorithm: str = "HS256"
    token_expire_minutes: int = 480  # 8 hours
    default_admin_user: str = "admin"
    default_admin_password: str = "admin123"


@dataclass
class Config:
    router_llm: LLMConfig
    medical_llm: LLMConfig
    embedding: EmbeddingConfig
    auth: AuthConfig
    locale: str = "zh-TW"
    chroma_dir: str = "./chroma_db"
    db_path: str = "./clinical.db"
    mock_data_dir: str = "./mock_data"
    max_upload_size_mb: int = 10

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            router_llm=LLMConfig(
                base_url=os.getenv("ROUTER_LLM_URL", "http://localhost:8001/v1"),
                model_name=os.getenv("ROUTER_MODEL", "router"),
                temperature=0.0,
                max_tokens=512,
            ),
            medical_llm=LLMConfig(
                base_url=os.getenv("MEDICAL_LLM_URL", "http://localhost:8002/v1"),
                model_name=os.getenv("MEDICAL_MODEL", "medgemma"),
                temperature=0.0,
                max_tokens=8192,
            ),
            embedding=EmbeddingConfig(
                base_url=os.getenv("EMBEDDING_URL", "http://localhost:8003/v1"),
                model_name=os.getenv("EMBEDDING_MODEL", "embedgemma"),
            ),
            auth=AuthConfig(
                jwt_secret=os.getenv("JWT_SECRET", "change-me-in-production"),
                token_expire_minutes=int(os.getenv("TOKEN_EXPIRE_MINUTES", "480")),
            ),
            locale=os.getenv("LOCALE", "zh-TW"),
            chroma_dir=os.getenv("CHROMA_DIR", "./chroma_db"),
            db_path=os.getenv("DB_PATH", "./clinical.db"),
            mock_data_dir=os.getenv("MOCK_DATA_DIR", "./mock_data"),
        )


config = Config.from_env()