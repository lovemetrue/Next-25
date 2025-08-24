# handlers/driver.py
from telebot import TeleBot, types
from datetime import datetime, timedelta
from database.models import User, Order, OrderStatus, UserRole, OrderStatusHistory
from keyboards.request_actions import get_request_actions_keyboard
from keyboards.main_menu import get_main_menu
from peewee import fn
from states.request_states import DriverStates
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def register_driver_handlers(bot: TeleBot):

     # ===================== ВСПОМОГАТЕЛЬНО =====================

    def _ensure_driver_call(bot, call: types.CallbackQuery) -> bool:
        """
        Проверяет, что инициатор коллбэка — диспетчер.
        Возвращает True/False, при False отправляет ответ в callback_query.
        """
        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.answer_callback_query(call.id, "❌ Команда доступна только водителю.")
            return False
        return True

    def _ensure_driver_msg(bot, message: types.Message) -> bool:
        """
        Проверяет, что отправитель сообщения — диспетчер.
        Возвращает True/False, при False отвечает в чат.
        """
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Команда доступна только водителю.")
            return False
        return True

    def _ensure_driver(call_or_msg):
        """Вернуть User, если это водитель; иначе отправить сообщение/answer и вернуть None."""
        tg_id = call_or_msg.from_user.id if hasattr(call_or_msg, "from_user") else None
        if tg_id is None:
            return None
        user = User.get_or_none(User.tg_id == tg_id)
        if not user or user.role != int(UserRole.DRIVER):
            # Если это callback_query — у объекта есть answer_callback_query
            if hasattr(call_or_msg, "id"):  # callback
                bot.answer_callback_query(call_or_msg.id, "❌ Команда доступна только водителю.")
            else:
                bot.send_message(call_or_msg.chat.id, "❌ Команда доступна только водителю.")
            return None
        return user

    def _fmt_order_brief(order: Order) -> str:
        dt = getattr(order, "datetime", None) or getattr(order, "exec_datetime", None)
        dt_text = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
        status_text = OrderStatus(order.status).label if order.status is not None else "—"
        driver_name = f"{order.driver.first_name or ''} {(order.driver.last_name or '')}".strip() if order.driver else "—"
        return f"📋 Заявка #{order.id}\n{order.from_addr} → {order.to_addr}\n🕒 {dt_text}\n🚚 Водитель: {driver_name}\n🚦 {status_text}"

    # --- Список активных заявок ---
    @bot.message_handler(func=lambda m: m.text == "📆 Активные заявки")
    def driver_active_orders(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Доступно только водителю.")
            return

        orders = (Order
                  .select()
                  .where((Order.driver == user) &
                         (Order.status.not_in([int(OrderStatus.DELIVERED), int(OrderStatus.CANCELLED)])))
                  .order_by(Order.datetime.desc()))
        if not orders:
            bot.send_message(message.chat.id, "📭 У вас нет активных заявок.")
            return

        for o in orders:
            markup = get_request_actions_keyboard(o, "driver")
            bot.send_message(message.chat.id, _fmt_order_brief(o), reply_markup=markup)


    #### Статистика
    @bot.message_handler(func=lambda m: m.text == "📊 Моя статистика")
    def driver_stats(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Доступно только водителю.")
            return

        total = Order.select().where(Order.driver == user).count()
        by_status_q = (Order
                       .select(Order.status, fn.COUNT(Order.id).alias("cnt"))
                       .where(Order.driver == user)
                       .group_by(Order.status))
        status_counts = {OrderStatus(r.status).label: r.cnt for r in by_status_q}

        delivered_week = (Order.select()
                          .where((Order.driver == user) &
                                 (Order.status == int(OrderStatus.DELIVERED)) &
                                 (Order.datetime >= datetime.now() - timedelta(days=7)))
                          .count())

        lines = [
            f"📊 Ваша статистика",
            f"Всего заявок: {total}",
            ""
        ]
        if status_counts:
            for k, v in status_counts.items():
                lines.append(f"• {k}: {v}")
        else:
            lines.append("• нет данных")
        lines += [
            "",
            f"✅ Доставлено за 7 дней: {delivered_week}"
        ]
        bot.send_message(message.chat.id, "\n".join(lines))



    # ===================== ЗАВЕРШЕННЫЕ ЗАЯВКИ =====================
    @bot.message_handler(func=lambda m: m.text == "🚛 Завершенные заявки")
    def driver_completed_orders(message: types.Message):
        user = _ensure_driver(message)
        if not user:
            return

        # Заявки с статусом DELIVERED или CANCELLED
        orders = (Order
                  .select()
                  .where((Order.driver == user) &
                         (Order.status.in_([int(OrderStatus.DELIVERED), int(OrderStatus.CANCELLED)])))
                  .order_by(Order.datetime.desc())
                  .limit(20))  # Ограничим количество для избежания перегрузки

        if not orders:
            bot.send_message(message.chat.id, "📭 У вас нет завершенных заявок.")
            return

        for order in orders:
            # Для завершенных заявок не показываем actions keyboard
            bot.send_message(message.chat.id, _fmt_order_brief(order))

        ##### EDITION OF ORDERS
        # === Блок: проверка импортов состояний (если DriverStates лежит в другом модуле) ===
        try:
            from states.request_states import DriverStates
        except Exception:
            try:
                from states.driver_states import DriverStates
            except Exception:
                # Если и тут нет — убедитесь, что у вас есть StateGroup с именем DriverStates,
                # содержащие waiting_comment и waiting_photo.
                DriverStates = None

    # === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

    def _ensure_driver_call(call: types.CallbackQuery):
        """
        Вернуть объект User, если инициатор callback_query — водитель.
        В противном случае отправляет answer_callback_query и возвращает None.
        """
        from_user = getattr(call, "from_user", None)
        if not from_user:
            try:
                bot.answer_callback_query(call.id, "❌ Неверный запрос.")
            except Exception:
                pass
            return None
        user = User.get_or_none(User.tg_id == from_user.id)
        if not user or int(user.role) != int(UserRole.DRIVER):
            try:
                bot.answer_callback_query(call.id, "❌ Команда доступна только водителю.")
            except Exception:
                pass
            return None
        return user

    def _ensure_driver_msg(message: types.Message):
        """
        Вернуть объект User, если отправитель message — водитель.
        В противном случае отправляет сообщение в чат и возвращает None.
        """
        from_user = getattr(message, "from_user", None)
        if not from_user:
            return None
        user = User.get_or_none(User.tg_id == from_user.id)
        if not user or int(user.role) != int(UserRole.DRIVER):
            try:
                bot.send_message(message.chat.id, "❌ Команда доступна только водителю.")
            except Exception:
                pass
            return None
        return user

    def _get_order_or_notify_chat(chat_id: int, order_id: int):
        """
        Получить заявку по id или отправить сообщение в чат (chat_id), если не найдена.
        """
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            try:
                bot.send_message(chat_id, "❌ Заявка не найдена.")
            except Exception:
                pass
        return order

    def _get_order_or_notify_callback(call: types.CallbackQuery, order_id: int):
        """
        Получить заявку по id или ответить в callback (call) что не найдена.
        """
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            try:
                bot.answer_callback_query(call.id, "❌ Заявка не найдена.")
            except Exception:
                pass
        return order

    # Мэппинг человекочитаемых названий для кнопок (используется при показе вариантов)
    _STATUS_LABELS = {
        int(OrderStatus.ENROUTE_TO_LOADING): "🚚 В путь на загрузку",
        int(OrderStatus.LOADING): "📦 На загрузке",
        int(OrderStatus.ENROUTE): "🚚 В путь",
        int(OrderStatus.DELIVERED): "✅ Доставлено",
        int(OrderStatus.CONFIRMED): "✅ Подтверждена",
        int(OrderStatus.NEW): "🆕 Новая",
        int(OrderStatus.CANCELLED): "❌ Отменена",
    }

    def _allowed_transitions_for(status_value: int) -> list[int]:
        """
        Возвращает список допустимых целевых статусов для данного текущего статуса (для водителя).
        Последовательность: NEW -> CONFIRMED -> ENROUTE_TO_LOADING -> LOADING -> ENROUTE -> DELIVERED
        (Дополнительно допускаем некоторые упрощённые переходы.)
        """
        NEW = int(OrderStatus.NEW)
        CONFIRMED = int(OrderStatus.CONFIRMED)
        ENROUTE_TO_LOADING = int(OrderStatus.ENROUTE_TO_LOADING)
        LOADING = int(OrderStatus.LOADING)
        ENROUTE = int(OrderStatus.ENROUTE)
        DELIVERED = int(OrderStatus.DELIVERED)
        CANCELLED = int(OrderStatus.CANCELLED)

        mapping = {
            NEW: [CONFIRMED],
            CONFIRMED: [ENROUTE_TO_LOADING, ENROUTE],
            # можно отправиться сразу в ENROUTE или сначала в ENROUTE_TO_LOADING
            ENROUTE_TO_LOADING: [LOADING],
            LOADING: [ENROUTE],
            ENROUTE: [DELIVERED],
        }
        return mapping.get(int(status_value), [])

    # === ХЕНДЛЕР: показать клавиатуру выбора статуса для водителя ===
    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_change_status:"))
    def cb_driver_change_status(call: types.CallbackQuery):
        """
        Показывает водителю inline-клавиатуру с допустимыми переходами статуса для выбранной заявки.
        callback_data ожидается: "driver_change_status:{order_id}"
        """
        user = _ensure_driver_call(call)
        if not user:
            return

        # получить order_id
        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
            return

        order = _get_order_or_notify_callback(call, order_id)
        if not order:
            return

        # проверяем, что текущий водитель назначен на заявку
        if not order.driver or int(order.driver.id) != int(user.id):
            bot.answer_callback_query(call.id, "Заявка не найдена или недоступна.")
            return

        # формируем доступные переходы
        targets = _allowed_transitions_for(int(order.status))
        if not targets:
            bot.answer_callback_query(call.id, "Нет доступных переходов статуса для этой заявки.")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for ts in targets:
            label = _STATUS_LABELS.get(ts, f"Статус {ts}")
            # callback: driver_set_status:{order_id}:{new_status}
            markup.add(types.InlineKeyboardButton(label, callback_data=f"driver_set_status:{order.id}:{ts}"))

        # возможно полезно добавить кнопку Отмена / Вернуться
        markup.add(types.InlineKeyboardButton("⬅️ Отмена", callback_data=f"driver_cancel_action:{order.id}"))

        try:
            bot.send_message(call.message.chat.id, "Выберите новый статус:", reply_markup=markup)
        except Exception:
            bot.answer_callback_query(call.id, "Не удалось показать клавиатуру.")
            return

        bot.answer_callback_query(call.id)

    # === ХЕНДЛЕР: установить выбранный статус ===
    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_set_status:"))
    def cb_driver_set_status(call: types.CallbackQuery):
        """
        Обрабатывает смену статуса водителем.
        callback_data: "driver_set_status:{order_id}:{new_status_int}"
        Проверяет принадлежность водителю и допустимость перехода.
        """
        user = _ensure_driver_call(call)
        if not user:
            return

        parts = call.data.split(":")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Ошибка данных.")
            return

        try:
            order_id = int(parts[1])
            new_status = int(parts[2])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка данных.")
            return

        order = _get_order_or_notify_callback(call, order_id)
        if not order:
            return

        if not order.driver or int(order.driver.id) != int(user.id):
            bot.answer_callback_query(call.id, "Заявка не найдена или недоступна.")
            return

        valid_targets = _allowed_transitions_for(int(order.status))
        if new_status not in valid_targets:
            bot.answer_callback_query(call.id, "Недопустимое изменение статуса.")
            return

        # выполняем обновление
        prev_status = int(order.status)
        order.status = new_status
        order.save()

        status_name = _STATUS_LABELS.get(new_status, str(new_status))
        OrderStatusHistory.create(
            order=order,
            by_user=user,
            status=new_status,
            note=f"Водитель изменил статус на: {status_name}"
        )

        # уведомляем диспетчера (если есть tg_id)
        try:
            if order.dispatcher and getattr(order.dispatcher, "tg_id", None):
                bot.send_message(order.dispatcher.tg_id,
                                 f"🚦 В заявке #{order.id} водитель изменил статус на: {status_name}")
        except Exception:
            pass

        # подтверждение водителю
        bot.answer_callback_query(call.id, f"Статус изменён на: {status_name}")

        # пытаемся обновить исходное сообщение с карточкой (если возможно)
        try:
            bot.edit_message_text(
                _fmt_order_brief(order),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_request_actions_keyboard(order, "driver")
            )
        except Exception:
            # fallback: высылаем новую карточку
            try:
                bot.send_message(call.message.chat.id, _fmt_order_brief(order),
                                 reply_markup=get_request_actions_keyboard(order, "driver"))
            except Exception:
                pass

    # === ХЕНДЛЕР: добавить комментарий (через состояние) ===
    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_add_comment:"))
    def cb_driver_add_comment(call: types.CallbackQuery):
        """
        Переводит водителя в состояние ожидания комментария.
        callback_data: "driver_add_comment:{order_id}"
        """
        user = _ensure_driver_call(call)
        if not user:
            return

        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
            return

        order = _get_order_or_notify_callback(call, order_id)
        if not order:
            return

        if not order.driver or int(order.driver.id) != int(user.id):
            bot.answer_callback_query(call.id, "Заявка не найдена или недоступна.")
            return

        if DriverStates is None:
            bot.answer_callback_query(call.id, "Состояния не настроены (DriverStates отсутствует).")
            return

        # переводим в состояние
        bot.set_state(call.from_user.id, DriverStates.waiting_comment, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order.id

        bot.send_message(call.message.chat.id, "Введите ваш комментарий (или /stop для отмены):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=(DriverStates.waiting_comment if DriverStates else None), content_types=["text"])
    def driver_comment_step(message: types.Message):
        """
        Обрабатывает введённый комментарий водителя, сохраняет в историю и уведомляет диспетчера.
        """
        if DriverStates is None:
            bot.send_message(message.chat.id, "Состояния не настроены.")
            return

        user = _ensure_driver_msg(message)
        if not user:
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        # отмена
        if (message.text or "").strip().lower() in ("/stop", "отмена", "выйти"):
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.send_message(message.chat.id, "Операция отменена.")
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = _get_order_or_notify_chat(message.chat.id, order_id) if order_id else None
        if not order or not order.driver or int(order.driver.id) != int(user.id):
            bot.send_message(message.chat.id, "Заявка не найдена или недоступна.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        text = (message.text or "").strip()
        OrderStatusHistory.create(order=order, by_user=user, status=order.status,
                                  note=f"Комментарий водителя: {text}")

        try:
            if order.dispatcher and getattr(order.dispatcher, "tg_id", None):
                bot.send_message(order.dispatcher.tg_id,
                                 f"💬 Комментарий от водителя по заявке #{order.id}:\n\n{text}")
        except Exception:
            pass

        bot.send_message(message.chat.id, "✅ Комментарий добавлен.")
        bot.delete_state(message.from_user.id, message.chat.id)

    # === ХЕНДЛЕР: прикрепить фото (через состояние) ===
    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_add_photo:"))
    def cb_driver_add_photo(call: types.CallbackQuery):
        """
        Переводит водителя в состояние ожидания фото/документа.
        callback_data: "driver_add_photo:{order_id}"
        """
        user = _ensure_driver_call(call)
        if not user:
            return

        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
            return

        order = _get_order_or_notify_callback(call, order_id)
        if not order:
            return

        if not order.driver or int(order.driver.id) != int(user.id):
            bot.answer_callback_query(call.id, "Заявка не найдена или недоступна.")
            return

        if DriverStates is None:
            bot.answer_callback_query(call.id, "Состояния не настроены (DriverStates отсутствует).")
            return

        bot.set_state(call.from_user.id, DriverStates.waiting_photo, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order.id

        bot.send_message(call.message.chat.id, "Прикрепите фото или документ к заявке (или /stop для отмены):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=(DriverStates.waiting_photo if DriverStates else None),
                         content_types=["photo", "document", "text"])
    def driver_photo_step(message: types.Message):
        """
        Обрабатывает загруженное фото/документ, сохраняет file_id в Attachment (если есть модель),
        добавляет запись в историю и пересылает файл диспетчеру (если подключён).
        """
        if DriverStates is None:
            bot.send_message(message.chat.id, "Состояния не настроены.")
            return

        user = _ensure_driver_msg(message)
        if not user:
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        # отмена
        if (message.content_type == "text") and (
                (message.text or "").strip().lower() in ("/stop", "отмена", "выйти")):
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.send_message(message.chat.id, "Операция отменена.")
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = _get_order_or_notify_chat(message.chat.id, order_id) if order_id else None
        if not order or not order.driver or int(order.driver.id) != int(user.id):
            bot.send_message(message.chat.id, "Заявка не найдена или недоступна.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        # извлекаем вложение
        file_id = None
        file_type = None
        caption = None
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "image"
            caption = getattr(message, "caption", None)
        elif message.document:
            file_id = message.document.file_id
            mt = (message.document.mime_type or "").lower()
            file_type = "image" if mt.startswith("image/") else "document"
            caption = getattr(message, "caption", None)
        else:
            bot.send_message(message.chat.id, "❌ Прикрепите фото или документ.")
            return

        # Сохраняем в Attachment, если модель есть (попытка)
        try:
            Attachment.create(order=order, uploaded_by=user, file_id=file_id, file_type=file_type, caption=caption)
        except Exception:
            # если нет модели Attachment — просто логируем и продолжаем
            logger = logging.getLogger(__name__)
            logger.debug("Attachment не сохранён (возможно, модель не определена) или произошла ошибка.")

        # Запись в историю
        OrderStatusHistory.create(order=order, by_user=user, status=order.status,
                                  note=f"Водитель добавил файл: {caption or '[файл]'}")

        # Пересылка диспетчеру
        try:
            if order.dispatcher and getattr(order.dispatcher, "tg_id", None):
                if file_type == "image":
                    bot.send_photo(order.dispatcher.tg_id, file_id,
                                   caption=f"Фото от водителя по заявке #{order.id}\n{caption or ''}")
                else:
                    bot.send_document(order.dispatcher.tg_id, file_id,
                                      caption=f"Файл от водителя по заявке #{order.id}\n{caption or ''}")
        except Exception:
            pass

        bot.delete_state(message.from_user.id, message.chat.id)

    # === ХЕНДЛЕР: принять заявку ===
    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_accept:"))
    def cb_driver_accept(call: types.CallbackQuery):
        """
        Принятие заявки водителем (callback_data = "driver_accept:{order_id}").
        Только для заявок в статусе NEW.
        Назначает водителя на заявку и переводит статус в CONFIRMED.
        """
        user = _ensure_driver_call(call)
        if not user:
            return

        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
            return

        order = _get_order_or_notify_callback(call, order_id)
        if not order:
            return

        # проверка статуса
        if int(order.status) != int(OrderStatus.NEW):
            bot.answer_callback_query(call.id, "Заявку нельзя принять — она уже не в статусе NEW.")
            return

        # проверка, не назначен ли другой водитель
        if order.driver and int(order.driver.id) != int(user.id):
            bot.answer_callback_query(call.id, "Заявка уже назначена другому водителю.")
            return

        order.driver = user
        order.status = int(OrderStatus.CONFIRMED)
        order.save()

        OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="Водитель принял заявку")

        # уведомление диспетчеру
        try:
            if order.dispatcher and getattr(order.dispatcher, "tg_id", None):
                bot.send_message(order.dispatcher.tg_id,
                                 f"🚚 Водитель {user.first_name or ''} принял заявку #{order.id}")
        except Exception:
            pass

        bot.answer_callback_query(call.id, "✅ Заявка принята.")

        # Обновляем исходное сообщение с карточкой (если возможно)
        try:
            bot.edit_message_text(
                _fmt_order_brief(order),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=get_request_actions_keyboard(order, "driver")
            )
        except Exception:
            # fallback — отправим обновлённую карточку
            try:
                bot.send_message(call.message.chat.id, _fmt_order_brief(order),
                                 reply_markup=get_request_actions_keyboard(order, "driver"))
            except Exception:
                pass