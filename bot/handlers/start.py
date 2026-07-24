from aiogram import Router, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import re

from bot.config import settings
from bot.states.registration import RegistrationStates
from bot.keyboards.inline import language_keyboard, main_menu_keyboard
from bot.services.database import async_session
from bot.models.user import User

router = Router()

LANG_AMHARIC = "am"
LANG_ENGLISH = "en"
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 100


def get_brand_welcome_text(lang: str, full_name: str | None = None) -> str:
    if lang == LANG_AMHARIC:
        if full_name:
            return (
                f"✨ እንኳን ደህና መጡ {full_name}!\n\n"
                f"ወደ {settings.SHOP_NAME} በደህና መጡ። የፕሪሚየም የጸጉር አገልግሎት እዚህ ይጀምራል።"
            )
        return (
            f"✨ ወደ {settings.SHOP_NAME} እንኳን በደህና መጡ\n\n"
            "የፕሪሚየም የጸጉር እንክብካቤ በአንድ እንቅስቃሴ ይቀርብሎታል።"
        )

    if full_name:
        return (
            f"✨ Welcome back {full_name}!\n\n"
            f"You’re in the right place for a polished experience at {settings.SHOP_NAME}."
        )

    return (
        f"✨ Welcome to {settings.SHOP_NAME}\n\n"
        "Your premium grooming experience starts here — book appointments, manage your visits, and enjoy a seamless service."
    )

def validate_ethiopian_phone(phone: str) -> bool:
    """Validate Ethiopian phone number format: 09XXXXXXXX or +2519XXXXXXXX"""
    pattern = r'^(0[97]\d{8}|\+251[97]\d{8})$'
    return bool(re.match(pattern, phone))

def sanitize_name(name: str) -> str:
    """Remove unwanted characters from name"""
    return re.sub(r'[<>{}]', '', name).strip()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Check if admin
    if user_id == settings.ADMIN_USER_ID:
        from bot.keyboards.inline import admin_menu_keyboard
        await message.answer(
            f"🛡️ Welcome Admin!\n\n{settings.SHOP_NAME} Dashboard",
            reply_markup=admin_menu_keyboard()
        )
        return
    
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()
    except Exception as e:
        await message.answer("An error occurred. Please try again later.")
        return
    
    if user:
        text = get_brand_welcome_text(user.language, user.full_name)
        await message.answer(text, reply_markup=main_menu_keyboard(user.language))
    else:
        await message.answer(
            f"{get_brand_welcome_text(LANG_ENGLISH)}\n\n"
            "🌍 ቋንቋ ይምረጡ / Choose your language:",
            reply_markup=language_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_language)


@router.callback_query(F.data.in_(["lang_am", "lang_en"]), RegistrationStates.waiting_for_language)
async def process_language(callback: CallbackQuery, state: FSMContext):
    lang = LANG_AMHARIC if callback.data == "lang_am" else LANG_ENGLISH
    await state.update_data(language=lang)
    
    if lang == LANG_AMHARIC:
        await callback.message.edit_text("🪪 ስምዎን ያስገቡ። ለምሳሌ: አበበ አለም")
    else:
        await callback.message.edit_text("🪪 Please enter your full name so we can personalize your experience.")
    
    await state.set_state(RegistrationStates.waiting_for_name)
    await callback.answer()


@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    full_name = sanitize_name(message.text.strip())
    
    if len(full_name) < MIN_NAME_LENGTH or len(full_name) > MAX_NAME_LENGTH:
        data = await state.get_data()
        lang = data.get('language', LANG_ENGLISH)
        if lang == LANG_AMHARIC:
            await message.answer(f"እባክዎ ከ{MIN_NAME_LENGTH} እስከ {MAX_NAME_LENGTH} ፊደላት ያስገቡ:")
        else:
            await message.answer(f"Please enter {MIN_NAME_LENGTH}-{MAX_NAME_LENGTH} characters:")
        return
    
    await state.update_data(full_name=full_name)
    
    data = await state.get_data()
    lang = data.get('language', LANG_ENGLISH)
    
    if lang == LANG_AMHARIC:
        await message.answer("📱 ስልክ ቁጥርዎን ያስገቡ (ለምሳሌ: 0911223344):")
    else:
        await message.answer("📱 Please share your phone number so we can confirm your booking (e.g., 0911223344):")
    
    await state.set_state(RegistrationStates.waiting_for_phone)


