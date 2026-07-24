from datetime import date, timedelta, datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, cast, Date
import logging

from bot.states.booking import BookingStates, RescheduleStates
from bot.config import settings
from bot.keyboards.inline import booking_detail_keyboard, my_bookings_keyboard, services_keyboard, main_menu_keyboard
from bot.services.database import async_session
from bot.models.user import User
from bot.models.service import Service
from bot.models.booking import Booking

router = Router()
logger = logging.getLogger(__name__)
LANG_AMHARIC = "am"


def generate_time_slots():
    slots = []
    hour = 9
    minute = 0
    while hour < 18:
        slots.append(f"{hour:02d}:{minute:02d}")
        minute += 30
        if minute == 60:
            hour += 1
            minute = 0
    return slots


async def get_booked_times(booking_date_str: str) -> list:
    booking_date_val = date.fromisoformat(booking_date_str)
    
    async with async_session() as session:
        result = await session.execute(
            select(Booking.booking_time).where(
                Booking.booking_date == booking_date_val,
                Booking.status.in_(['pending_payment', 'pending_verification', 'confirmed'])
            )
        )
        booked = result.scalars().all()
        return [t.strftime("%H:%M") for t in booked]


@router.callback_query(F.data == "book_appointment")
async def show_services(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    
    if not user:
        await callback.message.edit_text("Please /start first.")
        await callback.answer()
        return
    
    lang = user.language
    await state.update_data(language=lang)
    
    async with async_session() as session:
        result = await session.execute(
            select(Service).where(Service.is_active == True).order_by(Service.service_id)
        )
        services = result.scalars().all()
    
    if lang == LANG_AMHARIC:
        text = "✂️ አገልግሎቱን ይምረጡ — የእርስዎ እርካታ በእኛ ተመርጧል።"
    else:
        text = "✂️ Select your service — choose the experience that fits your style."
    
    await callback.message.edit_text(text, reply_markup=services_keyboard(services, lang))
    await state.set_state(BookingStates.selecting_service)
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    
    if lang == LANG_AMHARIC:
        text = "🏠 ዋና ምናሌ — ወደ ሌሎች አገልግሎቶች ይመለሱ"
    else:
        text = "🏠 Main Menu — return to your options anytime."
    
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard(lang))
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("service_"), BookingStates.selecting_service)
async def select_service(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    lang = data.get('language', 'en')
    
    async with async_session() as session:
        result = await session.execute(
            select(Service).where(Service.service_id == service_id)
        )
        service = result.scalar_one_or_none()
    
    if not service:
        await callback.answer("Service not found")
        return
    
    await state.update_data(
        service_id=service.service_id,
        service_name=service.name_en,
        service_name_am=service.name_am,
        service_price=service.price,
        service_duration=service.duration
    )
    
    if lang == LANG_AMHARIC:
        text = (
            f"✨ አገልግሎት: {service.name_am}\n"
            f"💸 ዋጋ: {service.price} Birr\n\n"
            f"ቀጣይ ለመሄድ ቀን ይምረጡ።"
        )
    else:
        text = (
            f"✨ Service: {service.name_en}\n"
            f"💸 Price: {service.price} Birr\n\n"
            f"Choose your preferred date to continue."
        )
    
    continue_text = "Pick Date" if lang == 'en' else "ቀን ይምረጡ"
    back_text = "Back" if lang == 'en' else "ተመለስ"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=continue_text, callback_data="pick_date")],
        [InlineKeyboardButton(text=back_text, callback_data="back_to_services")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery, state: FSMContext):
    await show_services(callback, state)


@router.callback_query(F.data == "pick_date")
async def show_dates(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language', 'en')
    
    today = date.today()
    builder = InlineKeyboardBuilder()
    
    for i in range(settings.MAX_BOOKING_DAYS):
        d = today + timedelta(days=i)
        if d.weekday() == 6:
            continue
        day_name = d.strftime("%A")
        date_str = d.strftime("%b %d")
        builder.row(InlineKeyboardButton(
            text=f"{day_name}, {date_str}",
            callback_data=f"date_{d.isoformat()}"
        ))
    
    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="back_to_services"))
    
    if lang == LANG_AMHARIC:
        text = "📅 ቀን ይምረጡ — እንዴት በማስቀመጥ እንደሚመጡ ይመርጡ"
    else:
        text = "📅 Select your preferred date for a seamless visit."
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(BookingStates.selecting_date)
    await callback.answer()


