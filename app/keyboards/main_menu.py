from telebot.types import ReplyKeyboardMarkup, KeyboardButton



def get_main_menu(role):
    """Получить главное меню в зависимости от роли пользователя"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if role == 'dispatcher':
        markup.add(
            KeyboardButton('➕ Создать заявку'),
            KeyboardButton('📋 Мои заявки')
        )
        markup.add(
            KeyboardButton('👨‍💼 Водители'),
            KeyboardButton('📊 Статистика')
        )
        markup.add(
            KeyboardButton('📂 Заявки по статусу')
        )
    elif role == 'driver':
        markup.add(
            KeyboardButton('📆 Активные заявки'),
        )
        markup.add(
            KeyboardButton('📊 Моя статистика')
        )
        markup.add(
            KeyboardButton('🚛 Завершенные заявки')
        )
    elif role == 'manager':
        markup.add(
            KeyboardButton('📊 Общая статистика'),
            KeyboardButton('👥 Персонал')
        )
        markup.add(
            KeyboardButton('📋 Все заявки'),
            KeyboardButton('📈 Аналитика')
        )
        markup.add(
            KeyboardButton('📤 Экспорт отчетов')
        )

    else:
        # Меню по умолчанию (для неавторизованных пользователей)
        markup.add(
            KeyboardButton('👤 Регистрация'),
            KeyboardButton('ℹ️ Помощь')
        )

    return markup


def get_cancel_button():
    """Кнопка отмены действия"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('❌ Отмена'))
    return markup


def get_back_button():
    """Кнопка возврата"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('⬅️ Назад'))
    return markup



def get_contact_button():
    """Кнопка для запроса номера телефона"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('📞 Отправить номер', request_contact=True))
    markup.add(KeyboardButton('❌ Отмена'))
    return markup