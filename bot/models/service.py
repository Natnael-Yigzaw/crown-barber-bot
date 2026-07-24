from sqlalchemy import Column, Integer, String, Boolean
from bot.services.database import Base

class Service(Base):
    __tablename__ = 'services'
    
    service_id = Column(Integer, primary_key=True, autoincrement=True)
    name_en = Column(String(255), nullable=False)
    name_am = Column(String(255), nullable=False)
    price = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, default=True)