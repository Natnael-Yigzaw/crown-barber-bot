import logging
from datetime import datetime, date, time as dt_time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from bot.config import settings
from bot.keyboards.inline import admin_back_keyboard, admin_menu_keyboard
from bot.states.admin import AdminStates
from bot.services.database import async_session
from bot.services.settings import get_setting, get_int_setting, set_setting, delete_setting, get_all_settings, refresh_cache
from bot.services.working_hours import get_day_schedule, get_all_schedules, update_day_schedule, format_time, format_working_hours_display, to_ethiopian_time_str, DAY_NAMES_EN, DAY_NAMES_AM
from bot.models.user import User
from bot.models.booking import Booking
from bot.models.payment import Payment
from bot.models.service import Service

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_USER_ID


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Unauthorized.")
        return

    shop_name = await get_setting("SHOP_NAME", settings.SHOP_NAME)
    await message.answer(
        f"🛡️ Admin Dashboard\n\n{shop_name}",
        reply_markup=admin_menu_keyboard()
    )


@router.callback_query(F.data == "admin_pending")
async def show_pending_payments(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(Payment, Booking, User)
            .join(Booking, Payment.booking_id == Booking.booking_id)
            .join(User, Payment.user_id == User.user_id)
            .where(Payment.status == 'pending')
            .order_by(Payment.created_at.desc())
        )
        pending = result.all()

    if not pending:
        await callback.message.answer("No pending payments.", reply_markup=admin_back_keyboard())
        await callback.answer()
        return

    count = 0
    for payment, booking, user in pending:
        service_name = "N/A"
        if booking.service_id:
            service_result = await session.execute(
                select(Service).where(Service.service_id == booking.service_id)
            )
            service = service_result.scalar_one_or_none()
            if service:
                service_name = service.name_en

        text = (
            f"ID: {booking.booking_id}\n"
            f"Customer: {user.full_name}\n"
            f"Phone: {user.phone_number}\n"
            f"Service: {service_name}\n"
            f"Date: {booking.booking_date}\n"
            f"Time: {booking.booking_time}\n"
            f"Amount: {payment.amount} Birr\n"
        )

        buttons = [
            [
                InlineKeyboardButton(text="Approve", callback_data=f"approve_{payment.payment_id}"),
                InlineKeyboardButton(text="Decline", callback_data=f"decline_{payment.payment_id}")
            ],
            [InlineKeyboardButton(text="Chat", callback_data=f"chat_{booking.booking_id}")]
        ]

        if payment.screenshot_path and payment.screenshot_path.startswith("http"):
            buttons.insert(0, [InlineKeyboardButton(text="View Screenshot", url=payment.screenshot_path)])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        if payment.screenshot_path and not payment.screenshot_path.startswith("http"):
            try:
                with open(payment.screenshot_path, 'rb') as photo:
                    await callback.message.answer_photo(photo=photo, caption=text, reply_markup=keyboard)
            except Exception:
                await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.answer(text, reply_markup=keyboard)

        count += 1

    await callback.answer(f"Found {count} pending")


@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    payment_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(select(Payment).where(Payment.payment_id == payment_id))
        payment = result.scalar_one_or_none()

        if payment and payment.status == 'pending':
            payment.status = 'verified'
            payment.verified_at = datetime.now()

            booking_result = await session.execute(
                select(Booking).where(Booking.booking_id == payment.booking_id)
            )
            booking = booking_result.scalar_one_or_none()
            if booking:
                booking.status = 'confirmed'

            await session.commit()

            try:
                await callback.bot.send_message(
                    chat_id=payment.user_id,
                    text="✅ Payment Verified! Your booking is now confirmed. See you soon!"
                )
            except Exception:
                pass

    await callback.answer("Approved!")
    await callback.message.reply(f"Payment #{payment_id} approved.")


