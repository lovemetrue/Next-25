from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from app.database.models import Order, OrderStatus
from telebot import types




# ===================== СПИСКИ ПО СТАТУСАМ (4 КНОПКИ) =====================
def get_status_filter_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает InlineKeyboard с 4 кнопками списков:
    - все новые, подтвержденные, выполненные (доставленные), отмененные.
    """
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🆕 Все новые заявки", callback_data="list_status:NEW"),
        InlineKeyboardButton("✅ Все подтвержденные заявки", callback_data="list_status:CONFIRMED"),
        InlineKeyboardButton("📦 Все выполненные заявки", callback_data="list_status:DELIVERED"),
        InlineKeyboardButton("❌ Все отмененные заявки", callback_data="list_status:CANCELLED"),
    )
    return kb


# keyboards/request_actions.py

#
# def get_driver_status_keyboard(order):
#     markup = types.InlineKeyboardMarkup(row_width=1)
#
#     # В зависимости от текущего статуса показываем доступные варианты
#     if order.status == int(OrderStatus.CONFIRMED):
#         markup.add(
#             types.InlineKeyboardButton("🚛 В Пути",
#                                        callback_data=f"driver_set_status:{order.id}:{int(OrderStatus.ENROUTE)}")
#         )
#     elif order.status == int(OrderStatus.ENROUTE):
#         markup.add(
#             types.InlineKeyboardButton("📦 На загрузке",
#                                        callback_data=f"driver_set_status:{order.id}:{int(OrderStatus.LOADING)}")
#         )
#     elif order.status == int(OrderStatus.LOADING):
#         markup.add(
#             types.InlineKeyboardButton("🚛 В путь на выгрузку",
#                                        callback_data=f"driver_set_status:{order.id}:{int(OrderStatus.ENROUTE_TO_LOADING)}"),
#             types.InlineKeyboardButton("✅ Доставлено",
#                                        callback_data=f"driver_set_status:{order.id}:{int(OrderStatus.DELIVERED)}")
#         )
#
#     markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"driver_cancel:{order.id}"))
#     return markup

def get_prefix_keyboard():
    """Клавиатура для выбора префикса заявки"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton('с НДС'),
        KeyboardButton('без НДС'),
        KeyboardButton('нал')
    )
    markup.add(KeyboardButton('❌ Отмена'))
    return markup


def get_drivers_keyboard(drivers):
    """Клавиатура для выбора водителя"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)

    for driver in drivers:
        btn_text = f"{driver.first_name} {driver.last_name or ''}"
        if driver.username:
            btn_text += f" (@{driver.username})"
        markup.add(KeyboardButton(btn_text))

    markup.add(KeyboardButton('❌ Без водителя'), KeyboardButton('❌ Отмена'))
    return markup


def get_request_status_keyboard():
    """Клавиатура для выбора статуса заявки"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton('🆕 Новая'),
        KeyboardButton('✅ Подтверждена'),
        KeyboardButton('🚛 В пути'),
        KeyboardButton('📦 На загрузке'),
        KeyboardButton('✅ Доставлено'),
        KeyboardButton('❌ Отменена')
    )
    markup.add(KeyboardButton('⬅️ Назад'), KeyboardButton('❌ Отмена'))
    return markup

# keyboards/request_actions.py
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import OrderStatus

