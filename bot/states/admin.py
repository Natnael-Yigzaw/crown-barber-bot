from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_decline_reason = State()
    chatting_with_customer = State()
    editing_service = State()
    waiting_for_service_name_en = State()
    waiting_for_service_name_am = State()
    waiting_for_service_price = State()
    waiting_for_service_duration = State()
    waiting_for_service_status = State()
    editing_schedule = State()
    editing_settings = State()
    waiting_for_setting_key = State()
    waiting_for_setting_value = State()