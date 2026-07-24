from sqlalchemy import Column, Integer, BigInteger, String, Date, Time, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from bot.services.database import Base

class Booking(Base):
    __tablename__ = 'bookings'
    
    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    service_id = Column(Integer, ForeignKey('services.service_id'), nullable=False)
    booking_date = Column(Date, nullable=False)
    booking_time = Column(Time, nullable=False)
    status = Column(String(20), default='pending_payment')
    deposit_amount = Column(Integer, nullable=False)
    remaining_amount = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="bookings")
    service = relationship("Service", backref="bookings")