@router.callback_query(F.data.startswith("date_"), BookingStates.selecting_date)
async def select_date(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')

    today = date.today()
    selected = date.fromisoformat(selected_date)
    if selected < today:
        if lang == LANG_AMHARIC:
            await callback.answer("ያለፈ ቀን መምረጥ አይቻልም።", show_alert=True)
        else:
            await callback.answer("Cannot select past date.", show_alert=True)
        return
    
    await state.update_data(booking_date=selected_date)
    
    booked_times = await get_booked_times(selected_date)
    all_slots = generate_time_slots()
    available_slots = [t for t in all_slots if t not in booked_times]

    if selected == today:
        now = datetime.now().strftime("%H:%M")
        available_slots = [t for t in available_slots if t > now]
    
    builder = InlineKeyboardBuilder()
    
    if not available_slots:
        if lang == LANG_AMHARIC:
            text = "😔 በዚህ ቀን ክፍት ቦታ የለም። እባክዎ ሌላ ቀን ይምረጡ።"
        else:
            text = "😔 No appointments are available on that date. Please choose another day."
    else:
        row = []
        for t in available_slots:
            row.append(InlineKeyboardButton(text=t, callback_data=f"time_{t}"))
            if len(row) == 3:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)
        
        if lang == LANG_AMHARIC:
            text = f"🕒 ቀን: {selected_date}\nሰዓት ይምረጡ — የእርስዎ ምርጥ ሰዓት ይመርጡ"
        else:
            text = f"🕒 Date: {selected_date}\nSelect a time that suits you best."
    
    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="pick_date"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(BookingStates.selecting_time)
    await callback.answer()


@router.callback_query(F.data.startswith("time_"), BookingStates.selecting_time)
async def select_time(callback: CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')
    
    await state.update_data(booking_time=selected_time)
    
    service_name = data.get('service_name_am') if lang == LANG_AMHARIC else data.get('service_name')
    service_price = data.get('service_price')
    booking_date = data.get('booking_date')
    deposit = settings.DEPOSIT_AMOUNT
    remaining = service_price - deposit
    
    if lang == LANG_AMHARIC:
        text = (
            f"✨ === የቀጠሮ ማጠቃለያ ===\n\n"
            f"አገልግሎት: {service_name}\n"
            f"💸 ዋጋ: {service_price} Birr\n"
            f"📅 ቀን: {booking_date}\n"
            f"🕒 ሰዓት: {selected_time}\n\n"
            f"💳 ቅድመ ክፍያ: {deposit} Birr\n"
            f"🏪 በቀጠሮ ቀን: {remaining} Birr\n\n"
            f"ይህን ቀጠሮ አረጋግጥ?"
        )
    else:
        text = (
            f"✨ === Booking Summary ===\n\n"
            f"Service: {service_name}\n"
            f"Price: {service_price} Birr\n"
            f"Date: {booking_date}\n"
            f"Time: {selected_time}\n\n"
            f"Deposit: {deposit} Birr\n"
            f"At the shop: {remaining} Birr\n\n"
            f"Would you like to confirm this appointment?"
        )
    
    confirm_text = "Confirm" if lang == 'en' else "አረጋግጥ"
    change_text = "Change" if lang == 'en' else "ቀይር"
    cancel_text = "Cancel" if lang == 'en' else "ሰርዝ"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=confirm_text, callback_data="confirm_booking")],
        [InlineKeyboardButton(text=change_text, callback_data="pick_date")],
        [InlineKeyboardButton(text=cancel_text, callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(BookingStates.confirming)
    await callback.answer()


@router.callback_query(F.data == "confirm_booking", BookingStates.confirming)
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language', 'en')
    user_id = callback.from_user.id
    
    service_price = data.get('service_price')
    deposit = settings.DEPOSIT_AMOUNT
    remaining = service_price - deposit
    
    try:
        async with async_session() as session:
            booking = Booking(
                user_id=user_id,
                service_id=data.get('service_id'),
                booking_date=date.fromisoformat(data.get('booking_date')),
                booking_time=datetime.strptime(data.get('booking_time'), "%H:%M").time(),
                status='pending_payment',
                deposit_amount=deposit,
                remaining_amount=remaining
            )
            session.add(booking)
            await session.commit()
            await session.refresh(booking)
            booking_id = booking.booking_id
        
        if lang == LANG_AMHARIC:
            text = (
                f"✅ === ቀጠሮ ተመዝግቧል! ===\n\n"
                f"አገልግሎት: {data.get('service_name_am')}\n"
                f"📅 ቀን: {data.get('booking_date')}\n"
                f"🕒 ሰዓት: {data.get('booking_time')}\n\n"
                f"💳 ለማረጋገጥ {deposit} Birr ቅድመ ክፍያ ያስፈልጋል\n"
                f"📸 እባክዎ የክፍያ ስክሪንሾት ያስገቡ።\n\n"
                f"🏦 CBE: {settings.CBE_ACCOUNT}\n"
                f"📱 Telebirr: {settings.TELEBIRR_NUMBER}"
            )
        else:
            text = (
                f"✅ === Booking Confirmed! ===\n\n"
                f"Service: {data.get('service_name')}\n"
                f"Date: {data.get('booking_date')}\n"
                f"Time: {data.get('booking_time')}\n\n"
                f"Please upload a {deposit} Birr deposit screenshot to secure your appointment.\n\n"
                f"🏦 CBE: {settings.CBE_ACCOUNT}\n"
                f"📱 Telebirr: {settings.TELEBIRR_NUMBER}"
            )
        
        upload_text = "Upload Screenshot" if lang == 'en' else "ስክሪንሾት አስገባ"
        back_text = "Main Menu" if lang == 'en' else "ዋና ምናሌ"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=upload_text, callback_data=f"upload_payment_{booking_id}")],
            [InlineKeyboardButton(text=back_text, callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.clear()
    
    except Exception as e:
        logger.error(f"Booking failed for user {user_id}: {e}")
        if lang == LANG_AMHARIC:
            await callback.message.answer("ስህተት ተከስቷል። እንደገና ይሞክሩ።")
        else:
            await callback.message.answer("Error occurred. Please try again.")
    
    await callback.answer()

@router.callback_query(F.data == "my_bookings")
async def show_my_bookings(callback: CallbackQuery):
    """Show customer's bookings"""
    user_id = callback.from_user.id
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
    
    if not user:
        await callback.answer("Please /start first")
        return
    
    lang = user.language
    
    async with async_session() as session:
        result = await session.execute(
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.booking_date.desc())
            .limit(10)
        )
        bookings = result.scalars().all()
    
    if not bookings:
        if lang == 'am':
            text = "📝 ምንም ቀጠሮ የለዎትም። አዲስ ቀጠሮ ለመያዝ ከላይ ይጀምሩ።"
        else:
            text = "📝 You do not have any bookings yet. Start a new reservation whenever you’re ready."
        
        back_text = "Back" if lang == 'en' else "ተመለስ"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=back_text, callback_data="back_to_main")]
        ])
    else:
        if lang == 'am':
            text = "🗓️ የእርስዎ ቀጠሮዎች — እያንዳንዱን ለመመልከት ይምረጡ"
        else:
            text = "🗓️ Your bookings — choose any visit to view more details."
        
        keyboard = my_bookings_keyboard(bookings, lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("view_booking_"))
