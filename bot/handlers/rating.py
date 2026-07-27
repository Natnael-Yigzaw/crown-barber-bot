import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from bot.states.rating import RatingStates
from bot.services.database import async_session
from bot.models.booking import Booking
from bot.models.rating import Rating
from bot.models.user import User

router = Router()
logger = logging.getLogger(__name__)


def rating_keyboard(booking_id: int):
    """Create star rating keyboard - one star per row"""
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    keyboard = []
    for i, star in enumerate(stars, 1):
        keyboard.append([InlineKeyboardButton(text=star, callback_data=f"rate_{booking_id}_{i}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def skip_review_keyboard(booking_id: int, lang: str = 'en'):
    """Skip or leave review"""
    skip_text = "Skip" if lang == 'en' else "መዝለል"
    review_text = "Leave Review" if lang == 'en' else "አስተያየት መስጠት"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=review_text, callback_data=f"review_{booking_id}")],
        [InlineKeyboardButton(text=skip_text, callback_data=f"skip_review_{booking_id}")]
    ])


@router.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: CallbackQuery):
    """Save rating when customer taps stars"""
    parts = callback.data.split("_")
    booking_id = int(parts[1])
    rating_value = int(parts[2])
    user_id = callback.from_user.id
    
    # Get user language
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    # Save rating
    try:
        async with async_session() as session:
            rating = Rating(
                booking_id=booking_id,
                user_id=user_id,
                rating=rating_value
            )
            session.add(rating)
            await session.commit()
    except Exception as e:
        logger.error(f"Rating save failed: {e}")
        await callback.answer("Already rated or error occurred.", show_alert=True)
        return
    
    if lang == 'am':
        text = f"✅ አመሰግናለሁ! {rating_value} ⭐ ሰጥተዋል።\n\nአስተያየት መስጠት ይፈልጋሉ?"
    else:
        text = f"✅ Thank you! You rated {rating_value} ⭐\n\nWould you like to leave a review?"
    
    await callback.message.edit_text(text, reply_markup=skip_review_keyboard(booking_id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("review_"))
async def start_review(callback: CallbackQuery, state: FSMContext):
    """Ask customer to type a review"""
    booking_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    await state.update_data(review_booking_id=booking_id)
    
    if lang == 'am':
        await callback.message.edit_text("📝 እባክዎ አስተያየትዎን ይጻፉ (ወይም /skip ለማለፍ):")
    else:
        await callback.message.edit_text("📝 Please write your review (or /skip to pass):")
    
    await state.set_state(RatingStates.waiting_for_review)
    await callback.answer()


@router.message(RatingStates.waiting_for_review, F.text)
async def save_review(message: Message, state: FSMContext):
    """Save text review"""
    if message.text == "/skip":
        await state.clear()
        await message.answer("👍 Thank you for your rating!")
        return
    
    data = await state.get_data()
    booking_id = data.get('review_booking_id')
    review_text = message.text.strip()
    
    async with async_session() as session:
        result = await session.execute(
            select(Rating).where(Rating.booking_id == booking_id)
        )
        rating = result.scalar_one_or_none()
        
        if rating:
            rating.review = review_text
            await session.commit()
    
    await state.clear()
    
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.user_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    if lang == 'am':
        await message.answer("✅ አስተያየትዎ ተቀብሏል። አመሰግናለሁ!")
    else:
        await message.answer("✅ Review received. Thank you!")


@router.callback_query(F.data.startswith("skip_review_"))
async def skip_review(callback: CallbackQuery):
    """Skip text review"""
    user_id = callback.from_user.id
    
    async with async_session() as session:
        user_result = await session.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    if lang == 'am':
        await callback.message.edit_text("👍 ስለ እርስዎ አስተያየት አመሰግናለሁ!")
    else:
        await callback.message.edit_text("👍 Thanks for your rating!")
    
    await callback.answer()