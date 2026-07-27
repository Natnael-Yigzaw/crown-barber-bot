"""12-hour time formatting utilities with Ethiopian period display"""

from datetime import time


def to_12h(t: time) -> str:
    """Convert time to 12-hour format with AM/PM"""
    hour = t.hour
    minute = t.minute
    
    if hour == 0:
        return f"12:{minute:02d} AM"
    elif hour < 12:
        return f"{hour}:{minute:02d} AM"
    elif hour == 12:
        return f"12:{minute:02d} PM"
    else:
        return f"{hour - 12}:{minute:02d} PM"


def to_12h_str(time_str: str) -> str:
    """Convert 'HH:MM' string to 12-hour format"""
    hour, minute = map(int, time_str.split(":"))
    
    if hour == 0:
        return f"12:{minute:02d} AM"
    elif hour < 12:
        return f"{hour}:{minute:02d} AM"
    elif hour == 12:
        return f"12:{minute:02d} PM"
    else:
        return f"{hour - 12}:{minute:02d} PM"


def get_ethiopian_period(hour: int) -> str:
    """
    Get Ethiopian period based on Western hour.
    
    7 AM - 11 AM  → ጠዋት (Morning)
    12 PM         → ቀን (Noon)
    1 PM - 5 PM   → ከሰዓት (Afternoon)
    6 PM - 6 AM   → ምሽት (Night)
    """
    if 7 <= hour <= 11:
        return "ጠዋት"
    elif hour == 12:
        return "ቀን"
    elif 13 <= hour <= 17:
        return "ከሰዓት"
    else:
        return "ምሽት"


def to_ethiopian_display(western_time_str: str) -> str:
    """
    Convert Western time to Ethiopian time for display.
    Shows Ethiopian hour with period.
    
    Examples:
    08:00 → 2:00 ጠዋት
    12:00 → 6:00 ቀን
    14:00 → 8:00 ከሰዓት
    19:00 → 1:00 ምሽት
    """
    hour, minute = map(int, western_time_str.split(":"))
    
    # Convert to Ethiopian hour
    if hour >= 6:
        eth_hour = hour - 6
    else:
        eth_hour = hour + 18
    
    eth_hour = eth_hour % 24
    
    # Get Ethiopian period
    period = get_ethiopian_period(hour)
    
    # Convert to 12-hour display
    if eth_hour == 0:
        display_hour = 12
    elif eth_hour > 12:
        display_hour = eth_hour - 12
    else:
        display_hour = eth_hour
    
    return f"{display_hour}:{minute:02d} {period}"


def format_time_slot_label(western_time_str: str, lang: str = 'en') -> str:
    """
    Format time slot button label.
    
    English: "8:00 AM"
    Amharic: "8:00 AM (2:00 ጠዋት)"
    """
    label_12h = to_12h_str(western_time_str)
    
    if lang == 'am':
        eth_time = to_ethiopian_display(western_time_str)
        return f"{label_12h}\n({eth_time})"
    else:
        return label_12h