@router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    data = await state.get_data()
    lang = data.get('language', LANG_ENGLISH)
    
    if not validate_ethiopian_phone(phone):
        if lang == LANG_AMHARIC:
            await message.answer("እባክዎ ትክክለኛ ስልክ ቁጥር ያስገቡ (0911223344 ወይም +251911223344):")
        else:
            await message.answer("Please enter a valid phone number (0911223344 or +251911223344):")
        return
    
    full_name = data.get('full_name')
    if not full_name:
        await message.answer("Session expired. Please /start again.")
        await state.clear()
        return
    
    user_id = message.from_user.id
    
    try:
        async with async_session() as session:
            existing = await session.execute(
                select(User).where(User.phone_number == phone)
            )
            if existing.scalar_one_or_none():
                if lang == LANG_AMHARIC:
                    await message.answer("ይህ ስልክ ቁጥር አስቀድሞ ተመዝግቧል። ሌላ ቁጥር ያስገቡ:")
                else:
                    await message.answer("This phone number is already registered. Please use a different number:")
                return
            
            new_user = User(
                user_id=user_id,
                full_name=full_name,
                phone_number=phone,
                language=lang
            )
            session.add(new_user)
            await session.commit()
    
    except Exception as e:
        if lang == LANG_AMHARIC:
            await message.answer("የቴክኒክ ችግር ተከስቷል። እባክዎ እንደገና ይሞክሩ።")
        else:
            await message.answer("A technical error occurred. Please try again.")
        return
    
    if lang == LANG_AMHARIC:
        text = f"✅ ምዝገባ ተጠናቋል! {full_name} በምርጥ የጸጉር ልምድ እንኳን ደህና መጡ!"
    else:
        text = f"✅ Registration complete! Welcome {full_name} — your premium experience is ready."
    
    await message.answer(text, reply_markup=main_menu_keyboard(lang))
    await state.clear()
    
    try:
        await message.bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=f"New Customer!\n\nName: {full_name}\nPhone: {phone}\nLanguage: {lang}"
        )
    except Exception:
        pass

@router.callback_query(F.data == "change_language")
async def change_language(callback: CallbackQuery, state: FSMContext):
    """Allow existing user to switch language"""
    await callback.message.edit_text(
        "🌍 ቋንቋ ይምረጡ / Choose your language:",
        reply_markup=language_keyboard()
    )
    await state.set_state(RegistrationStates.changing_language)
    await callback.answer()


@router.callback_query(F.data.in_(["lang_am", "lang_en"]), RegistrationStates.changing_language)
async def update_language(callback: CallbackQuery, state: FSMContext):
    """Update language for existing user without re-registration"""
    lang = "am" if callback.data == "lang_am" else "en"
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.language = lang
            await session.commit()
    
    await state.clear()
    
    if lang == 'am':
        text = "ቋንቋዎ ወደ አማርኛ ተቀይሯል።"
    else:
        text = "Language changed to English."
    
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(lang))
    await callback.answer()


@router.callback_query(F.data == "about")
async def about_shop(callback: CallbackQuery):
    """Show shop information"""
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    if lang == 'am':
        text = (
            f"✨ {settings.SHOP_NAME}\n\n"
            f"📍 አድራሻ: {settings.SHOP_ADDRESS}\n"
            f"📞 ስልክ: {settings.SHOP_PHONE}\n"
            f"🕐 ሰዓታት: {settings.OPENING_TIME} - {settings.CLOSING_TIME}\n"
            f"📅 እሁድ: እረፍት\n\n"
            "እንደ አንድ የበለጠ ቅድመ-ተሞክሮ በተለይ የጸጉር አገልግሎት ይቀርብሎታል።\n"
            "ለቀጠሮ እና ለማስተናገድ አሁን ይጀምሩ።"
        )
    else:
        text = (
            f"✨ {settings.SHOP_NAME}\n\n"
            f"📍 Address: {settings.SHOP_ADDRESS}\n"
            f"📞 Phone: {settings.SHOP_PHONE}\n"
            f"🕐 Hours: {settings.OPENING_TIME} - {settings.CLOSING_TIME}\n"
            f"📅 Sunday: Closed\n\n"
            "A premium grooming experience designed for comfort, precision, and style.\n"
            "Book your visit and enjoy a refined service from start to finish."
        )
    
    back_text = "Back" if lang == 'en' else "ተመለስ"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_text, callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()