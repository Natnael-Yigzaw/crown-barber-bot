from sqlalchemy import Column, String, Text, DateTime, func
from bot.services.database import Base


class ShopSetting(Base):
    __tablename__ = 'shop_settings'

    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())