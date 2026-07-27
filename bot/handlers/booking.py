from datetime import date, timedelta, datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import logging

from bot.states.booking import BookingStates, RescheduleStates
from bot.config import settings
from bot.keyboards.inline import booking_detail_keyboard, my_bookings_keyboard, services_keyboard, main_menu_keyboard
from bot.services.database import async_session
from bot.services.settings import get_setting, get_int_setting
from bot.services.working_hours import get_day_schedule
from bot.models.user import User
from bot.models.service import Service
from bot.models.booking import Booking
from bot.models.rating import Rating
from bot.utils.ethiopian_time import format_date_am, format_ethiopian_date
from bot.utils.time_format import to_12h_str, to_ethiopian_display
from bot.utils.messages import (
    customer_booking_confirmed,
    customer_booking_details,
    customer_booking_summary,
)

router = Router()
logger = logging.getLogger(__name__)
LANG_AMHARIC = "am"


def parse_time(value: str) -> datetime.time:
    hour, minute = map(int, value.split(":"))
    return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()


def generate_time_slots(
    opening_time: str | None = None,
    closing_time: str | None = None,
    interval_minutes: int | None = None,
) -> list[str]:
    start = datetime.strptime(opening_time or "02:00", "%H:%M")
    end = datetime.strptime(closing_time or "13:00", "%H:%M")
    step = interval_minutes or 60

    slots = []
    current = start
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=step)
    return slots


def build_available_slots(
    slots: list[str],
    booked_intervals: list[tuple[datetime.time, int]],
    service_duration_minutes: int,
    opening_time: str | None = None,
    closing_time: str | None = None,
) -> list[str]:
    opening = parse_time(opening_time or "02:00")
    closing = parse_time(closing_time or "13:00")
    available = []

    for slot in slots:
        slot_start = parse_time(slot)
        slot_end = (datetime.combine(date.today(), slot_start) + timedelta(minutes=service_duration_minutes)).time()

        if slot_start < opening or slot_end > closing:
            continue

        has_conflict = False
        for booked_start, booked_duration in booked_intervals:
            booked_end = (datetime.combine(date.today(), booked_start) + timedelta(minutes=booked_duration)).time()
            if max(slot_start, booked_start) < min(slot_end, booked_end):
                has_conflict = True
                break

        if not has_conflict:
            available.append(slot)

    return available


