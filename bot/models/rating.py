from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from bot.services.database import Base


class Rating(Base):
    __tablename__ = 'ratings'
    
    rating_id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey('bookings.booking_id'), unique=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    rating = Column(Integer, nullable=False)
    review = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    booking = relationship("Booking", backref="rating")
    user = relationship("User", backref="ratings")