import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.services.database import check_connection, engine
from bot.services.notification import check_and_send_reminders, send_daily_summary, expire_pending_bookings
from bot.services.settings import refresh_cache
from bot.handlers.start import router as start_router
from bot.handlers.booking import router as booking_router
from bot.handlers.payment import router as payment_router
from bot.handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def main():
    if not await check_connection():
        logger.error("Database connection failed!")
        sys.exit(1)
    
    logger.info("Database connected")
    
    await refresh_cache()
    logger.info("Settings cache loaded")
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=MemoryStorage())
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Open the main menu"),
    ])
    
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open the main menu"),
            BotCommand(command="admin", description="Admin panel"),
        ],
        scope=BotCommandScopeChat(chat_id=settings.ADMIN_USER_ID)
    )
    
    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    
    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(
        check_and_send_reminders,
        'interval',
        minutes=5,
        args=[bot],
        id='reminders'
    )
    
    scheduler.add_job(
        expire_pending_bookings,
        'interval',
        minutes=10,
        id='expire_pending_bookings'
    )

    scheduler.add_job(
        send_daily_summary,
        'cron',
        hour=20,
        minute=0,
        args=[bot],
        id='daily_summary'
    )
    
    scheduler.start()
    logger.info("Scheduler started")
    logger.info("Bot is running...")
    
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot stopped cleanly")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")