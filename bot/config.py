from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    BOT_TOKEN: str
    ADMIN_USER_ID: int
    
    SHOP_NAME: str
    SHOP_ADDRESS: str
    SHOP_PHONE: str
    
    DEPOSIT_AMOUNT: int
    CBE_ACCOUNT: str
    TELEBIRR_NUMBER: str
    
    OPENING_TIME: str
    CLOSING_TIME: str
    CLOSED_DAYS: str
    
    MAX_BOOKING_DAYS: int = 7
    SLOT_DURATION_MINUTES: int = 30
    SCREENSHOTS_DIR: str = "screenshots"
    PAYMENTS_CHANNEL_ID: int
    
    @property
    def closed_days_list(self) -> list:
        return [int(d.strip()) for d in self.CLOSED_DAYS.split(',') if d.strip()]
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()