async def get_booked_intervals(booking_date_str: str, exclude_booking_id: int | None = None,
) -> list[tuple[datetime.time, int]]:
    booking_date_val = date.fromisoformat(booking_date_str)

    async with async_session() as session:
        query = select(Booking.booking_time, Service.duration).join(
            Service, Booking.service_id == Service.service_id
        ).where(
            Booking.booking_date == booking_date_val,
            Booking.status.in_(['pending_payment', 'pending_verification', 'confirmed'])
        )

        if exclude_booking_id is not None:
            query = query.where(Booking.booking_id != exclude_booking_id)

        result = await session.execute(
            query
        )
        booked = result.all()
        return [(booking_time, int(duration)) for booking_time, duration in booked]


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
        text = "ደረጃ 1/3\nአገልግሎት ይምረጡ"
    else:
        text = "Step 1 of 3\nChoose a service"

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
            f"ደረጃ 2/3\n\n"
            f"አገልግሎት: {service.name_am}\n"
            f"ዋጋ: {service.price} Birr\n\n"
            f"ቀን ይምረጡ።"
        )
    else:
        text = (
            f"Step 2 of 3\n\n"
            f"Service: {service.name_en}\n"
            f"Price: {service.price} Birr\n\n"
            f"Pick a date to continue."
        )

    continue_text = "Pick date" if lang == 'en' else "ቀን ይምረጡ"
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

    max_days = await get_int_setting("MAX_BOOKING_DAYS", settings.MAX_BOOKING_DAYS)

    today = date.today()
    builder = InlineKeyboardBuilder()

    for i in range(max_days):
        d = today + timedelta(days=i)
        day_schedule = await get_day_schedule(d.weekday())
        if day_schedule and not day_schedule.is_working_day:
            continue
        if lang == LANG_AMHARIC:
            label = format_ethiopian_date(d)
        else:
            day_name = d.strftime("%A")
            date_str = d.strftime("%b %d")
            label = f"{day_name}, {date_str}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"date_{d.isoformat()}"))

    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="back_to_services"))

    if lang == LANG_AMHARIC:
        text = "ደረጃ 2/3\nቀን ይምረጡ"
    else:
        text = "Step 2 of 3\nPick a date"

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

    day_schedule = await get_day_schedule(selected.weekday())

    if not day_schedule or not day_schedule.is_working_day:
        if lang == LANG_AMHARIC:
            await callback.answer("በዚህ ቀን ሱቁ ዝግ ነው።", show_alert=True)
        else:
            await callback.answer("Shop is closed on this day.", show_alert=True)
        return

    await state.update_data(booking_date=selected_date)

    opening = day_schedule.opening_time.strftime("%H:%M")
    closing = day_schedule.closing_time.strftime("%H:%M")
    slot_duration = day_schedule.slot_duration or 60

    booked_intervals = await get_booked_intervals(selected_date)
    all_slots = generate_time_slots(opening, closing, slot_duration)

    if day_schedule.lunch_start and day_schedule.lunch_end:
        lunch_start_str = day_schedule.lunch_start.strftime("%H:%M")
        lunch_end_str = day_schedule.lunch_end.strftime("%H:%M")
        all_slots = [s for s in all_slots if not (lunch_start_str <= s < lunch_end_str)]

    available_slots = build_available_slots(
        all_slots,
        booked_intervals,
        service_duration_minutes=data.get('service_duration', slot_duration),
        opening_time=opening,
        closing_time=closing,
    )

    if selected == today:
        now = datetime.now().strftime("%H:%M")
        available_slots = [t for t in available_slots if t > now]

    builder = InlineKeyboardBuilder()

    if not available_slots:
        if lang == LANG_AMHARIC:
            text = "😔 በዚህ ቀን ክፍት ቦታ የለም። ሌላ ቀን ይምረጡ።"
        else:
            text = "😔 No appointments available on that date."
    else:
        row = []
        for t in available_slots:
            if lang == LANG_AMHARIC:
                label_12h = to_12h_str(t)
                eth_time = to_ethiopian_display(t)
                label = f"{label_12h}  ({eth_time})"
            else:
                label = to_12h_str(t)
            row.append(InlineKeyboardButton(text=label, callback_data=f"time_{t}"))
            if len(row) == 1:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)

        if lang == LANG_AMHARIC:
            date_obj = date.fromisoformat(selected_date)
            date_am = format_date_am(date_obj)
            text = f"ደረጃ 3/3\n{date_am}\nሰዓት ይምረጡ\n(12 ሰዓት | የኢትዮጵያ ሰዓት)"
        else:
            text = f"Step 3 of 3\nDate: {selected_date}\nPick a time"

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

    deposit = await get_int_setting("DEPOSIT_AMOUNT", settings.DEPOSIT_AMOUNT)
    remaining = service_price - deposit

    text = customer_booking_summary(
        service_name=service_name,
        service_price=service_price,
        booking_date=booking_date,
        booking_time=selected_time,
        deposit=deposit,
        remaining=remaining,
        lang=lang,
    )

    confirm_text = "Confirm booking" if lang == 'en' else "ቀጠሮ አረጋግጥ"
    change_text = "Change time" if lang == 'en' else "ጊዜ ቀይር"
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
    deposit = await get_int_setting("DEPOSIT_AMOUNT", settings.DEPOSIT_AMOUNT)
    remaining = service_price - deposit
    cbe = await get_setting("CBE_ACCOUNT", settings.CBE_ACCOUNT)
    telebirr = await get_setting("TELEBIRR_NUMBER", settings.TELEBIRR_NUMBER)

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

        text = customer_booking_confirmed(
            service_name=data.get('service_name_am') if lang == LANG_AMHARIC else data.get('service_name'),
            booking_date=data.get('booking_date'),
            booking_time=data.get('booking_time'),
            deposit=deposit,
            cbe=cbe,
            telebirr=telebirr,
            lang=lang,
        )

        upload_text = "Upload payment screenshot" if lang == 'en' else "የክፍያ ስክሪንሾት ላክ"
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
            text = "📝 ምንም ቀጠሮ የለዎትም።"
        else:
            text = "📝 You have no bookings yet."

        back_text = "Back" if lang == 'en' else "ተመለስ"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=back_text, callback_data="back_to_main")]
        ])
    else:
        if lang == 'am':
            text = "🗓️ የእርስዎ ቀጠሮዎች"
        else:
            text = "🗓️ Your bookings"

        keyboard = my_bookings_keyboard(bookings, lang)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("view_booking_"))