@router.callback_query(F.data.startswith("decline_"))
async def decline_payment_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    payment_id = int(callback.data.split("_")[1])
    await state.update_data(decline_payment_id=payment_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Screenshot unclear", callback_data="reason_unclear")],
        [InlineKeyboardButton(text="Wrong amount", callback_data="reason_wrong_amount")],
        [InlineKeyboardButton(text="Payment not received", callback_data="reason_not_received")],
        [InlineKeyboardButton(text="Other", callback_data="reason_other")],
        [InlineKeyboardButton(text="Back", callback_data="admin_pending")]
    ])

    await callback.message.reply("Select decline reason:", reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_for_decline_reason)
    await callback.answer()


@router.callback_query(F.data.startswith("reason_"), AdminStates.waiting_for_decline_reason)
async def decline_payment_finish(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    reason_map = {
        "reason_unclear": "Screenshot not clear",
        "reason_wrong_amount": "Wrong amount paid",
        "reason_not_received": "Payment not received",
        "reason_other": "Other issue"
    }

    reason = reason_map.get(callback.data, "Not specified")
    data = await state.get_data()
    payment_id = data.get('decline_payment_id')

    async with async_session() as session:
        result = await session.execute(select(Payment).where(Payment.payment_id == payment_id))
        payment = result.scalar_one_or_none()

        if payment and payment.status == 'pending':
            payment.status = 'declined'
            payment.decline_reason = reason
            await session.commit()

            try:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Upload New Screenshot", callback_data=f"upload_payment_{payment.booking_id}")]
                ])
                await callback.bot.send_message(
                    chat_id=payment.user_id,
                    text=f"❌ Payment Declined\n\nReason: {reason}\n\nPlease upload a new screenshot.",
                    reply_markup=keyboard
                )
            except Exception:
                pass

    await state.clear()
    await callback.answer("Declined")
    await callback.message.reply(f"Payment #{payment_id} declined: {reason}")


