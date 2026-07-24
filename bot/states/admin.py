from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_decline_reason = State()
    chatting_with_customer = State()
    editing_service = State()
    editing_schedule = State()
    editing_settings = State()