async def view_booking(callback: CallbackQuery):
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Booking).where(
                Booking.booking_id == booking_id,
                Booking.user_id == callback.from_user.id,
            )
        )
        booking = result.scalar_one_or_none()

        if not booking:
            await callback.answer("Booking not found")
            return

        user_result = await session.execute(
            select(User).where(User.user_id == callback.from_user.id)
        )
        user = user_result.scalar_one_or_none()

        service_result = await session.execute(
            select(Service).where(Service.service_id == booking.service_id)
        )
        service = service_result.scalar_one_or_none()

    lang = user.language if user else 'en'
    if service:
        service_name = service.name_am if lang == 'am' else service.name_en
    else:
        service_name = "N/A"

    text = customer_booking_details(booking, service_name, lang)

    async with async_session() as session:
        rating_result = await session.execute(
            select(Rating).where(Rating.booking_id == booking_id)
        )
        existing_rating = rating_result.scalar_one_or_none()

    if existing_rating:
        stars = "⭐" * existing_rating.rating
        if lang == 'am':
            text += f"\n\n⭐ ደረጃ: {stars}"
            if existing_rating.review:
                text += f"\n💬 አስተያየት: {existing_rating.review}"
        else:
            text += f"\n\n⭐ Rating: {stars}"
            if existing_rating.review:
                text += f"\n💬 Review: {existing_rating.review}"

    keyboard = booking_detail_keyboard(booking.booking_id, booking.status, lang)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("reschedule_"))
async def reschedule_start(callback: CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(Booking, User, Service)
            .join(User, Booking.user_id == User.user_id)
            .join(Service, Booking.service_id == Service.service_id)
            .where(
                Booking.booking_id == booking_id,
                Booking.user_id == callback.from_user.id,
                Booking.status.in_(['pending_payment', 'pending_verification', 'confirmed'])
            )
        )
        row = result.one_or_none()

    if not row:
        await callback.answer("Booking not found", show_alert=True)
        return

    booking, user, service = row
    lang = user.language if user else 'en'
    await state.update_data(
        reschedule_booking_id=booking_id,
        service_duration=service.duration,
        language=lang,
    )

    max_days = await get_int_setting("MAX_BOOKING_DAYS", settings.MAX_BOOKING_DAYS)

    today = date.today()
    builder = InlineKeyboardBuilder()

    for i in range(max_days):
        d = today + timedelta(days=i)
        day_schedule = await get_day_schedule(d.weekday())
        if day_schedule and not day_schedule.is_working_day:
            continue
        if lang == LANG_AMHARIC:
            label = format_ethiopian_date(d)
        else:
            day_name = d.strftime("%A")
            date_str = d.strftime("%b %d")
            label = f"{day_name}, {date_str}"
        builder.row(InlineKeyboardButton(text=label, callback_data=f"newdate_{d.isoformat()}"))

    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data=f"view_booking_{booking_id}"))

    if lang == 'am':
        text = "📅 አዲስ ቀን ይምረጡ"
    else:
        text = "📅 Select a new date"

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(RescheduleStates.selecting_new_date)
    await callback.answer()


