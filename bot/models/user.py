from sqlalchemy import Column, BigInteger, String, DateTime, func
from bot.services.database import Base

class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(BigInteger, primary_key=True)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    language = Column(String(2), default='en')
    created_at = Column(DateTime(timezone=True), server_default=func.now())