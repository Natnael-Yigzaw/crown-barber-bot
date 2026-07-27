import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from bot.config import settings
from bot.states.payment import PaymentStates
from bot.keyboards.inline import main_menu_keyboard
from bot.services.database import async_session
from bot.services.payment_storage import save_screenshot_to_channel
from bot.services.settings import get_int_setting, get_setting
from bot.models.user import User
from bot.models.booking import Booking
from bot.models.payment import Payment
from bot.utils.messages import booking_time_label, payment_instructions

router = Router()
logger = logging.getLogger(__name__)

MAX_SIZE = 5 * 1024 * 1024


@router.callback_query(F.data.startswith("upload_payment_"))
async def request_screenshot(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()

        booking_result = await session.execute(
            select(Booking).where(
                Booking.booking_id == booking_id,
                Booking.user_id == user_id,
                Booking.status.in_(['pending_payment', 'pending_verification'])
            )
        )
        booking = booking_result.scalar_one_or_none()

    lang = user.language if user else 'en'
    if not booking:
        await callback.answer("Booking not found", show_alert=True)
        return

    await state.update_data(booking_id=booking_id, language=lang)

    deposit = await get_int_setting("DEPOSIT_AMOUNT", settings.DEPOSIT_AMOUNT)
    cbe = await get_setting("CBE_ACCOUNT", settings.CBE_ACCOUNT)
    telebirr = await get_setting("TELEBIRR_NUMBER", settings.TELEBIRR_NUMBER)

    text = payment_instructions(booking, deposit, cbe, telebirr, lang)

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Back" if lang == 'en' else "🔙 ተመለስ",
                callback_data="back_to_main"
            )]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(PaymentStates.waiting_for_screenshot)
    await callback.answer()


@router.message(PaymentStates.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get('booking_id')
    lang = data.get('language', 'en')
    user_id = message.from_user.id
    user_name = message.from_user.full_name

    photo = message.photo[-1]
    file_id = photo.file_id

    if photo.file_size > MAX_SIZE:
        if lang == 'am':
            await message.answer("⚠️ ፋይሉ በጣም ትልቅ ነው። ከ5MB በታች ያስገቡ።")
        else:
            await message.answer("⚠️ File too large. Please upload under 5MB.")
        return

    deposit = await get_int_setting("DEPOSIT_AMOUNT", settings.DEPOSIT_AMOUNT)

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.booking_id == booking_id,
                    Booking.user_id == user_id,
                    Booking.status.in_(['pending_payment', 'pending_verification'])
                )
            )
            booking = result.scalar_one_or_none()

        if not booking:
            await state.clear()
            if lang == 'am':
                await message.answer("ቀጠሮው አልተገኘም።")
            else:
                await message.answer("Booking not found.")
            return

        screenshot_link = await save_screenshot_to_channel(
            bot=message.bot,
            file_id=file_id,
            booking_id=booking_id,
            user_name=user_name
        )

        async with async_session() as session:
            payment = Payment(
                booking_id=booking_id,
                user_id=user_id,
                amount=deposit,
                screenshot_path=screenshot_link,
                status='pending'
            )
            session.add(payment)

            result = await session.execute(
                select(Booking).where(
                    Booking.booking_id == booking_id,
                    Booking.user_id == user_id,
                )
            )
            booking = result.scalar_one_or_none()
            if booking:
                booking.status = 'pending_verification'

            await session.commit()

        if lang == 'am':
            text = "✅ ክፍያ ተቀብሏል! አስተዳዳሪ ሲያረጋግጥ ያሳውቅዎታል።"
        else:
            text = "✅ Payment received! You'll be notified when admin verifies it."

        await message.answer(text, reply_markup=main_menu_keyboard(lang))

        await message.bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=(
                f"Payment uploaded\n\n"
                f"Booking: #{booking_id}\n"
                f"Customer: {user_name}\n"
                f"Appointment: {booking.booking_date} at {booking_time_label(booking.booking_time)}\n"
                f"Amount: {deposit} Birr\n\n"
                f"View: {screenshot_link}\n\n"
                f"Use /admin to verify"
            )
        )

    except Exception as e:
        logger.error(f"Payment save failed: {e}")
        if lang == 'am':
            await message.answer("⚠️ ስህተት ተከስቷል። እንደገና ይሞክሩ።")
        else:
            await message.answer("⚠️ Something went wrong. Please try again.")

    await state.clear()


@router.message(PaymentStates.waiting_for_screenshot)
async def invalid_upload(message: Message):
    await message.answer("📸 Please upload a valid photo (JPG, PNG, or WebP).")