@router.callback_query(F.data.startswith("newdate_"), RescheduleStates.selecting_new_date)
async def reschedule_select_date(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')

    await state.update_data(new_date=selected_date)

    day_schedule = await get_day_schedule(date.fromisoformat(selected_date).weekday())

    if not day_schedule or not day_schedule.is_working_day:
        if lang == 'am':
            await callback.answer("በዚህ ቀን ሱቁ ዝግ ነው።", show_alert=True)
        else:
            await callback.answer("Shop is closed on this day.", show_alert=True)
        return

    opening = day_schedule.opening_time.strftime("%H:%M")
    closing = day_schedule.closing_time.strftime("%H:%M")
    slot_duration = day_schedule.slot_duration or 60

    booked_intervals = await get_booked_intervals(
        selected_date,
        exclude_booking_id=data.get('reschedule_booking_id'),
    )
    all_slots = generate_time_slots(opening, closing, slot_duration)

    if day_schedule.lunch_start and day_schedule.lunch_end:
        lunch_start_str = day_schedule.lunch_start.strftime("%H:%M")
        lunch_end_str = day_schedule.lunch_end.strftime("%H:%M")
        all_slots = [s for s in all_slots if not (lunch_start_str <= s < lunch_end_str)]

    available_slots = build_available_slots(
        all_slots,
        booked_intervals,
        service_duration_minutes=data.get('service_duration', slot_duration),
        opening_time=opening,
        closing_time=closing,
    )

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
            if lang == LANG_AMHARIC:
                label_12h = to_12h_str(t)
                eth_time = to_ethiopian_display(t)
                label = f"{label_12h}  ({eth_time})"
            else:
                label = to_12h_str(t)
            row.append(InlineKeyboardButton(text=label, callback_data=f"newtime_{t}"))
            if len(row) == 1:
                builder.row(*row)
                row = []
        if row:
            builder.row(*row)

        if lang == 'am':
            date_obj = date.fromisoformat(selected_date)
            date_am = format_date_am(date_obj)
            text = f"Change appointment\n{date_am}\nአዲስ ሰዓት ይምረጡ\n(12 ሰዓት | የኢትዮጵያ ሰዓት)"
        else:
            text = f"Change appointment\nNew date: {selected_date}\nPick a new time"

    back_text = "Back" if lang == 'en' else "ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data=f"reschedule_{data.get('reschedule_booking_id')}"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await state.set_state(RescheduleStates.selecting_new_time)
    await callback.answer()


@router.callback_query(F.data.startswith("newtime_"), RescheduleStates.selecting_new_time)
async def reschedule_confirm(callback: CallbackQuery, state: FSMContext):
    new_time = callback.data.split("_")[1]
    data = await state.get_data()
    lang = data.get('language', 'en')
    booking_id = data.get('reschedule_booking_id')
    new_date = data.get('new_date')

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Booking).where(
                    Booking.booking_id == booking_id,
                    Booking.user_id == callback.from_user.id,
                    Booking.status.in_(['pending_payment', 'pending_verification', 'confirmed'])
                )
            )
            booking = result.scalar_one_or_none()

            if not booking:
                await callback.answer("Booking not found", show_alert=True)
                return

            booking.booking_date = date.fromisoformat(new_date)
            booking.booking_time = datetime.strptime(new_time, "%H:%M").time()
            await session.commit()

        if lang == 'am':
            new_date_obj = date.fromisoformat(new_date)
            eth_time = to_ethiopian_display(new_time)
            eth_date = format_ethiopian_date(new_date_obj)

            text = (
                f"ቀጠሮ ተቀይሯል\n\n"
                f"አዲስ ቀን: {eth_date}\n"
                f"አዲስ ሰዓት: {eth_time}"
            )
        else:
            time_12h = to_12h_str(new_time)
            eth_time = to_ethiopian_display(new_time)
            text = f"Appointment changed\n\nNew date: {new_date}\nNew time: {time_12h} (Eth: {eth_time})"

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
