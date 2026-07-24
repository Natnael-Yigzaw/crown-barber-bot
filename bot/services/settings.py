from typing import Any
from sqlalchemy import select
from bot.config import settings
from bot.models.shop_setting import ShopSetting
from bot.services.database import async_session

_cache: dict[str, Any] = {}
_cache_loaded = False


async def refresh_cache():
    """Reload all settings from database"""
    global _cache, _cache_loaded
    
    _cache = {
        "SHOP_NAME": settings.SHOP_NAME,
        "SHOP_ADDRESS": settings.SHOP_ADDRESS,
        "SHOP_PHONE": settings.SHOP_PHONE,
        "DEPOSIT_AMOUNT": str(settings.DEPOSIT_AMOUNT),
        "CBE_ACCOUNT": settings.CBE_ACCOUNT,
        "TELEBIRR_NUMBER": settings.TELEBIRR_NUMBER,
        "OPENING_TIME": settings.OPENING_TIME,
        "CLOSING_TIME": settings.CLOSING_TIME,
        "CLOSED_DAYS": settings.CLOSED_DAYS,
        "MAX_BOOKING_DAYS": str(getattr(settings, 'MAX_BOOKING_DAYS', 7)),
        "SLOT_DURATION_MINUTES": str(getattr(settings, 'SLOT_DURATION_MINUTES', 30)),
    }
    
    async with async_session() as session:
        result = await session.execute(select(ShopSetting))
        rows = result.scalars().all()
    
    for row in rows:
        _cache[row.setting_key] = row.setting_value
    
    _cache_loaded = True


async def get_setting(key: str, default: Any = None) -> str:
    """Get a setting value"""
    global _cache_loaded
    if not _cache_loaded:
        await refresh_cache()
    return _cache.get(key, str(default) if default else "")


async def get_int_setting(key: str, default: int = 0) -> int:
    """Get integer setting"""
    val = await get_setting(key, str(default))
    try:
        return int(val)
    except ValueError:
        return default


async def set_setting(key: str, value: str):
    """Save setting to DB and update cache"""
    async with async_session() as session:
        result = await session.execute(
            select(ShopSetting).where(ShopSetting.setting_key == key)
        )
        row = result.scalar_one_or_none()
        
        if row:
            row.setting_value = value
        else:
            session.add(ShopSetting(setting_key=key, setting_value=value))
        
        await session.commit()
    
    global _cache
    _cache[key] = value


async def delete_setting(key: str):
    """Remove setting from DB and cache"""
    async with async_session() as session:
        result = await session.execute(
            select(ShopSetting).where(ShopSetting.setting_key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()
    
    global _cache
    _cache.pop(key, None)


async def get_all_settings() -> dict[str, str]:
    """Get all settings as dict"""
    global _cache_loaded
    if not _cache_loaded:
        await refresh_cache()
    return dict(_cache)