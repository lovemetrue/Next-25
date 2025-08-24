# handlers/driver.py
from telebot import TeleBot, types
from datetime import datetime, timedelta
from database.models import User, Order, OrderStatus, UserRole, OrderStatusHistory
from keyboards.request_actions import get_request_actions_keyboard
from keyboards.main_menu import get_main_menu
from peewee import fn


def register_driver_handlers(bot: TeleBot):
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
        dt = getattr(order, "datetime", None) or getattr(order, "datetime", None)
        dt_text = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
        status_text = OrderStatus(order.status).label if order.status is not None else "—"
        driver_name = f"{order.driver.first_name or ''} {(order.driver.last_name or '')}".strip() if order.driver else "—"
        return f"📋 Заявка #{order.id}\n{order.from_addr} → {order.to_addr}\n🕒 {dt_text}\n🚚 Водитель: {driver_name}\n🚦 {status_text}"

    # --- Список активных заявок ---
    @bot.message_handler(func=lambda m: m.text == "📋 Активные заявки")
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

    # --- В пути (фильтр по статусу) ---
    @bot.message_handler(func=lambda m: m.text == "🚛 В пути")
    def driver_enroute_orders(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Доступно только водителю.")
            return

        orders = (Order
                  .select()
                  .where((Order.driver == user) &
                         (Order.status.in_([int(OrderStatus.ENROUTE), int(OrderStatus.ENROUTE_TO_LOADING)])))
                  .order_by(Order.datetime.desc()))
        if not orders:
            bot.send_message(message.chat.id, "📭 У вас нет заявок в маршруте.")
            return

        for o in orders:
            markup = get_request_actions_keyboard(o, "driver")
            bot.send_message(message.chat.id, _fmt_order_brief(o), reply_markup=markup)

    # --- Завершенные ---
    @bot.message_handler(func=lambda m: m.text == "✅ Завершенные")
    def driver_done_orders(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Доступно только водителю.")
            return

        orders = (Order
                  .select()
                  .where((Order.driver == user) & (Order.status == int(OrderStatus.DELIVERED)))
                  .order_by(Order.datetime.desc()))
        if not orders:
            bot.send_message(message.chat.id, "📭 У вас нет завершённых заявок.")
            return

        for o in orders:
            markup = get_request_actions_keyboard(o, "driver")
            bot.send_message(message.chat.id, _fmt_order_brief(o), reply_markup=markup)

    # --- Моя статистика ---
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

    # --- Универсальный обработчик callback для действий водителя ---
    @bot.callback_query_handler(func=lambda c: c.data.split(":", 1)[0] in {
        "accept_request", "reject_request", "start_driving", "loading", "delivered"
    })
    def cb_driver_actions(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        try:
            action, rest = call.data.split(":", 1)
            order_id = int(rest)
        except Exception:
            bot.answer_callback_query(call.id, "❌ Неверные данные callback.")
            return

        user = _ensure_driver(call)
        if not user:
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(call.message.chat.id, "❌ Заявка не найдена.")
            return

        # Проверки доступа: большинство действий доступны только назначенному водителю
        if action in ("start_driving", "loading", "delivered", "reject_request"):
            if not order.driver or order.driver.id != user.id:
                bot.send_message(call.message.chat.id, "❌ Вы не назначены на эту заявку.")
                return

        try:
            if action == "accept_request":
                # Водитель принимает заявку — если заявка без водителя, назначаем; если назначена другому — отказ
                if order.driver and order.driver.id != user.id:
                    bot.send_message(call.message.chat.id, "❌ Эта заявка назначена другому водителю.")
                    return
                order.driver = user
                order.status = int(OrderStatus.CONFIRMED)
                order.save()
                OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="Водитель принял заявку")
                bot.send_message(call.message.chat.id, f"✅ Вы приняли заявку #{order.id}.")
                # уведомляем диспетчера
                if order.dispatcher and order.dispatcher.tg_id:
                    bot.send_message(order.dispatcher.tg_id, f"✅ Водитель {user.first_name} принял заявку #{order.id}.")

            elif action == "reject_request":
                # водитель отказывается — снимаем назначение и возвращаем в NEW
                if order.driver and order.driver.id == user.id:
                    order.driver = None
                    order.status = int(OrderStatus.NEW)
                    order.save()
                    OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="Водитель отклонил заявку")
                    bot.send_message(call.message.chat.id, f"❌ Вы отклонили заявку #{order.id}.")
                    if order.dispatcher and order.dispatcher.tg_id:
                        bot.send_message(order.dispatcher.tg_id, f"❌ Водитель {user.first_name} отклонил заявку #{order.id}.")
                else:
                    bot.send_message(call.message.chat.id, "❌ Невозможно отклонить: вы не назначены на заявку.")

            elif action == "start_driving":
                order.status = int(OrderStatus.ENROUTE)
                order.save()
                OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="В пути")
                bot.send_message(call.message.chat.id, f"🚛 Вы пометили заявку #{order.id} как 'в пути'.")
                if order.dispatcher and order.dispatcher.tg_id:
                    bot.send_message(order.dispatcher.tg_id, f"🚛 Заявка #{order.id} — водитель {user.first_name} в пути.")

            elif action == "loading":
                order.status = int(OrderStatus.LOADING)
                order.save()
                OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="На загрузке")
                bot.send_message(call.message.chat.id, f"📦 Вы пометили заявку #{order.id} как 'на загрузке'.")
                if order.dispatcher and order.dispatcher.tg_id:
                    bot.send_message(order.dispatcher.tg_id, f"📦 Заявка #{order.id} — водитель {user.first_name} сообщает: на загрузке.")

            elif action == "delivered":
                order.status = int(OrderStatus.DELIVERED)
                order.save()
                OrderStatusHistory.create(order=order, by_user=user, status=order.status, note="Доставлено")
                bot.send_message(call.message.chat.id, f"✅ Вы пометили заявку #{order.id} как 'доставлено'.")
                if order.dispatcher and order.dispatcher.tg_id:
                    bot.send_message(order.dispatcher.tg_id, f"✅ Заявка #{order.id} доставлена водителем {user.first_name}.")

            else:
                bot.send_message(call.message.chat.id, "❌ Неизвестное действие.")
                return

        except Exception as e:
            logger.exception("Ошибка при обработке действия водителя:")
            bot.send_message(call.message.chat.id, f"❌ Ошибка при обработке: {e}")

    # --- Если нужно: команда просмотра деталей конкретной заявки для водителя (по ID) ---
    @bot.message_handler(func=lambda m: m.text and m.text.startswith("/order "))
    def cmd_order_detail(message: types.Message):
        try:
            _id = int(message.text.split(maxsplit=1)[1])
        except Exception:
            bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: /order <id>")
            return

        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DRIVER):
            bot.send_message(message.chat.id, "❌ Доступно только водителю.")
            return

        order = Order.get_or_none(Order.id == _id)
        if not order:
            bot.send_message(message.chat.id, "❌ Заявка не найдена.")
            return

        if not order.driver or order.driver.id != user.id:
            bot.send_message(message.chat.id, "❌ Вы не назначены на эту заявку.")
            return

        markup = get_request_actions_keyboard(order, "driver")
        bot.send_message(message.chat.id, _fmt_order_brief(order), reply_markup=markup)

    # регистрация завершена

    @bot.message_handler(func=lambda m: m.text == "🚛 Заявки по статусу")
    def show_status_lists_menu(message: types.Message):
        """
        Показывает диспетчеру 4 кнопки списков по статусу.
        (Добавьте пункт '📂 Заявки по статусу' в главное меню диспетчера.)
        """
        if not _ensure_driver_msg(bot, message):
            return
        bot.send_message(message.chat.id, "Выберите список:", reply_markup=get_status_filter_keyboard_driver())

    @bot.callback_query_handler(func=lambda c: c.data.startswith("list_status_driver:"))
    def cb_list_by_status(call: types.CallbackQuery):
        """
        Выводит список заявок диспетчера по выбранному статусу.
        Использует уже существующий рендер карточки (_send_order_card).
        """
        if not _ensure_driver_call(bot, call):
            return

        try:
            status_code = call.data.split(":", 1)[1]
        except Exception:
            bot.answer_callback_query(call.id, "Некорректный фильтр статуса.")
            return

        status_map = {
            "NEW": int(OrderStatus.NEW),
            "CONFIRMED": int(OrderStatus.CONFIRMED),
            "DELIVERED": int(OrderStatus.DELIVERED),
            "CANCELLED": int(OrderStatus.CANCELLED),
        }
        status_val = status_map.get(status_code)
        if status_val is None:
            bot.answer_callback_query(call.id, "Неизвестный статус.")
            return

        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not user:
            bot.answer_callback_query(call.id, "Ошибка пользователя.")
            return

        orders = (Order
                  .select()
                  .where((Order.driver == user) & (Order.status == status_val))
                  .order_by(Order.datetime.desc()))

        if not orders:
            empty_text = {
                "NEW": "🆕 Новых заявок нет.",
                "CONFIRMED": "✅ Подтвержденных заявок нет.",
                "DELIVERED": "📦 Выполненных заявок нет.",
                "CANCELLED": "❌ Отмененных заявок нет.",
            }[status_code]
            bot.send_message(call.message.chat.id, empty_text)
            bot.answer_callback_query(call.id)
            return

        # Печатаем все карточки
        for order in orders:
            # предполагаем, что у вас уже есть функция _send_order_card(bot, chat_id, order, role="driver")
            _send_order_card(bot, call.message.chat.id, order, role="driver")

        bot.answer_callback_query(call.id)