@router.callback_query(F.data.startswith("chat_"))
async def start_chat(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    booking_id = int(callback.data.split("_")[1])
    await state.update_data(chat_booking_id=booking_id)

    async with async_session() as session:
        result = await session.execute(select(Booking).where(Booking.booking_id == booking_id))
        booking = result.scalar_one_or_none()

    if booking:
        await callback.message.reply(
            f"Chat for Booking #{booking_id}\nCustomer ID: {booking.user_id}\n\nType your message (/done to end):"
        )
        await state.set_state(AdminStates.chatting_with_customer)

    await callback.answer()


@router.message(AdminStates.chatting_with_customer, F.text)
async def send_chat_message(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/done":
        await message.answer("Chat ended.")
        await state.clear()
        return

    data = await state.get_data()
    booking_id = data.get('chat_booking_id')

    async with async_session() as session:
        result = await session.execute(select(Booking).where(Booking.booking_id == booking_id))
        booking = result.scalar_one_or_none()

    if booking:
        try:
            await message.bot.send_message(
                chat_id=booking.user_id,
                text=f"Admin message:\n\n{message.text}"
            )
            await message.answer("Sent.")
        except Exception:
            await message.answer("Failed to send.")


@router.callback_query(F.data == "admin_today")
async def show_today_bookings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    today = date.today()

    async with async_session() as session:
        result = await session.execute(
            select(Booking, User)
            .join(User, Booking.user_id == User.user_id)
            .where(Booking.booking_date == today)
            .order_by(Booking.booking_time)
        )
        bookings = result.all()

    if not bookings:
        text = "No bookings for today."
    else:
        text = f"=== Today ({today}) ===\n\n"
        for booking, user in bookings:
            text += f"{booking.booking_time} - {user.full_name} ({booking.status})\n"

    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def back_to_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    shop_name = await get_setting("SHOP_NAME", settings.SHOP_NAME)
    await callback.message.edit_text(
        f"🛡️ Admin Dashboard\n\n{shop_name}",
        reply_markup=admin_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    shop_name = await get_setting("SHOP_NAME", settings.SHOP_NAME)
    await callback.message.edit_text(
        f"🛡️ Admin Dashboard\n\n{shop_name}",
        reply_markup=admin_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_all_bookings")
async def show_all_bookings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(Booking, User, Service)
            .join(User, Booking.user_id == User.user_id)
            .join(Service, Booking.service_id == Service.service_id)
            .order_by(Booking.booking_date.desc())
            .limit(20)
        )
        bookings = result.all()

    if not bookings:
        text = "No bookings found."
    else:
        text = "=== All Bookings ===\n\n"
        for booking, user, service in bookings:
            text += (
                f"#{booking.booking_id} | {booking.booking_date} | {booking.booking_time}\n"
                f"{user.full_name} | {service.name_en} | {booking.status}\n---\n"
            )

    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_customers")
async def show_customers(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(30)
        )
        users = result.scalars().all()

    if not users:
        text = "No customers yet."
    else:
        text = f"=== Customers ({len(users)}) ===\n\n"
        for user in users:
            text += f"👤 {user.full_name}\n📞 {user.phone_number}\n🌐 {user.language}\n---\n"

    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_services")
async def show_services_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(Service).order_by(Service.service_id))
        services = result.scalars().all()

    text = "=== Services ===\n\n"
    for s in services:
        status = "Active" if s.is_active else "Inactive"
        text += f"#{s.service_id} {s.name_en} - {s.price} Birr ({status})\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Service", callback_data="admin_add_service")],
        [InlineKeyboardButton(text="✏️ Edit Service", callback_data="admin_edit_service")],
        [InlineKeyboardButton(text="🗑️ Delete Service", callback_data="admin_delete_service")],
        [InlineKeyboardButton(text="« Back", callback_data="admin_menu")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_add_service")
async def start_add_service(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    await state.update_data(edit_service_id=None)
    await state.set_state(AdminStates.waiting_for_service_name_en)
    await callback.message.edit_text("Enter service name in English:", reply_markup=admin_back_keyboard())
    await callback.answer()


@router.message(AdminStates.waiting_for_service_name_en, F.text)
async def receive_service_name_en(message: Message, state: FSMContext):
    if message.text != "/skip":
        await state.update_data(service_name_en=message.text.strip())
    await state.set_state(AdminStates.waiting_for_service_name_am)

    data = await state.get_data()
    current = data.get('service_name_am', '')
    await message.answer(f"Enter service name in Amharic (or /skip):\nCurrent: {current}")


@router.message(AdminStates.waiting_for_service_name_am, F.text)
async def receive_service_name_am(message: Message, state: FSMContext):
    if message.text != "/skip":
        await state.update_data(service_name_am=message.text.strip())
    await state.set_state(AdminStates.waiting_for_service_price)

    data = await state.get_data()
    current = data.get('service_price', '')
    await message.answer(f"Enter service price (or /skip):\nCurrent: {current}")


@router.message(AdminStates.waiting_for_service_price, F.text)
async def receive_service_price(message: Message, state: FSMContext):
    if message.text != "/skip":
        try:
            price = int(message.text.strip())
            await state.update_data(service_price=price)
        except ValueError:
            await message.answer("Please enter a valid number.")
            return

    await state.set_state(AdminStates.waiting_for_service_duration)

    data = await state.get_data()
    current = data.get('service_duration', '')
    await message.answer(f"Enter duration in minutes (or /skip):\nCurrent: {current}")


@router.message(AdminStates.waiting_for_service_duration, F.text)
async def receive_service_duration(message: Message, state: FSMContext):
    if message.text != "/skip":
        try:
            duration = int(message.text.strip())
            await state.update_data(service_duration=duration)
        except ValueError:
            await message.answer("Please enter a valid number.")
            return

    data = await state.get_data()
    edit_id = data.get('edit_service_id')

    async with async_session() as session:
        if edit_id:
            service = await session.get(Service, edit_id)
            if service:
                if data.get('service_name_en'):
                    service.name_en = data['service_name_en']
                if data.get('service_name_am'):
                    service.name_am = data['service_name_am']
                if data.get('service_price'):
                    service.price = data['service_price']
                if data.get('service_duration'):
                    service.duration = data['service_duration']
                await session.commit()
                await message.answer("✅ Service updated successfully.")
            else:
                await message.answer("❌ Service not found.")
        else:
            service = Service(
                name_en=data.get('service_name_en', ''),
                name_am=data.get('service_name_am', ''),
                price=data.get('service_price', 0),
                duration=data.get('service_duration', 30),
                is_active=True,
            )
            session.add(service)
            await session.commit()
            await message.answer("✅ Service added successfully.")

    await state.clear()


@router.callback_query(F.data == "admin_edit_service")
async def start_edit_service(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(Service).order_by(Service.service_id))
        services = result.scalars().all()

    if not services:
        await callback.message.edit_text("No services available.", reply_markup=admin_back_keyboard())
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s.name_en, callback_data=f"edit_service_{s.service_id}")]
        for s in services
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="« Back", callback_data="admin_services")])

    await callback.message.edit_text("Select a service to edit:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_service_"))
