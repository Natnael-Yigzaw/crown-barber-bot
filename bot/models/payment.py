from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from bot.services.database import Base

class Payment(Base):
    __tablename__ = 'payments'
    
    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey('bookings.booking_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    amount = Column(Integer, nullable=False)
    screenshot_path = Column(Text)
    status = Column(String(20), default='pending')
    verified_at = Column(DateTime(timezone=True))
    decline_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    booking = relationship("Booking", backref="payments")
    user = relationship("User", backref="payments")