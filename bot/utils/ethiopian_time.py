from datetime import datetime, time, date, timedelta

MONTHS_AM = [
    "ጃንዩዌሪ", "ፌብሩዌሪ", "ማርች", "ኤፕሪል",
    "ሜይ", "ጁን", "ጁላይ", "ኦገስት",
    "ሴፕቴምበር", "ኦክቶበር", "ኖቬምበር", "ዲሴምበር"
]

DAYS_AM = ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሁድ"]
DAYS_AM_SHORT = ["ሰኞ", "ማክሰ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሁድ"]

ETH_MONTHS = [
    "መስከረም", "ጥቅምት", "ህዳር", "ታህሳስ",
    "ጥር", "የካቲት", "መጋቢት", "ሚያዝያ",
    "ግንቦት", "ሰኔ", "ሐምሌ", "ነሐሴ", "ጳጉሜ"
]


def to_ethiopian_time(western_time_str: str) -> str:
    """
    Convert Western 24h time to Ethiopian time.
    
    Ethiopian time starts at 6:00 AM Western = 12:00 ጠዋት (morning)
    
    Examples:
    02:00 -> 8:00 ምሽት (8 at night)
    06:00 -> 12:00 ጠዋት (12 morning)
    07:00 -> 1:00 ጠዋት (1 morning)
    12:00 -> 6:00 ቀን (6 day)
    13:00 -> 7:00 ቀን (7 day)
    18:00 -> 12:00 ምሽት (12 evening)
    19:00 -> 1:00 ምሽት (1 evening/night)
    """
    hour, minute = map(int, western_time_str.split(":"))
    
    if hour >= 6:
        eth_hour = hour - 6
    else:
        eth_hour = hour + 18
    
    eth_hour = eth_hour % 24
    
    if eth_hour == 0:
        display_hour = 12
    elif eth_hour > 12:
        display_hour = eth_hour - 12
    else:
        display_hour = eth_hour
    
    if hour >= 6 and hour < 12:
        period = "ጠዋት" 
    elif hour >= 12 and hour < 18:
        period = "ቀን"
    else:
        period = "ምሽት"
    
    return f"{display_hour}:{minute:02d} {period}"


def is_gregorian_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def gregorian_to_ethiopian(greg_date: date) -> tuple:
    new_year_day = 12 if is_gregorian_leap(greg_date.year) else 11
    new_year_date = date(greg_date.year, 9, new_year_day)

    if greg_date >= new_year_date:
        eth_year = greg_date.year - 7
        delta = (greg_date - new_year_date).days
    else:
        eth_year = greg_date.year - 8
        prev_new_year = date(greg_date.year - 1, 9, 12 if is_gregorian_leap(greg_date.year - 1) else 11)
        delta = (greg_date - prev_new_year).days

    eth_month = (delta // 30) + 1
    eth_day = (delta % 30) + 1

    if eth_month > 13:
        eth_month = 13
        eth_day = delta - 360 + 1

    return eth_year, eth_month, eth_day


def format_ethiopian_date(greg_date: date) -> str:
    """Format as: ሐሙስ፣ ሐምሌ 17፣ 2016"""
    year, month, day = gregorian_to_ethiopian(greg_date)
    day_name = DAYS_AM[greg_date.weekday()]
    month_name = ETH_MONTHS[month - 1]
    return f"{day_name}፣ {month_name} {day}፣ {year}"


def format_ethiopian_date_short(greg_date: date) -> str:
    """Format as: ሐሙስ ሐምሌ 17"""
    year, month, day = gregorian_to_ethiopian(greg_date)
    day_name = DAYS_AM[greg_date.weekday()]
    month_name = ETH_MONTHS[month - 1]
    return f"{day_name} {month_name} {day}"


def format_date_am(date_obj) -> str:
    """Format date in Amharic using Gregorian months: ሰኞ፣ ጁላይ 24"""
    day_name = DAYS_AM[date_obj.weekday()]
    month = MONTHS_AM[date_obj.month - 1]
    return f"{day_name}፣ {month} {date_obj.day}"


def format_date_am_short(date_obj) -> str:
    """Format date in short Amharic: ሰኞ 24/7"""
    day_name = DAYS_AM_SHORT[date_obj.weekday()]
    return f"{day_name} {date_obj.day}/{date_obj.month}"


def format_booking_datetime_am(date_obj, time_str: str) -> str:
    """Format full booking datetime in Amharic with Ethiopian time"""
    date_formatted = format_ethiopian_date(date_obj)
    eth_time = to_ethiopian_time(time_str)
    
    return (
        f"📅 {date_formatted}\n"
        f"🕐 {eth_time}"
    )