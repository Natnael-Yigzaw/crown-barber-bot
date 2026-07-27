from datetime import time
from typing import Optional
from sqlalchemy import select
from bot.services.database import async_session
from bot.models.working_hours import WorkingHours
from bot.utils.time_format import to_12h

DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_NAMES_AM = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሁድ"]
_UNSET = object()


async def get_day_schedule(day_of_week: int) -> Optional[WorkingHours]:
    async with async_session() as session:
        result = await session.execute(
            select(WorkingHours).where(WorkingHours.day_of_week == day_of_week)
        )
        return result.scalar_one_or_none()


async def get_all_schedules() -> list[WorkingHours]:
    async with async_session() as session:
        result = await session.execute(
            select(WorkingHours).order_by(WorkingHours.day_of_week)
        )
        return list(result.scalars().all())


async def update_day_schedule(
    day_of_week: int,
    is_working_day: bool = None,
    opening_time: time = None,
    closing_time: time = None,
    lunch_start: time | None | object = _UNSET,
    lunch_end: time | None | object = _UNSET,
    slot_duration: int = None,
):
    async with async_session() as session:
        result = await session.execute(
            select(WorkingHours).where(WorkingHours.day_of_week == day_of_week)
        )
        wh = result.scalar_one_or_none()
        
        if not wh:
            wh = WorkingHours(day_of_week=day_of_week)
            session.add(wh)
        
        if is_working_day is not None:
            wh.is_working_day = is_working_day
        if opening_time is not None:
            wh.opening_time = opening_time
        if closing_time is not None:
            wh.closing_time = closing_time
        if lunch_start is not _UNSET:
            wh.lunch_start = lunch_start
        if lunch_end is not _UNSET:
            wh.lunch_end = lunch_end
        if slot_duration is not None:
            wh.slot_duration = slot_duration
        
        await session.commit()


def format_time(t: time) -> str:
    """Format time for 12-hour display"""
    return to_12h(t)


def to_ethiopian_time_str(western_time: time) -> str:
    """Convert Western time to Ethiopian time string for display"""
    from bot.utils.time_format import get_ethiopian_period

    hour = western_time.hour
    minute = western_time.minute
    
    # Convert to Ethiopian hour
    if hour >= 6:
        eth_hour = hour - 6
    else:
        eth_hour = hour + 18
    
    eth_hour = eth_hour % 24
    
    # Get period
    period = get_ethiopian_period(hour)
    
    # Format
    if eth_hour == 0:
        display_hour = 12
    elif eth_hour > 12:
        display_hour = eth_hour - 12
    else:
        display_hour = eth_hour
    
    return f"{display_hour}:{minute:02d} {period}"


def format_working_hours_display(schedule: WorkingHours) -> str:
    """Format working hours for admin display showing 12-hour times"""
    western_open = to_12h(schedule.opening_time)
    western_close = to_12h(schedule.closing_time)
    eth_open = to_ethiopian_time_str(schedule.opening_time)
    eth_close = to_ethiopian_time_str(schedule.closing_time)
    
    lunch = ""
    if schedule.lunch_start and schedule.lunch_end:
        western_lunch = f"{to_12h(schedule.lunch_start)}-{to_12h(schedule.lunch_end)}"
        eth_lunch = f"{to_ethiopian_time_str(schedule.lunch_start)}-{to_ethiopian_time_str(schedule.lunch_end)}"
        lunch = f"\n   Lunch: {western_lunch} (Eth: {eth_lunch})"
    
    return (
        f"   {western_open} - {western_close}{lunch}\n"
        f"   Ethiopian: {eth_open} - {eth_close}\n"
        f"   Slots: {schedule.slot_duration} min"
    )