async def edit_service(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    service_id = int(parts[-1])

    async with async_session() as session:
        service = await session.get(Service, service_id)

    if not service:
        await callback.answer("Service not found", show_alert=True)
        return

    await state.update_data(
        edit_service_id=service_id,
        service_name_en=service.name_en,
        service_name_am=service.name_am,
        service_price=service.price,
        service_duration=service.duration,
    )
    await state.set_state(AdminStates.waiting_for_service_name_en)
    await callback.message.edit_text(
        f"Editing: {service.name_en}\n\nSend new name in English (or /skip to keep):",
        reply_markup=admin_back_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_delete_service")
async def delete_service(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(Service).order_by(Service.service_id))
        services = result.scalars().all()

    if not services:
        await callback.message.edit_text("No services available.", reply_markup=admin_back_keyboard())
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s.name_en, callback_data=f"delete_service_{s.service_id}")]
        for s in services
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="« Back", callback_data="admin_services")])

    await callback.message.edit_text("Select a service to delete:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("delete_service_"))
async def remove_service(callback: CallbackQuery):
    service_id = int(callback.data.split("_")[-1])
    async with async_session() as session:
        service = await session.get(Service, service_id)
        if service:
            await session.delete(service)
            await session.commit()

    await callback.answer("Service deleted")
    await callback.message.edit_text("✅ Service deleted.", reply_markup=admin_back_keyboard())


@router.callback_query(F.data == "admin_schedule")
async def show_schedule(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    schedules = await get_all_schedules()

    text = "=== Working Hours ===\n\n"
    for s in schedules:
        text += f"<b>{DAY_NAMES_EN[s.day_of_week]}:</b> "
        if s.is_working_day:
            text += "Open\n"
            text += format_working_hours_display(s)
        else:
            text += "Closed"
        text += "\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit Day", callback_data="admin_edit_schedule")],
        [InlineKeyboardButton(text="« Back", callback_data="admin_menu")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_edit_schedule")
async def choose_day_to_edit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    schedules = await get_all_schedules()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{DAY_NAMES_EN[s.day_of_week]} ({'Open' if s.is_working_day else 'Closed'})",
            callback_data=f"edit_day_{s.day_of_week}"
        )]
        for s in schedules
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="« Back", callback_data="admin_schedule")])

    await callback.message.edit_text("Select a day to edit:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_day_"))
