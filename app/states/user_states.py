from telebot.handler_backends import State, StatesGroup

class RegistrationStates(StatesGroup):
    """Состояния процесса регистрации пользователя"""
    phone = State()  # Ожидание номера телефона
    role = State()   # Ожидание выбора роли
    driver_info = State()  # Ожидание информации о водителе (только для водителей)

class ProfileUpdateStates(StatesGroup):
    """Состояния процесса обновления профиля"""
    phone = State()
    vehicle_type = State()

class AdminActionsStates(StatesGroup):
    """Состояния для административных действий"""
    add_user = State()
    edit_user = State()
    deactivate_user = State()