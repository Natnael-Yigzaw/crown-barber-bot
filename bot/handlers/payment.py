import os
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
from bot.models.user import User
from bot.models.booking import Booking
from bot.models.payment import Payment

router = Router()
logger = logging.getLogger(__name__)

ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
MAX_SIZE = 5 * 1024 * 1024


@router.callback_query(F.data.startswith("upload_payment_"))
async def request_screenshot(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    await state.update_data(booking_id=booking_id, language=lang)
    
    if lang == 'am':
        text = "📸 እባክዎ የክፍያ ስክሪንሾት ፎቶ ያስገቡ (ከ5MB በታች፣ JPG/PNG/WebP) — እንደሚረጋገጥ በአስተዳዳሪ ላይ ይታያል።"
    else:
        text = "📸 Please upload your payment screenshot (under 5MB, JPG/PNG/WebP) so we can verify your booking."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Back" if lang == 'en' else "ተመለስ",
            callback_data="back_to_main"
        )]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(PaymentStates.waiting_for_screenshot)
    await callback.answer()


@router.message(PaymentStates.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    """Receive payment screenshot, save to Telegram channel"""
    data = await state.get_data()
    booking_id = data.get('booking_id')
    lang = data.get('language', 'en')
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    photo = message.photo[-1]
    file_id = photo.file_id
    
    if photo.file_size > MAX_SIZE:
        if lang == 'am':
            await message.answer("⚠️ ፋይሉ በጣም ትልቅ ነው። እባክዎ ከ5MB በታች ያስገቡ።")
        else:
            await message.answer("⚠️ The file is too large. Please upload an image under 5MB.")
        return
    
    try:
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
                amount=settings.DEPOSIT_AMOUNT,
                screenshot_path=screenshot_link,
                status='pending'
            )
            session.add(payment)
            
            result = await session.execute(
                select(Booking).where(Booking.booking_id == booking_id)
            )
            booking = result.scalar_one_or_none()
            if booking:
                booking.status = 'pending_verification'
            
            await session.commit()
        
        if lang == 'am':
            text = (
                "✅ === ክፍያ ተቀብሏል! ===\n\n"
                "ስክሪንሾትዎ ተልኳል።\n"
                "አስተዳዳሪ ሲያረጋግጥ ማሳወቂያ ይደርስዎታል።"
            )
        else:
            text = (
                "✅ === Payment Received! ===\n\n"
                "Your screenshot has been sent successfully.\n"
                "You will be notified as soon as the admin verifies it."
            )
        
        await message.answer(text, reply_markup=main_menu_keyboard(lang))
        
        await message.bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=(
                f"New Payment Uploaded\n\n"
                f"Booking: #{booking_id}\n"
                f"Customer: {user_name}\n"
                f"Amount: {settings.DEPOSIT_AMOUNT} Birr\n\n"
                f"View Screenshot: {screenshot_link}\n\n"
                f"Use /admin to verify"
            )
        )
        
    except Exception as e:
        logger.error(f"Payment save failed: {e}")
        if lang == 'am':
            await message.answer("⚠️ ስህተት ተከስቷል። እባክዎ እንደገና ይሞክሩ።")
        else:
            await message.answer("⚠️ Something went wrong. Please try again in a moment.")
    
    await state.clear()


@router.message(PaymentStates.waiting_for_screenshot)
async def invalid_upload(message: Message):
    """Handle non-photo uploads"""
    await message.answer("📸 Please upload a valid photo in JPG, PNG, or WebP format.")