def get_request_actions_keyboard(order, role="dispatcher", include_chat: bool = True):
    """
    Возвращает InlineKeyboardMarkup с кнопками, подходящими для роли.
    """
    markup = InlineKeyboardMarkup(row_width=2)

    if role == "dispatcher":
        # Редактирование
        markup.add(
            InlineKeyboardButton("📍 Изменить точку А", callback_data=f"edit_from:{order.id}"),
            InlineKeyboardButton("📍 Изменить точку Б", callback_data=f"edit_to:{order.id}"),
        )
        markup.add(
            InlineKeyboardButton("📅 Изменить дату/время", callback_data=f"edit_dt:{order.id}"),
            InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_comment:{order.id}"),
        )
        markup.add(
            InlineKeyboardButton("📦 Тип груза", callback_data=f"edit_cargo:{order.id}"),
            InlineKeyboardButton("⚖️ Вес/объем", callback_data=f"edit_weight:{order.id}"),
        )

        # Назначение водителя
        markup.add(
            InlineKeyboardButton("👨‍💼 Назначить/сменить водителя", callback_data=f"assign_driver:{order.id}")
        )

        # Отмена — если статус новый/подтвержден
        if order.status in (int(OrderStatus.NEW), int(OrderStatus.CONFIRMED)):
            markup.add(
                InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_request:{order.id}")
            )

    elif role == "driver":
        # Водительские кнопки по статусу (можно расширить)
        # Для новой заявки - кнопка принятия
        if order.status == int(OrderStatus.NEW):
            markup.add(
                types.InlineKeyboardButton("✅ Принять заявку", callback_data=f"driver_accept:{order.id}")
            )
        # Для активных заявок - кнопки действий
        elif order.status not in [int(OrderStatus.DELIVERED), int(OrderStatus.CANCELLED)]:
            markup.add(
                types.InlineKeyboardButton("📋 Изменить статус", callback_data=f"driver_change_status:{order.id}"),
                types.InlineKeyboardButton("💬 Комментарий", callback_data=f"driver_add_comment:{order.id}")
            )
            markup.add(
                types.InlineKeyboardButton("📸 Прикрепить фото", callback_data=f"driver_add_photo:{order.id}")
            )

        if order.status == int(OrderStatus.CONFIRMED):
            markup.add(
                InlineKeyboardButton("🚛 В путь", callback_data=f"start_driving:{order.id}")
            )
        elif order.status == int(OrderStatus.ENROUTE):
            markup.add(
                InlineKeyboardButton("✅ Доставлено", callback_data=f"delivered:{order.id}")
            )
    elif user_role == 'manager':
        markup.add(
                    InlineKeyboardButton('👨‍💼 Переназначить', callback_data=f'reassign_driver:{order.id}'),
                    InlineKeyboardButton('❌ Отменить', callback_data=f'cancel_request:{order.id}')
                )
        if request_status == 'delivered':
            markup.add(InlineKeyboardButton('📊 Подробнее', callback_data=f'request_details:{order.id}'))

    # 💬 Чат и 🕘 История доступны и водителю, и диспетчеру
    if include_chat:
        markup.add(
            InlineKeyboardButton("💬 Чат", callback_data=f"open_chat:{order.id}"),
            InlineKeyboardButton("🕘 История", callback_data=f"request_history:{order.id}"),
        )

    return markup

# def get_request_actions_keyboard(order, user_role):
#     """Клавиатура действий с заявкой в зависимости от статуса и роли"""
#     markup = InlineKeyboardMarkup(row_width=2)
#     request_status = order.status
#
#     if user_role == 'dispatcher':
#         if request_status in ['new', 'confirmed']:
#             markup.add(
#                 InlineKeyboardButton('✏️ Редактировать', callback_data=f'edit_request:{order.id}'),
#                 InlineKeyboardButton('👨‍💼 Назначить водителя', callback_data=f'assign_driver:{order.id}')
#             )
#         if request_status == 'new':
#             markup.add(InlineKeyboardButton('❌ Отменить', callback_data=f'cancel_request:{order.id}'))
#
#     elif user_role == 'driver':
#         if request_status == 'assigned':
#             markup.add(
#                 InlineKeyboardButton('✅ Принять', callback_data=f'accept_request:{order.id}'),
#                 InlineKeyboardButton('❌ Отклонить', callback_data=f'reject_request:{order.id}')
#             )
#         elif request_status == 'confirmed':
#             markup.add(
#                 InlineKeyboardButton('🚛 В путь', callback_data=f'start_driving:{order.id}'),
#                 InlineKeyboardButton('📦 На загрузке', callback_data=f'loading:{order.id}')
#             )
#         elif request_status == 'loading':
#             markup.add(InlineKeyboardButton('🚛 В путь', callback_data=f'start_driving:{order.id}'))
#         elif request_status == 'in_transit':
#             markup.add(InlineKeyboardButton('✅ Доставлено', callback_data=f'delivered:{order.id}'))
#
#     elif user_role == 'manager':
#         markup.add(
#             InlineKeyboardButton('👨‍💼 Переназначить', callback_data=f'reassign_driver:{order.id}'),
#             InlineKeyboardButton('❌ Отменить', callback_data=f'cancel_request:{order.id}')
#         )
#         if request_status == 'delivered':
#             markup.add(InlineKeyboardButton('📊 Подробнее', callback_data=f'request_details:{order.id}'))
#
#     # Для всех ролей
#     markup.add(
#         InlineKeyboardButton('💬 Чат', callback_data=f'open_chat:{order.id}'),
#         InlineKeyboardButton('📋 История', callback_data=f'request_history:{order.id}')
#     )
#
#     return markup


def get_confirmation_keyboard():
    """Клавиатура для подтверждения действий"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('✅ Да', callback_data='confirm_yes'),
        InlineKeyboardButton('❌ Нет', callback_data='confirm_no')
    )
    return markup


def get_request_filter_keyboard():
    """Клавиатура для фильтрации заявок"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        KeyboardButton('🆕 Новые'),
        KeyboardButton('✅ Подтвержденные'),
        KeyboardButton('🚛 В пути')

    )
    markup.add(
        KeyboardButton('📦 На загрузке'),
        KeyboardButton('✅ Доставленные'),
        KeyboardButton('❌ Отмененные')
    )
    markup.add(
        KeyboardButton('📅 Сегодня'),
        KeyboardButton('📆 Неделя'),
        KeyboardButton('📊 Все')
    )
    markup.add(KeyboardButton('⬅️ Назад'))
    return markup
