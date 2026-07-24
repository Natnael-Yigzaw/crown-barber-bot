import logging
from aiogram import Bot
from bot.config import settings

logger = logging.getLogger(__name__)


async def save_screenshot_to_channel(bot: Bot, file_id: str, booking_id: int, user_name: str) -> str:
    """
    Save payment screenshot to Telegram channel.
    Returns the message link that admin can click to view.
    """
    try:
        caption = f"Payment for Booking #{booking_id}\nCustomer: {user_name}"
        
        msg = await bot.send_photo(
            chat_id=settings.PAYMENTS_CHANNEL_ID,
            photo=file_id,
            caption=caption
        )
        
        channel_id = str(settings.PAYMENTS_CHANNEL_ID).replace('-100', '')
        link = f"https://t.me/c/{channel_id}/{msg.message_id}"
        
        logger.info(f"Screenshot saved to channel: {link}")
        return link
        
    except Exception as e:
        logger.error(f"Failed to save screenshot to channel: {e}")
        raise