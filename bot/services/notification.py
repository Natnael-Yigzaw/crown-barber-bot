import logging
from datetime import datetime, date, timedelta
from sqlalchemy import select

from bot.config import settings
from bot.services.database import async_session
from bot.services.settings import get_setting
from bot.models.booking import Booking
from bot.models.user import User
from bot.utils.ethiopian_time import to_ethiopian_time

logger = logging.getLogger(__name__)


async def expire_pending_bookings() -> int:
    cutoff = datetime.now() - timedelta(minutes=30)

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.status == 'pending_payment',
                Booking.created_at <= cutoff,
            )
        )
        bookings = result.scalars().all()

        for booking in bookings:
            booking.status = 'canceled'

        await session.commit()

        if bookings:
            logger.info(f"Expired {len(bookings)} pending bookings")

        return len(bookings)


async def check_and_send_reminders(bot):
    now = datetime.now()
    today = date.today()

    shop_name = await get_setting("SHOP_NAME", settings.SHOP_NAME)
    shop_address = await get_setting("SHOP_ADDRESS", settings.SHOP_ADDRESS)
    shop_phone = await get_setting("SHOP_PHONE", settings.SHOP_PHONE)

    async with async_session() as session:
        result = await session.execute(
            select(Booking, User)
            .join(User, Booking.user_id == User.user_id)
            .where(
                Booking.booking_date == today,
                Booking.status == 'confirmed'
            )
        )
        bookings = result.all()

    for booking, user in bookings:
        booking_time = booking.booking_time.strftime("%H:%M")
        booking_datetime = datetime.combine(today, booking.booking_time)
        time_diff = booking_datetime - now
        minutes_until = time_diff.total_seconds() / 60

        if 115 <= minutes_until <= 125:
            if user.language == 'am':
                eth_time = to_ethiopian_time(booking_time)
                text = (
                    f"⏰ ማሳሰቢያ\n\n"
                    f"ውድ {user.full_name},\n\n"
                    f"ከ2 ሰዓት በኋላ ቀጠሮ አለዎት!\n"
                    f"🕐 ሰዓት: {eth_time}\n\n"
                    f"📍 {shop_address}\n"
                    f"📞 {shop_phone}\n\n"
                    f"በሰዓቱ እንጠብቅዎታለን!"
                )
            else:
                text = (
                    f"⏰ Reminder\n\n"
                    f"Dear {user.full_name},\n\n"
                    f"You have an appointment in 2 hours!\n"
                    f"Time: {booking_time}\n\n"
                    f"📍 {shop_address}\n"
                    f"📞 {shop_phone}\n\n"
                    f"Please arrive on time!"
                )

            try:
                await bot.send_message(chat_id=user.user_id, text=text)
                logger.info(f"Sent 2h reminder to {user.full_name}")
            except Exception as e:
                logger.error(f"Failed to send reminder to {user.user_id}: {e}")

        elif 25 <= minutes_until <= 35:
            if user.language == 'am':
                eth_time = to_ethiopian_time(booking_time)
                text = (
                    f"🚶 አሁን መሄድ ይጀምሩ!\n\n"
                    f"{user.full_name},\n"
                    f"ቀጠሮዎ በ30 ደቂቃ ውስጥ ነው!\n"
                    f"🕐 ሰዓት: {eth_time}\n\n"
                    f"አሁኑኑ ይጓዙ!"
                )
            else:
                text = (
                    f"🚶 Time to Head Over!\n\n"
                    f"{user.full_name},\n"
                    f"Your appointment is in 30 minutes!\n"
                    f"Time: {booking_time}\n\n"
                    f"Time to make your way to the shop!"
                )

            try:
                await bot.send_message(chat_id=user.user_id, text=text)
                logger.info(f"Sent 30min reminder to {user.full_name}")
            except Exception as e:
                logger.error(f"Failed to send reminder to {user.user_id}: {e}")


async def send_daily_summary(bot):
    today = date.today()

    async with async_session() as session:
        result = await session.execute(
            select(Booking)
            .where(Booking.booking_date == today)
            .order_by(Booking.booking_time)
        )
        bookings = result.scalars().all()

    if not bookings:
        return

    confirmed = [b for b in bookings if b.status == 'confirmed']
    pending = [b for b in bookings if b.status in ['pending_payment', 'pending_verification']]
    completed = [b for b in bookings if b.status == 'completed']

    text = (
        f"=== Daily Summary ({today}) ===\n\n"
        f"Total bookings: {len(bookings)}\n"
        f"Confirmed: {len(confirmed)}\n"
        f"Pending: {len(pending)}\n"
        f"Completed: {len(completed)}\n\n"
        f"Revenue (deposits): {sum(b.deposit_amount for b in bookings)} Birr\n"
    )

    tomorrow = today + timedelta(days=1)
    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(Booking.booking_date == tomorrow)
        )
        tomorrow_bookings = result.scalars().all()

    if tomorrow_bookings:
        text += f"\nTomorrow: {len(tomorrow_bookings)} bookings scheduled"

    try:
        await bot.send_message(chat_id=settings.ADMIN_USER_ID, text=text)
        logger.info("Daily summary sent to admin")
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")