async def view_booking(callback: CallbackQuery):
    """Show single booking details"""
    booking_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(Booking.booking_id == booking_id)
        )
        booking = result.scalar_one_or_none()
        
        user_result = await session.execute(
            select(User).where(User.user_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        
        service_result = await session.execute(
            select(Service).where(Service.service_id == booking.service_id)
        )
        service = service_result.scalar_one_or_none()
    
    if not booking:
        await callback.answer("Booking not found")
        return
    
    lang = user.language if user else 'en'
    service_name = service.name_am if lang == 'am' else service.name_en
    
    status_map = {
        'pending_payment': 'Waiting for payment' if lang == 'en' else 'ክፍያ በመጠበቅ ላይ',
        'pending_verification': 'Verifying payment' if lang == 'en' else 'ክፍያ በመረጋገጥ ላይ',
        'confirmed': 'Confirmed' if lang == 'en' else 'ተረጋግጧል',
        'completed': 'Completed' if lang == 'en' else 'ተጠናቋል',
        'declined': 'Payment issue' if lang == 'en' else 'የክፍያ ችግር',
    }
    status_text = status_map.get(booking.status, booking.status)
    
    if lang == 'am':
        text = (
            f"✨ === የቀጠሮ ዝርዝር ===\n\n"
            f"✂️ አገልግሎት: {service_name}\n"
            f"📅 ቀን: {booking.booking_date}\n"
            f"🕒 ሰዓት: {booking.booking_time}\n"
            f"🔹 ሁኔታ: {status_text}\n"
            f"💳 ቅድመ ክፍያ: {booking.deposit_amount} Birr\n"
            f"💰 ቀሪ: {booking.remaining_amount} Birr\n"
        )
    else:
        text = (
            f"✨ === Booking Details ===\n\n"
            f"Service: {service_name}\n"
            f"Date: {booking.booking_date}\n"
            f"Time: {booking.booking_time}\n"
            f"Status: {status_text}\n"
            f"Deposit: {booking.deposit_amount} Birr\n"
            f"Remaining: {booking.remaining_amount} Birr\n"
        )
    
    keyboard = booking_detail_keyboard(booking.booking_id, booking.status, lang)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("reschedule_"))
async def reschedule_start(callback: CallbackQuery, state: FSMContext):
    """Start reschedule process - show dates"""
    booking_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        user_result = await session.execute(
            select(User).where(User.user_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()
    
    lang = user.language if user else 'en'
    await state.update_data(reschedule_booking_id=booking_id, language=lang)
    
    today = date.today()
    builder = InlineKeyboardBuilder()
    
    for i in range(settings.MAX_BOOKING_DAYS):
        d = today + timedelta(days=i)
        if d.weekday() == 6:
            continue
        day_name = d.strftime("%A")
        date_str = d.strftime("%b %d")
        builder.row(InlineKeyboardButton(
            text=f"{day_name}, {date_str}",
            callback_data=f"newdate_{d.isoformat()}"
        ))
    
    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data=f"view_booking_{booking_id}"))
    
    if lang == 'am':
        text = "📅 አዲስ ቀን ይምረጡ — እርስዎ ለሚመርጡት ጊዜ ይቀይሩ"
    else:
        text = "📅 Select a new date for your appointment."
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(RescheduleStates.selecting_new_date)
    await callback.answer()


@router.callback_query(F.data.startswith("newdate_"), RescheduleStates.selecting_new_date)
async def reschedule_select_date(callback: CallbackQuery, state: FSMContext):
    """Handle new date selection for reschedule"""
    selected_date = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')
    
    await state.update_data(new_date=selected_date)
    
    booked_times = await get_booked_times(selected_date)
    all_slots = generate_time_slots()
    available_slots = [t for t in all_slots if t not in booked_times]
    
    today = date.today()
    selected = date.fromisoformat(selected_date)
    if selected == today:
        now = datetime.now().strftime("%H:%M")
        available_slots = [t for t in available_slots if t > now]
    
    builder = InlineKeyboardBuilder()
    
    if not available_slots:
        if lang == 'am':
            text = "በዚህ ቀን ክፍት ቦታ የለም። ሌላ ቀን ይምረጡ።"
        else:
            text = "No available slots. Pick another date."
    else:
        row = []
        for t in available_slots:
            row.append(InlineKeyboardButton(text=t, callback_data=f"newtime_{t}"))
            if len(row) == 3:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)
        
        if lang == 'am':
            text = f"🕒 አዲስ ቀን: {selected_date}\nአዲስ ሰዓት ይምረጡ — ለእርስዎ የሚመች ጊዜ ይምረጡ"
        else:
            text = f"🕒 New date: {selected_date}\nSelect a new time that suits you."
    
    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data=f"reschedule_{data.get('reschedule_booking_id')}"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(RescheduleStates.selecting_new_time)
    await callback.answer()


