from aiogram.fsm.state import State, StatesGroup

class QuizState(StatesGroup):
    testing = State() # Test jarayonida ekanligi

class RegistrationState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()

class AdminState(StatesGroup):
    waiting_for_broadcast_message = State()

class MentorState(StatesGroup):
    waiting_for_group_broadcast = State()
    waiting_for_resource_title = State()
    waiting_for_resource_content = State()
