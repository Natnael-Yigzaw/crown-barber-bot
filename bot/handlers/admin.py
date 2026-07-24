import logging
from datetime import datetime, date
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from bot.config import settings
from bot.keyboards.inline import admin_back_keyboard, admin_menu_keyboard
from bot.states.admin import AdminStates
from bot.services.database import async_session
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Pending Payments", callback_data="admin_pending")],
        [InlineKeyboardButton(text="Today's Bookings", callback_data="admin_today")],
    ])
    
    await message.answer("=== Admin Panel ===\n\nSelect an option:", reply_markup=keyboard)


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
        await callback.message.answer(
            "No pending payments.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Back", callback_data="admin_back")]
            ])
        )
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
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"approve_{payment.payment_id}"),
                InlineKeyboardButton(text="Decline", callback_data=f"decline_{payment.payment_id}")
            ],
            [InlineKeyboardButton(text="Chat", callback_data=f"chat_{booking.booking_id}")]
        ])
        
        if payment.screenshot_path:
            try:
                with open(payment.screenshot_path, 'rb') as photo:
                    await callback.message.answer_photo(photo=photo, caption=text, reply_markup=keyboard)
            except Exception:
                await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.answer(text, reply_markup=keyboard)
        
        count += 1
    
    await callback.answer(f"Found {count} pending")
    await callback.message.edit_text(
        f"Found {count} pending payment(s):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Back", callback_data="admin_back")]
        ])
    )


@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    payment_id = int(callback.data.split("_")[1])
    
    async with async_session() as session:
        result = await session.execute(select(Payment).where(Payment.payment_id == payment_id))
        payment = result.scalar_one_or_none()
        
        if payment:
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
                    text="=== Payment Verified! ===\n\nYour booking is now confirmed. See you soon!"
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
        
        if payment:
            payment.status = 'declined'
            payment.decline_reason = reason
            await session.commit()
            
            try:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Upload New Screenshot", callback_data=f"upload_payment_{payment.booking_id}")]
                ])
                await callback.bot.send_message(
                    chat_id=payment.user_id,
                    text=f"=== Payment Declined ===\n\nReason: {reason}\n\nPlease upload a new screenshot.",
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def back_to_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"🛡️ Admin Dashboard\n\n{settings.SHOP_NAME}",
        reply_markup=admin_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_menu")
async def admin_menu_callback(callback: CallbackQuery):
    """Return to admin main menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"🛡️ Admin Dashboard\n\n{settings.SHOP_NAME}",
        reply_markup=admin_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_all_bookings")
async def show_all_bookings(callback: CallbackQuery):
    """Show all bookings"""
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
                f"{user.full_name} | {service.name_en} | {booking.status}\n"
                f"---\n"
            )
    
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_customers")
async def show_customers(callback: CallbackQuery):
    """Show all registered customers"""
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
    """Show and manage services"""
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
        [InlineKeyboardButton(text="« Back", callback_data="admin_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "admin_settings")
async def show_settings(callback: CallbackQuery):
    """Show current settings"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    text = (
        "=== Settings ===\n\n"
        f"Shop Name: {settings.SHOP_NAME}\n"
        f"Address: {settings.SHOP_ADDRESS}\n"
        f"Phone: {settings.SHOP_PHONE}\n"
        f"Deposit: {settings.DEPOSIT_AMOUNT} Birr\n"
        f"CBE: {settings.CBE_ACCOUNT}\n"
        f"Telebirr: {settings.TELEBIRR_NUMBER}\n"
        f"Hours: {settings.OPENING_TIME} - {settings.CLOSING_TIME}\n"
        f"Closed Days: Sunday\n\n"
        "To change settings, edit the .env file and restart."
    )
    
    await callback.message.edit_text(text, reply_markup=admin_back_keyboard())
    await callback.answer()