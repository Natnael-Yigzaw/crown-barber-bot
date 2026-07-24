from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def language_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇪🇹 አማርኛ", callback_data="lang_am"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    )
    return builder.as_markup()


def main_menu_keyboard(lang: str = 'en'):
    builder = InlineKeyboardBuilder()

    if lang == 'am':
        builder.row(InlineKeyboardButton(text="✂️ ቀጠሮ ይያዙ", callback_data="book_appointment"))
        builder.row(InlineKeyboardButton(text="🗓️ ቀጠሮዎቼ", callback_data="my_bookings"))
        builder.row(InlineKeyboardButton(text="✨ ስለ እኛ", callback_data="about"))
        builder.row(InlineKeyboardButton(text="🌐 ቋንቋ ቀይር", callback_data="change_language"))
    else:
        builder.row(InlineKeyboardButton(text="✂️ Book Appointment", callback_data="book_appointment"))
        builder.row(InlineKeyboardButton(text="🗓️ My Bookings", callback_data="my_bookings"))
        builder.row(InlineKeyboardButton(text="✨ About Us", callback_data="about"))
        builder.row(InlineKeyboardButton(text="🌐 Change Language", callback_data="change_language"))

    return builder.as_markup()


def services_keyboard(services: list, lang: str = 'en'):
    builder = InlineKeyboardBuilder()

    for service in services:
        name = service.name_am if lang == 'am' else service.name_en
        text = f"{name} - {service.price} Birr"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"service_{service.service_id}"))

    back_text = "🔙 ተመለስ" if lang == 'am' else "🔙 Back"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="back_to_main"))

    return builder.as_markup()


def my_bookings_keyboard(bookings: list, lang: str = 'en'):
    builder = InlineKeyboardBuilder()

    for booking in bookings:
        text = f"{booking.booking_date} - {booking.booking_time}"
        builder.row(InlineKeyboardButton(text=text, callback_data=f"view_booking_{booking.booking_id}"))

    back_text = "🔙 Back" if lang == 'en' else "🔙 ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="back_to_main"))

    return builder.as_markup()


def booking_detail_keyboard(booking_id: int, status: str, lang: str = 'en'):
    builder = InlineKeyboardBuilder()

    if status in ['pending_payment', 'pending_verification', 'confirmed']:
        reschedule_text = "🔄 Reschedule" if lang == 'en' else "🔄 ቀን ቀይር"
        builder.row(InlineKeyboardButton(text=reschedule_text, callback_data=f"reschedule_{booking_id}"))

    back_text = "🔙 Back" if lang == 'en' else "🔙 ተመለስ"
    builder.row(InlineKeyboardButton(text=back_text, callback_data="my_bookings"))

    return builder.as_markup()


def admin_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Today's Bookings", callback_data="admin_today"))
    builder.row(InlineKeyboardButton(text="📋 All Bookings", callback_data="admin_all_bookings"))
    builder.row(InlineKeyboardButton(text="👥 Customers", callback_data="admin_customers"))
    builder.row(InlineKeyboardButton(text="💈 Services", callback_data="admin_services"))
    builder.row(InlineKeyboardButton(text="🕐 Schedule", callback_data="admin_schedule"))
    builder.row(InlineKeyboardButton(text="📸 Pending Payments", callback_data="admin_pending"))
    builder.row(InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings"))
    return builder.as_markup()


def admin_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Back to Admin Menu", callback_data="admin_menu")]
    ])