from aiogram.fsm.state import State, StatesGroup

class RatingStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_review = State()