@router.callback_query(F.data.startswith("newtime_"), RescheduleStates.selecting_new_time)
async def reschedule_confirm(callback: CallbackQuery, state: FSMContext):
    """Complete reschedule"""
    new_time = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')
    booking_id = data.get('reschedule_booking_id')
    new_date = data.get('new_date')
    
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Booking).where(Booking.booking_id == booking_id)
            )
            booking = result.scalar_one_or_none()
            
            if booking:
                booking.booking_date = date.fromisoformat(new_date)
                booking.booking_time = datetime.strptime(new_time, "%H:%M").time()
                await session.commit()
        
        if lang == 'am':
            text = f"✅ === ቀጠሮ ተቀይሯል! ===\n\n📅 አዲስ ቀን: {new_date}\n🕒 አዲስ ሰዓት: {new_time}"
        else:
            text = f"✅ === Rescheduled! ===\n\n📅 New date: {new_date}\n🕒 New time: {new_time}"
        
        await callback.message.edit_text(text, reply_markup=main_menu_keyboard(lang))
        
        await callback.bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=f"Booking #{booking_id} rescheduled to {new_date} at {new_time}"
        )
        
    except Exception as e:
        logger.error(f"Reschedule failed: {e}")
        if lang == 'am':
            await callback.answer("ስህተት ተከስቷል።", show_alert=True)
        else:
            await callback.answer("Error occurred.", show_alert=True)
    
    await state.clear()
    await callback.answer()