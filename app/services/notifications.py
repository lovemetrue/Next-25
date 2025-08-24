import logging
from database import crud
from telebot import types

logger = logging.getLogger(__name__)


def notify_driver_about_request(bot, request_id):
    request = crud.get_request(request_id)
    driver = crud.get_user(request.driver_id)

    if not driver:
        return

    text = f"🚛 Новая заявка #{request_id}\n\n"
    text += f"От: {request.point_a} → До: {request.point_b}\n"
    text += f"Время: {request.scheduled_time}\n"
    if request.comment:
        text += f"Комментарий: {request.comment}\n"

    markup = types.InlineKeyboardMarkup()
    accept_btn = types.InlineKeyboardButton(
        "✅ Принять",
        callback_data=f"accept_request:{request_id}"
    )
    reject_btn = types.InlineKeyboardButton(
        "❌ Отклонить",
        callback_data=f"reject_request:{request_id}"
    )
    markup.add(accept_btn, reject_btn)

    bot.send_message(driver.telegram_id, text, reply_markup=markup)



def notify_dispatcher_about_status_change(bot, request_id, message_text):
    """Уведомить диспетчера об изменении статуса заявки"""
    try:
        request = crud.get_request(request_id)
        if not request or not request.dispatcher:
            logger.error(f"Не удалось найти заявку #{request_id} или диспетчера")
            return False

        # Форматируем сообщение
        notification_text = f"🔔 Изменение статуса заявки #{request_id}\n\n"
        notification_text += f"{message_text}\n\n"
        notification_text += f"Текущий статус: {request.status}\n"

        # Отправляем уведомление диспетчеру
        bot.send_message(
            request.dispatcher.telegram_id,
            notification_text
        )

        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления диспетчеру: {e}")
        return False


def notify_driver_about_assignment(bot, request_id):
    """Уведомить водителя о назначении на заявку"""
    try:
        request = crud.get_request(request_id)
        if not request or not request.driver:
            logger.error(f"Не удалось найти заявку #{request_id} или водителя")
            return False

        # Форматируем сообщение о новой заявке
        message_text = format_request_notification(request)

        # Создаем клавиатуру для принятия/отклонения заявки
        markup = types.InlineKeyboardMarkup()
        accept_btn = types.InlineKeyboardButton(
            "✅ Принять",
            callback_data=f"accept_request:{request_id}"
        )
        reject_btn = types.InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"reject_request:{request_id}"
        )
        markup.add(accept_btn, reject_btn)

        # Отправляем уведомление водителю
        bot.send_message(
            request.driver.telegram_id,
            message_text,
            reply_markup=markup
        )

        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления водителю: {e}")
        return False


def notify_about_new_message(bot, request_id, sender_id, message_text):
    """Уведомить участников заявки о новом сообщении в чате"""
    try:
        request = crud.get_request(request_id)
        if not request:
            logger.error(f"Не удалось найти заявку #{request_id}")
            return False

        # Определяем получателей (все участники заявки кроме отправителя)
        recipients = []
        if request.dispatcher.telegram_id != sender_id:
            recipients.append(request.dispatcher)
        if request.driver and request.driver.telegram_id != sender_id:
            recipients.append(request.driver)

        # Форматируем сообщение
        notification_text = f"💬 Новое сообщение в заявке #{request_id}\n\n"
        notification_text += f"{message_text}\n\n"
        notification_text += f"От: {get_user_display_name(sender_id)}"

        # Отправляем уведомления всем получателям
        for recipient in recipients:
            bot.send_message(
                recipient.telegram_id,
                notification_text
            )

        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о сообщении: {e}")
        return False


def notify_about_system_event(bot, user_id, event_text):
    """Уведомить пользователя о системном событии"""
    try:
        bot.send_message(
            user_id,
            f"⚙️ Системное уведомление:\n\n{event_text}"
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке системного уведомления: {e}")
        return False


def format_request_notification(request):
    """Форматирование уведомления о заявке"""
    text = f"🚛 Новая заявка #{request.id}\n\n"
    text += f"Префикс: {request.prefix}\n"
    text += f"Маршрут: {request.point_a} → {request.point_b}\n"
    text += f"Дата/время: {request.scheduled_time}\n"

    if request.cargo_type:
        text += f"Груз: {request.cargo_type}\n"
    if request.weight:
        text += f"Вес: {request.weight} кг\n"
    if request.volume:
        text += f"Объем: {request.volume} м³\n"
    if request.comment:
        text += f"Комментарий: {request.comment}\n"

    text += f"\nДиспетчер: {request.dispatcher.first_name}"

    return text


def get_user_display_name(user_id):
    """Получить отображаемое имя пользователя"""
    user = crud.get_user(user_id)
    if not user:
        return "Неизвестный пользователь"

    if user.username:
        return f"{user.first_name} (@{user.username})"
    else:
        return user.first_name