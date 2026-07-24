from sqlalchemy import Column, Integer, Boolean, Time
from bot.services.database import Base


class WorkingHours(Base):
    __tablename__ = 'working_hours'

    id = Column(Integer, primary_key=True, autoincrement=True)
    day_of_week = Column(Integer, nullable=False, unique=True)
    is_working_day = Column(Boolean, default=True)
    opening_time = Column(Time, nullable=False)
    closing_time = Column(Time, nullable=False)
    lunch_start = Column(Time)
    lunch_end = Column(Time)
    slot_duration = Column(Integer, default=60)