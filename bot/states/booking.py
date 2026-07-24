from aiogram.fsm.state import State, StatesGroup

class BookingStates(StatesGroup):
    selecting_service = State()
    selecting_date = State()
    selecting_time = State()
    confirming = State()

class RescheduleStates(StatesGroup):
    selecting_new_date = State()
    selecting_new_time = State()