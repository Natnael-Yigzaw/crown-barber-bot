from datetime import date, time
from html import escape

from bot.utils.ethiopian_time import format_ethiopian_date
from bot.utils.time_format import to_12h, to_12h_str, to_ethiopian_display


STATUS_LABELS = {
    "pending_payment": ("Waiting for payment", "ክፍያ በመጠበቅ ላይ"),
    "pending_verification": ("Payment under review", "ክፍያ በመረጋገጥ ላይ"),
    "confirmed": ("Confirmed", "ተረጋግጧል"),
    "completed": ("Completed", "ተጠናቋል"),
    "declined": ("Payment issue", "የክፍያ ችግር"),
    "canceled": ("Canceled", "ተሰርዟል"),
}


def status_label(status: str, lang: str = "en") -> str:
    labels = STATUS_LABELS.get(status)
    if not labels:
        return status.replace("_", " ").title()
    return labels[1] if lang == "am" else labels[0]


def time_label(time_str: str, include_ethiopian: bool = True) -> str:
    western = to_12h_str(time_str)
    if not include_ethiopian:
        return western
    return f"{western} (Eth: {to_ethiopian_display(time_str)})"


def booking_time_label(booking_time: time, include_ethiopian: bool = True) -> str:
    return time_label(booking_time.strftime("%H:%M"), include_ethiopian)


def customer_booking_summary(
    service_name: str,
    service_price: int,
    booking_date: str,
    booking_time: str,
    deposit: int,
    remaining: int,
    lang: str = "en",
) -> str:
    if lang == "am":
        eth_date = format_ethiopian_date(date.fromisoformat(booking_date))
        eth_time = to_ethiopian_display(booking_time)
        return (
            "የቀጠሮ ማጠቃለያ\n\n"
            f"አገልግሎት: {service_name}\n"
            f"ዋጋ: {service_price} Birr\n"
            f"ቀን: {eth_date}\n"
            f"ሰዓት: {eth_time}\n\n"
            f"ቅድመ ክፍያ: {deposit} Birr\n"
            f"በሱቅ የሚከፈል: {remaining} Birr\n\n"
            "ቀጠሮውን ያረጋግጡ?"
        )

    return (
        "Confirm your appointment\n\n"
        f"Service: {service_name}\n"
        f"Price: {service_price} Birr\n"
        f"Date: {booking_date}\n"
        f"Time: {time_label(booking_time)}\n\n"
        f"Deposit: {deposit} Birr\n"
        f"Pay at the shop: {remaining} Birr\n\n"
        "Ready to confirm?"
    )


def customer_booking_confirmed(
    service_name: str,
    booking_date: str,
    booking_time: str,
    deposit: int,
    cbe: str,
    telebirr: str,
    lang: str = "en",
) -> str:
    if lang == "am":
        eth_date = format_ethiopian_date(date.fromisoformat(booking_date))
        eth_time = to_ethiopian_display(booking_time)
        return (
            "ቀጠሮ ተመዝግቧል\n\n"
            f"አገልግሎት: {service_name}\n"
            f"ቀን: {eth_date}\n"
            f"ሰዓት: {eth_time}\n\n"
            f"ቅድመ ክፍያ: {deposit} Birr\n"
            "ክፍያውን ከፈጸሙ በኋላ ስክሪንሾት ይላኩ።\n\n"
            f"CBE: {cbe}\n"
            f"Telebirr: {telebirr}"
        )

    return (
        "Appointment saved\n\n"
        f"Service: {service_name}\n"
        f"Date: {booking_date}\n"
        f"Time: {time_label(booking_time)}\n\n"
        f"Deposit due: {deposit} Birr\n"
        "Send your payment screenshot after paying.\n\n"
        f"CBE: {cbe}\n"
        f"Telebirr: {telebirr}"
    )


def customer_booking_details(booking, service_name: str, lang: str = "en") -> str:
    booking_time_str = booking.booking_time.strftime("%H:%M")
    status = status_label(booking.status, lang)

    if lang == "am":
        return (
            "የቀጠሮ ዝርዝር\n\n"
            f"አገልግሎት: {service_name}\n"
            f"ቀን: {format_ethiopian_date(booking.booking_date)}\n"
            f"ሰዓት: {to_ethiopian_display(booking_time_str)}\n"
            f"ሁኔታ: {status}\n"
            f"ቅድመ ክፍያ: {booking.deposit_amount} Birr\n"
            f"ቀሪ: {booking.remaining_amount} Birr"
        )

    return (
        "Appointment details\n\n"
        f"Service: {service_name}\n"
        f"Date: {booking.booking_date}\n"
        f"Time: {time_label(booking_time_str)}\n"
        f"Status: {status}\n"
        f"Deposit: {booking.deposit_amount} Birr\n"
        f"Remaining: {booking.remaining_amount} Birr"
    )


def payment_instructions(booking, deposit: int, cbe: str, telebirr: str, lang: str = "en") -> str:
    booking_time = booking_time_label(booking.booking_time)

    if lang == "am":
        return (
            f"ቅድመ ክፍያ: <b>{deposit} Birr</b>\n\n"
            f"ቀጠሮ: {booking.booking_date} at {escape(booking_time)}\n\n"
            f"CBE: <code>{escape(cbe)}</code>\n"
            f"Telebirr: <code>{escape(telebirr)}</code>\n\n"
            "ከከፈሉ በኋላ የስክሪንሾት ፎቶዎን በቀጥታ ይላኩ።\n"
            "ፋይሉ ከ5MB በታች መሆን አለበት።"
        )

    return (
        f"Deposit: <b>{deposit} Birr</b>\n\n"
        f"Appointment: {booking.booking_date} at {escape(booking_time)}\n\n"
        f"CBE: <code>{escape(cbe)}</code>\n"
        f"Telebirr: <code>{escape(telebirr)}</code>\n\n"
        "Send your payment screenshot as a photo.\n"
        "File size must be under 5MB."
    )


def admin_booking_line(booking, user, service=None) -> str:
    service_name = service.name_en if service else "N/A"
    return (
        f"#{booking.booking_id} | {to_12h(booking.booking_time)} | "
        f"{user.full_name} | {service_name} | {status_label(booking.status)}"
    )


def admin_payment_review(payment, booking, user, service=None) -> str:
    service_name = service.name_en if service else "N/A"
    return (
        "Payment review\n\n"
        f"Booking: #{booking.booking_id}\n"
        f"Customer: {user.full_name}\n"
        f"Phone: {user.phone_number}\n"
        f"Service: {service_name}\n"
        f"Appointment: {booking.booking_date} at {booking_time_label(booking.booking_time)}\n"
        f"Status: {status_label(booking.status)}\n"
        f"Amount: {payment.amount} Birr"
    )
