# handlers/chat.py
from datetime import datetime
from telebot import TeleBot, types
from database.models import Order, User, OrderMessage, Attachment, UserRole


def register_chat_handlers(bot: TeleBot):

    # ---------- Открыть чат ----------
    @bot.callback_query_handler(func=lambda c: c.data.startswith("open_chat:"))
    def cb_open_chat(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "❌ Неверный идентификатор заявки.")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена.")
            return

        bot.send_message(
            call.message.chat.id,
            f"💬 Чат по заявке #{order.id}.\n"
            f"Напиши сообщение — оно будет отправлено другой стороне и сохранено в истории.\n"
            f"Чтобы выйти из чата — нажми ⬅️ Назад или отправь /stop."
        )

        # сохраняем в state, что пользователь пишет в чат
        bot.set_state(call.from_user.id, "chatting", call.message.chat.id)
        # записываем order_id в state через контекст
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order.id

    # ---------- Сообщения в чате ----------
    @bot.message_handler(state="chatting", content_types=["text", "photo", "document"])
    def chat_message(message: types.Message):
        # получаем данные state через контекст (это исправляет ошибку TypeError)
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        if not order_id:
            bot.send_message(message.chat.id, "❌ Внутренняя ошибка: не найдена привязка к заявке. Завершаю чат.")
            try:
                bot.delete_state(message.from_user.id, message.chat.id)
            except Exception:
                pass
            return

        # возможность выйти из чата по тексту
        text_lower = (message.text or "").strip().lower() if message.content_type == "text" else ""
        if text_lower in ("⬅️ назад".lower(), "/stop", "/exit", "выйти"):
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.send_message(message.chat.id, "Вы вышли из чата.", reply_markup=None)
            return

        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Ошибка: вы не зарегистрированы.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "❌ Ошибка: заявка не найдена. Завершаю чат.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        # Сохраняем сообщение + вложение (если есть)
        saved_text = None
        # файл/фото
        if message.content_type == "photo" or message.content_type == "document":
            # сохраняем Attachment (файл)
            if message.photo:
                file_id = message.photo[-1].file_id
                file_type = "image"
            else:
                file_id = message.document.file_id
                mt = (message.document.mime_type or "").lower()
                file_type = "image" if mt.startswith("image/") else "document"

            caption = getattr(message, "caption", None)
            # создаём attachment
            try:
                Attachment.create(
                    order=order,
                    uploaded_by=user,
                    file_id=file_id,
                    file_type=file_type,
                    caption=caption
                )
            except Exception as e:
                # логируем/сообщаем, но продолжаем
                bot.send_message(message.chat.id, f"⚠️ Не удалось сохранить вложение: {e}")

            saved_text = caption or "[Вложение]"
            # записываем сообщение с текстом-описанием вложения
            OrderMessage.create(order=order, sender=user, message=saved_text)

        else:
            # текстовое сообщение
            saved_text = (message.text or "").strip()
            OrderMessage.create(order=order, sender=user, message=saved_text)

        # Определяем получателя(ей): отправляем противоположной стороне
        recipients = []
        if user.role == int(UserRole.DRIVER):
            # от водителя — диспетчеру
            if order.dispatcher and order.dispatcher.tg_id:
                recipients.append(order.dispatcher.tg_id)
        elif user.role == int(UserRole.DISPATCHER):
            # от диспетчера — водителю
            if order.driver and order.driver.tg_id:
                recipients.append(order.driver.tg_id)
        else:
            # если менеджер или другое — можно разослать обоим (опционально)
            if order.dispatcher and order.dispatcher.tg_id:
                recipients.append(order.dispatcher.tg_id)
            if order.driver and order.driver.tg_id:
                recipients.append(order.driver.tg_id)

        if not recipients:
            bot.send_message(message.chat.id, "❌ Вторая сторона не назначена или не имеет tg_id"
                                              " — сообщение сохранено в истории.")
            return

        # Отправляем сообщение(я) получателю(ям)
        for tg in set(recipients):
            try:
                bot.send_message(
                    tg,
                    f"💬 Сообщение по заявке #{order.id} от {user.first_name or 'Пользователь'}:\n{saved_text}"
                )
            except Exception:
                bot.send_message(message.chat.id,  "Сообщение не было отправлено")
                pass

        # подтверждаем отправку отправителю

    # ---------- История сообщений ----------
    @bot.callback_query_handler(func=lambda c: c.data.startswith("request_history:"))
    def cb_request_history(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "❌ Неверный идентификатор заявки.")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена.")
            return

        msgs = (
            OrderMessage
            .select()
            .where(OrderMessage.order == order)
            .order_by(OrderMessage.created_at)
        )

        if not msgs:
            bot.send_message(call.message.chat.id, f"📋 История заявки #{order.id} пуста.")
            return

        history_lines = [f"📋 История сообщений по заявке #{order.id}:\n"]
        for m in msgs:
            sender_name = (m.sender.first_name if m.sender else "Неизвестный")
            ts = m.created_at.strftime("%d.%m %H:%M") if getattr(m, "created_at", None) else ""
            text = m.message or "[вложение]"
            history_lines.append(f"[{ts}] {sender_name}: {text}")

        # Если история большая — можно разбить на части; пока отправим одним сообщением
        bot.send_message(call.message.chat.id, "\n".join(history_lines))