async def edit_day_options(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    day = int(callback.data.split("_")[-1])
    schedule = await get_day_schedule(day)

    if not schedule:
        await callback.answer("Schedule not found")
        return

    western_open = format_time(schedule.opening_time)
    western_close = format_time(schedule.closing_time)
    eth_open = to_ethiopian_time_str(schedule.opening_time)
    eth_close = to_ethiopian_time_str(schedule.closing_time)

    text = (
        f"<b>Editing: {DAY_NAMES_EN[day]}</b>\n\n"
        f"Status: {'Open' if schedule.is_working_day else 'Closed'}\n"
        f"Opens: {western_open} (Eth: {eth_open})\n"
        f"Closes: {western_close} (Eth: {eth_close})\n"
    )
    
    if schedule.lunch_start and schedule.lunch_end:
        w_lunch_s = format_time(schedule.lunch_start)
        w_lunch_e = format_time(schedule.lunch_end)
        e_lunch_s = to_ethiopian_time_str(schedule.lunch_start)
        e_lunch_e = to_ethiopian_time_str(schedule.lunch_end)
        text += f"Lunch: {w_lunch_s}-{w_lunch_e} (Eth: {e_lunch_s}-{e_lunch_e})\n"
    else:
        text += "Lunch: None\n"
    
    text += (
        f"Slot: {schedule.slot_duration} min\n\n"
        f"<b>Send new values:</b>\n"
        f"<code>open,close,lunch_start,lunch_end,slot,is_open</code>\n\n"
        f"Example: <code>02:00,13:00,06:00,06:30,60,true</code>\n"
        f"Or send <code>closed</code> to mark as non-working day\n"
        f"Send /skip to cancel"
    )

    await state.set_state(AdminStates.editing_schedule)
    await state.update_data(edit_day=day)
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.editing_schedule, F.text)
async def save_day_schedule(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/skip":
        await state.clear()
        await message.answer("Cancelled.")
        return

    data = await state.get_data()
    day = data['edit_day']

    if message.text.lower() == 'closed':
        await update_day_schedule(day, is_working_day=False)
        await state.clear()
        await message.answer(f"✅ {DAY_NAMES_EN[day]} marked as closed.")
        return

    try:
        parts = message.text.split(',')
        opening = dt_time.fromisoformat(parts[0].strip())
        closing = dt_time.fromisoformat(parts[1].strip())
        lunch_start = dt_time.fromisoformat(parts[2].strip()) if len(parts) > 2 and parts[2].strip() else None
        lunch_end = dt_time.fromisoformat(parts[3].strip()) if len(parts) > 3 and parts[3].strip() else None
        slot_dur = int(parts[4].strip()) if len(parts) > 4 and parts[4].strip() else 60
        is_open = parts[5].strip().lower() == 'true' if len(parts) > 5 else True

        await update_day_schedule(
            day_of_week=day,
            is_working_day=is_open,
            opening_time=opening,
            closing_time=closing,
            lunch_start=lunch_start,
            lunch_end=lunch_end,
            slot_duration=slot_dur,
        )

        await state.clear()
        await message.answer(f"✅ {DAY_NAMES_EN[day]} updated successfully!")
    except Exception as e:
        await message.answer(f"❌ Error: {e}\n\nFormat: open,close,lunch_start,lunch_end,slot,is_open\nExample: 02:00,13:00,06:00,06:30,60,true")


@router.callback_query(F.data == "admin_settings")
async def show_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    settings_map = await get_all_settings()
    text = "=== Settings ===\n\n"
    for key, value in settings_map.items():
        text += f"{key}: {value}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit Setting", callback_data="admin_edit_setting")],
        [InlineKeyboardButton(text="« Back", callback_data="admin_menu")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_edit_setting")
async def edit_setting_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return

    settings_map = await get_all_settings()

    if not settings_map:
        await callback.message.edit_text("No settings available.", reply_markup=admin_back_keyboard())
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=key, callback_data=f"edit_setting_{key}")]
        for key in settings_map
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="« Back", callback_data="admin_settings")])

    await callback.message.edit_text("Select a setting to edit:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_setting_"))
async def start_edit_setting(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("edit_setting_", "", 1)
    current = await get_setting(key, "")
    await state.update_data(edit_setting_key=key)
    await state.set_state(AdminStates.waiting_for_setting_value)
    await callback.message.edit_text(f"Editing: {key}\nCurrent: {current}\n\nEnter new value:", reply_markup=admin_back_keyboard())
    await callback.answer()


@router.message(AdminStates.waiting_for_setting_value, F.text)
async def receive_setting_value(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data['edit_setting_key']
    value = message.text.strip()

    await set_setting(key, value)
    await refresh_cache()

    await state.clear()
    await message.answer(f"✅ {key} updated to: {value}")