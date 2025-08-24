# handlers/dispatcher.py
from telebot import TeleBot, types
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from app.database.models import (
    User, Order, OrderStatus, UserRole, OrderPrefix, Attachment, OrderStatusHistory
)
from app.keyboards.request_actions import (
    get_prefix_keyboard,
    get_drivers_keyboard,
    get_request_filter_keyboard,
    get_request_actions_keyboard,
    get_status_filter_keyboard
)
import logging
from app.keyboards.main_menu import get_main_menu
from peewee import fn
from app.states.request_states import RequestsStates
from handlers.chat import register_chat_handlers


PREFIX_MAP = {
    "с ндс": OrderPrefix.WITH_VAT,
    "без ндс": OrderPrefix.WITHOUT_VAT,
    "нал": OrderPrefix.CASH,
}


def register_dispatcher_handlers(bot: TeleBot):
    # ----------------- ВСПОМОГАТЕЛЬНОЕ -----------------
    def _get_order_or_notify(bot: TeleBot, chat_id: int, order_id: int) -> Order | None:
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(chat_id, "❌ Заявка не найдена.")
        return order

    def _can_edit(order: Order) -> bool:
        return int(order.status) in (int(OrderStatus.NEW), int(OrderStatus.CONFIRMED))

    def _send_actions(bot: TeleBot, chat_id: int, order: Order, title: str | None = None):
        markup = get_request_actions_keyboard(order, role="dispatcher", include_chat=True)
        text = title or f"✏️ Действия для заявки #{order.id}:"
        bot.send_message(chat_id, text, reply_markup=markup)

    # def _parse_order_id_from_text(text: str) -> int | None:
    #     # резервная функция (если где-то понадобится)
    #     try:
    #         hash_pos = text.find("#")
    #         if hash_pos == -1:
    #             return None
    #         num = ""
    #         for ch in text[hash_pos + 1:]:
    #             if ch.isdigit():
    #                 num += ch
    #             else:
    #                 break
    #         return int(num) if num else None
    #     except Exception:
    #         return None
    #
    # def _status_to_keyboard_code(status: int) -> str:
    #     mapping = {
    #         OrderStatus.NEW: "new",
    #         OrderStatus.CONFIRMED: "confirmed",
    #         OrderStatus.ENROUTE_TO_LOADING: "enroute_to_loading",
    #         OrderStatus.LOADING: "loading",
    #         OrderStatus.ENROUTE: "in_transit",
    #         OrderStatus.DELIVERED: "delivered",
    #         OrderStatus.CANCELLED: "cancelled",
    #     }
    #     return mapping.get(OrderStatus(status), "new")
    #
    # STATUS_TEXT_TO_ENUM = {
    #     "🆕 Новые": OrderStatus.NEW,
    #     "✅ Подтвержденные": OrderStatus.CONFIRMED,
    #     "🚛 В пути": OrderStatus.ENROUTE,
    #     "📦 На загрузке": OrderStatus.LOADING,
    #     "✅ Доставленные": OrderStatus.DELIVERED,
    #     "❌ Отмененные": OrderStatus.CANCELLED,
    # }

    def _format_order_brief(o: Order) -> str:
        # здесь используем поле datetime (как в твоих моделях)
        base = (f"🚛 Заявка #{o.id}\n"
                f"Статус: {OrderStatus(o.status).label}\n"
                f"{o.from_addr} → {o.to_addr}\n"
                f"🕒 {o.datetime.strftime('%d.%m.%Y %H:%M')}")
        if o.status == int(OrderStatus.CANCELLED) and o.cancel_reason:
            base += f"\n🚫 Причина отмены: {o.cancel_reason}"
        return base



    # def _show_dispatcher_menu(bot: TeleBot, chat_id: int):
    #     """Показать главное меню диспетчера (создать заявку, водители, статистика)."""
    #     bot.send_message(chat_id, "Главное меню диспетчера:", reply_markup=get_main_menu("dispatcher"))

    def _extract_attachment_from_message(message: types.Message):
        """
        Возвращает dict с данными вложения или None.
        Формат: {"file_id": str, "file_type": "image"|"document", "caption": Optional[str]}
        """
        # Фото
        if message.photo:
            return {
                "file_id": message.photo[-1].file_id,
                "file_type": "image",
                "caption": getattr(message, "caption", None)
            }

        # Документ
        if message.document:
            mt = (message.document.mime_type or "").lower()
            is_image = mt.startswith("image/")
            return {
                "file_id": message.document.file_id,
                "file_type": "image" if is_image else "document",
                "caption": getattr(message, "caption", None)
            }

        return None

    # --------------------- CREATION FLOW ---------------------

    @bot.message_handler(func=lambda m: m.text == "➕ Создать заявку")
    def create_order_start(message: types.Message):
        bot.delete_state(message.from_user.id, message.chat.id)
        bot.send_message(message.chat.id, "Выберите префикс заявки:", reply_markup=get_prefix_keyboard())
        bot.set_state(message.from_user.id, "order_prefix", message.chat.id)

    @bot.message_handler(state="order_prefix")
    def order_prefix_step(message: types.Message):
        text = (message.text or "").strip().lower()
        if text not in PREFIX_MAP:
            bot.send_message(message.chat.id, "❌ Выберите префикс с клавиатуры.")
            return

        bot.add_data(message.from_user.id, message.chat.id, order_prefix=int(PREFIX_MAP[text]))
        drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True))
        bot.send_message(message.chat.id, "Выберите водителя (или нажмите ❌ Без водителя):",
                         reply_markup=get_drivers_keyboard(drivers))
        bot.set_state(message.from_user.id, "order_driver", message.chat.id)

    @bot.message_handler(state="order_driver")
    def order_driver_step(message: types.Message):
        raw = (message.text or "").strip()

        if raw == "❌ Без водителя":
            bot.add_data(message.from_user.id, message.chat.id, driver_id=None)
        else:
            driver = None
            if "(" in raw and ")" in raw and "@" in raw:
                try:
                    uname = raw.split("(")[1].split(")")[0].strip()
                    if uname.startswith("@"):
                        uname = uname[1:]
                    driver = User.get_or_none((User.username == uname) & (User.role == int(UserRole.DRIVER)))
                except Exception:
                    driver = None
            if not driver:
                parts = raw.split(" (@")[0].split()
                first = parts[0] if parts else ""
                last = parts[1] if len(parts) > 1 else None
                q = User.select().where((User.role == int(UserRole.DRIVER)) & (User.first_name == first))
                if last:
                    q = q.where(User.last_name == last)
                driver = q.first()

            bot.add_data(message.from_user.id, message.chat.id, driver_id=(driver.id if driver else None))

        bot.send_message(message.chat.id, "Введите адрес отправления (Точка А):")
        bot.set_state(message.from_user.id, "order_from_addr", message.chat.id)

    @bot.message_handler(state="order_from_addr")
    def order_from_step(message: types.Message):
        txt = (message.text or "").strip()
        if not txt:
            bot.send_message(message.chat.id, "❌ Укажите адрес отправления.")
            return
        bot.add_data(message.from_user.id, message.chat.id, from_addr=txt)
        bot.send_message(message.chat.id, "Введите адрес назначения (Точка Б):")
        bot.set_state(message.from_user.id, "order_to_addr", message.chat.id)

    @bot.message_handler(state="order_to_addr")
    def order_to_step(message: types.Message):
        txt = (message.text or "").strip()
        if not txt:
            bot.send_message(message.chat.id, "❌ Укажите адрес назначения.")
            return
        bot.add_data(message.from_user.id, message.chat.id, to_addr=txt)
        # Сразу к типу груза — шаг даты убран
        bot.send_message(message.chat.id, "Введите тип груза (опционально, можно оставить пустым):")
        bot.set_state(message.from_user.id, "order_cargo", message.chat.id)

    @bot.message_handler(state="order_cargo")
    def order_cargo_step(message: types.Message):
        cargo = (message.text or "").strip() or None
        bot.add_data(message.from_user.id, message.chat.id, cargo_type=cargo)
        bot.send_message(message.chat.id, "Введите вес/объём (опционально):")
        bot.set_state(message.from_user.id, "order_weight_volume", message.chat.id)

    @bot.message_handler(state="order_weight_volume")
    def order_weight_volume_step(message: types.Message):
        wv = (message.text or "").strip() or None
        bot.add_data(message.from_user.id, message.chat.id, weight_volume=wv)
        bot.send_message(message.chat.id, "Комментарий (опционально):")
        bot.set_state(message.from_user.id, "order_comment", message.chat.id)

    @bot.message_handler(state="order_comment")
    def order_comment_step(message: types.Message):
        comment = (message.text or "").strip() or None
        bot.add_data(message.from_user.id, message.chat.id, comment=comment)
        bot.send_message(
            message.chat.id,
            "Прикрепите файл (фото/документ) или напишите «пропустить».",
        )
        bot.set_state(message.from_user.id, "order_file", message.chat.id)

    @bot.message_handler(state="order_file", content_types=["text"])
    def order_file_skip_or_unknown(message: types.Message):
        text = (message.text or "").strip().lower()
        if text in ("пропустить", "skip", "нет", "без файла"):
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                _create_order_from_state(bot, message, data, first_file=None)
        else:
            bot.send_message(message.chat.id, "Если файла нет — напишите «пропустить», либо пришлите фото/документ.")

    @bot.message_handler(state="order_file", content_types=["photo", "document"])
    def order_file_step(message: types.Message):
        file = _extract_attachment_from_message(message)
        if file is None:
            bot.send_message(message.chat.id, "❌ Неподдерживаемый тип файла. Пришлите изображение или документ.")
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            _create_order_from_state(bot, message, data, first_file=file)

    def _create_order_from_state(bot: TeleBot, message: types.Message, data: dict, first_file: dict | None):
        try:
            prefix = data.get("order_prefix")
            from_addr = data.get("from_addr")
            to_addr = data.get("to_addr")
            exec_dt = data.get("datetime") or datetime.now()

            if not all([prefix, from_addr, to_addr]):
                bot.send_message(message.chat.id, "⚠️ Не все данные заполнены. Начните заново: «➕ Создать заявку».")
                return

            dispatcher = User.get_or_none(User.tg_id == message.from_user.id)
            if not dispatcher:
                bot.send_message(message.chat.id, "❌ Ошибка: вы не зарегистрированы как диспетчер.")
                return

            driver_id = data.get("driver_id")
            driver = User.get_by_id(driver_id) if driver_id else None

            order = Order.create(
                dispatcher=dispatcher,
                driver=driver,
                prefix=int(prefix),
                from_addr=from_addr,
                to_addr=to_addr,
                datetime=exec_dt,
                cargo_type=data.get("cargo_type"),
                weight_volume=data.get("weight_volume"),
                comment=data.get("comment"),
                status=int(OrderStatus.NEW),
            )

            if first_file:
                Attachment.create(
                    order=order,
                    uploaded_by=dispatcher,
                    file_id=first_file["file_id"],
                    file_type=first_file["file_type"],
                    caption=first_file.get("caption"),
                )

            bot.send_message(
                message.chat.id,
                f"✅ Заявка #{order.id} создана: «{from_addr} → {to_addr}»\n"
                f"🕒 Дата: {exec_dt.strftime('%d.%m.%Y %H:%M')}\n"
                f"🚛 Водитель: {(driver.first_name + (' ' + (driver.last_name or ''))).strip() if driver else 'не назначен'}"
            )

            bot.delete_state(message.from_user.id, message.chat.id)
            bot.send_message(message.chat.id, f"Ваше меню:", reply_markup=get_main_menu("dispatcher"))

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка при создании заявки: {e}")
            raise

    # ====== 👨‍💼 ВОДИТЕЛИ (список и активные заявки) ======
    @bot.message_handler(func=lambda m: m.text == "👨‍💼 Водители")
    def list_drivers(message: types.Message):
        dispatcher = _ensure_dispatcher(bot, message.chat.id, message.from_user.id)
        if not dispatcher:
            return

        drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True)).order_by(
            User.first_name, User.last_name)
        if not drivers:
            bot.send_message(message.chat.id, "Пока нет зарегистрированных водителей.")
            return

        for d in drivers:
            active_cnt = (Order.select()
                          .where((Order.driver == d) &
                                 (Order.status.not_in([int(OrderStatus.DELIVERED), int(OrderStatus.CANCELLED)])))
                          .count())
            uname = f"@{d.username}" if d.username else ""
            caption = f"👨‍💼 {d.first_name or ''} {d.last_name or ''} {uname}".strip()
            caption += f"\n🚚 Активных заявок: {active_cnt}"

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📦 Активные заявки", callback_data=f"driver_orders:{d.id}"))
            bot.send_message(message.chat.id, caption, reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("driver_orders:"))
    def cb_driver_orders(call: types.CallbackQuery):
        try:
            driver_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора.")
            return

        driver = User.get_or_none(User.id == driver_id)
        if not driver:
            bot.answer_callback_query(call.id, "Водитель не найден.")
            return

        orders = (Order.select()
                  .where((Order.driver == driver) &
                         (Order.status.not_in([int(OrderStatus.DELIVERED), int(OrderStatus.CANCELLED)])))
                  .order_by(Order.datetime))
        if not orders:
            bot.send_message(call.message.chat.id,
                             f"У водителя {driver.first_name or ''} {driver.last_name or ''} нет активных заявок.")
            return

        for o in orders:
            markup = get_request_actions_keyboard(o, "dispatcher")
            bot.send_message(
                call.message.chat.id,
                _format_order_brief(o),
                reply_markup=markup
            )
        bot.answer_callback_query(call.id)

    # ====== 📊 СТАТИСТИКА (для диспетчера) ======
    @bot.message_handler(func=lambda m: m.text == "📊 Статистика")
    def dispatcher_stats(message: types.Message):
        dispatcher = _ensure_dispatcher(bot, message.chat.id, message.from_user.id)
        if not dispatcher:
            return

        total = Order.select().where(Order.dispatcher == dispatcher).count()
        by_status = (Order
                     .select(Order.status, fn.COUNT(Order.id).alias("cnt"))
                     .where(Order.dispatcher == dispatcher)
                     .group_by(Order.status))

        status_counts = {OrderStatus(s.status).label: s.cnt for s in by_status}
        delivered_week = (Order.select()
                          .where((Order.dispatcher == dispatcher) &
                                 (Order.status == int(OrderStatus.DELIVERED)) &
                                 (Order.datetime >= datetime.now() - timedelta(days=7)))
                          .count())
        delivered_month = (Order.select()
                           .where((Order.dispatcher == dispatcher) &
                                  (Order.status == int(OrderStatus.DELIVERED)) &
                                  (Order.datetime >= datetime.now() - timedelta(days=30)))
                           .count())

        top_drivers = (Order
                       .select(Order.driver, fn.COUNT(Order.id).alias("cnt"))
                       .where((Order.dispatcher == dispatcher) & (Order.status == int(OrderStatus.DELIVERED)) & (
            Order.driver.is_null(False)))
                       .group_by(Order.driver)
                       .order_by(fn.COUNT(Order.id).desc())
                       .limit(5))

        lines = [
            f"📊 Статистика по вашим заявкам",
            f"Всего заявок: {total}",
            "",
            "По статусам:",
        ]
        if status_counts:
            for name, cnt in status_counts.items():
                lines.append(f"• {name}: {cnt}")
        else:
            lines.append("• нет данных")

        lines += [
            "",
            f"✅ Доставлено за 7 дней: {delivered_week}",
            f"✅ Доставлено за 30 дней: {delivered_month}",
            "",
            "🏆 Топ водителей (доставок):"
        ]
        if top_drivers:
            for row in top_drivers:
                d = row.driver
                lines.append(f"• {d.first_name or ''} {d.last_name or ''} — {row.cnt}")
        else:
            lines.append("• нет данных")

        bot.send_message(message.chat.id, "\n".join(lines))

    # ====== МОИ ЗАЯВКИ (inline фильтры: Неделя / Все) ======
    @bot.message_handler(func=lambda m: m.text == "📋 Мои заявки")
    def show_my_orders_menu(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Ошибка: вы не зарегистрированы.")
            return
        if user.role != int(UserRole.DISPATCHER):
            bot.send_message(message.chat.id, "❌ Эта функция доступна только диспетчеру.")
            return

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🗓 За неделю", callback_data="orders_week"),
            InlineKeyboardButton("📊 Все", callback_data="orders_all")
        )
        bot.send_message(message.chat.id, "Выберите период:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: c.data == "orders_week")
    def cb_orders_week(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not user:
            bot.send_message(call.message.chat.id, "❌ Ошибка: пользователь не найден.")
            return

        week_ago = datetime.now() - timedelta(days=7)
        orders = (Order
                  .select()
                  .where((Order.dispatcher == user) & (Order.datetime >= week_ago))
                  .order_by(Order.datetime.desc()))

        if not orders:
            bot.send_message(call.message.chat.id, "📭 За последнюю неделю заявок нет.")
            return

        for order in orders:
            _send_order_card(bot, call.message.chat.id, order, role="dispatcher")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "orders_all")
    def cb_orders_all(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not user:
            bot.send_message(call.message.chat.id, "❌ Ошибка: пользователь не найден.")
            return

        orders = (Order
                  .select()
                  .where(Order.dispatcher == user)
                  .order_by(Order.datetime.desc()))

        if not orders:
            bot.send_message(call.message.chat.id, "📭 У вас ещё нет заявок.")
            return

        for order in orders:
            _send_order_card(bot, call.message.chat.id, order, role="dispatcher")
        bot.answer_callback_query(call.id)

    def _send_order_card(bot: TeleBot, chat_id: int, order: Order, role="dispatcher"):
        status_map = {
            OrderStatus.NEW: "🆕 Новая",
            OrderStatus.CONFIRMED: "✅ Подтверждена",
            OrderStatus.ENROUTE: "🚛 В пути",
            OrderStatus.LOADING: "📦 На загрузке",
            OrderStatus.DELIVERED: "✅ Доставлена",
            OrderStatus.CANCELLED: "❌ Отменена",
        }
        status_text = status_map.get(order.status, "❔ Неизвестно")

        text = (
            f"📋 Заявка #{order.id}\n"
            f"➡️ {order.from_addr} → {order.to_addr}\n"
            f"📅 {order.datetime.strftime('%d.%m.%Y %H:%M')}\n"
            f"🚦 Статус: {status_text}"
        )
        # передаём сам объект order, чтобы keyboard формировала callback_data с id
        markup = get_request_actions_keyboard(order, role)
        bot.send_message(chat_id, text, reply_markup=markup)

    # ========== HANDLERS FOR  / ASSIGN / CANCEL (callback_data includes order_id) ==========

    # ===================== ROOT: ЕДИНАЯ КЛАВИАТУРА ДЕЙСТВИЙ =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_request:"))
    def cb_edit_request(call: types.CallbackQuery):
        """
        Кнопка "Редактировать заявку":
        - проверяет роль, достает заявку, отправляет унифицированную клавиатуру действий (редактирование + чат + история).
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.answer_callback_query(call.id, "Заявка не найдена.")
            return

        # ВНИМАНИЕ: в keyboards/request_actions.py убедитесь, что кнопка истории использует
        # callback_data=f"request_history:{order.id}"
        markup = get_request_actions_keyboard(order, role="dispatcher", include_chat=True)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"✏️ Действия для заявки #{order.id}:", reply_markup=markup)

    # # --- заменить старый cb_edit_request ---
    # @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_request:"))
    # def cb_edit_request(call: types.CallbackQuery):
    #     dispatcher = _ensure_dispatcher(bot, call.message.chat.id, call.from_user.id)
    #     if not dispatcher:
    #         bot.answer_callback_query(call.id)
    #         return
    #     try:
    #         order_id = int(call.data.split(":", 1)[1])
    #     except Exception:
    #         bot.answer_callback_query(call.id, "Ошибка идентификатора заявки.")
    #         return
    #
    #     order = Order.get_or_none(Order.id == order_id)
    #     if not order:
    #         bot.answer_callback_query(call.id, "Заявка не найдена.")
    #         return
    #
    #     bot.answer_callback_query(call.id)
    #     _send_actions(bot, call.message.chat.id, order)

    # --- edit_from (использует RequestsStates.edit_from) ---
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_from:"))
    def cb_edit_from(call: types.CallbackQuery):
        dispatcher = _ensure_dispatcher(bot, call.message.chat.id, call.from_user.id)
        if not dispatcher:
            bot.answer_callback_query(call.id)
            return
        order_id = int(call.data.split(":", 1)[1])
        order = _get_order_or_notify(bot, call.message.chat.id, order_id)
        if not order:
            bot.answer_callback_query(call.id);
            return
        if not _can_edit(order):
            bot.answer_callback_query(call.id, "Редактирование доступно только для новых/подтверждённых.")
            return
        # сохраняем order_id в state-контексте и ставим состояние
        bot.set_state(call.from_user.id, RequestsStates.edit_from, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order.id
        bot.send_message(call.message.chat.id, "Введите новый адрес точки А:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_from)
    def edit_from_step(message: types.Message):
        dispatcher = _ensure_dispatcher(bot, message.chat.id, message.from_user.id)
        if not dispatcher:
            bot.delete_state(message.from_user.id, message.chat.id)
            return
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")
        order = _get_order_or_notify(bot, message.chat.id, order_id) if order_id else None
        if not order:
            bot.delete_state(message.from_user.id, message.chat.id);
            return
        if not _can_edit(order):
            bot.send_message(message.chat.id, "Редактирование доступно только для новых/подтверждённых.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return
        order.from_addr = (message.text or "").strip()
        order.save()
        OrderStatusHistory.create(order=order, by_user=dispatcher, status=order.status, note="Изменена точка А")
        bot.send_message(message.chat.id, f"✅ Точка А обновлена для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)
        _send_actions(bot, message.chat.id, order)

    # ===================== EDIT TO =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_to:"))
    def cb_edit_to(call: types.CallbackQuery):
        """
        Callback-хендлер для редактирования точки Б.
        Переводит пользователя в состояние RequestsStates.edit_to.
        """
        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        bot.set_state(call.from_user.id, RequestsStates.edit_to, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, "Введите новый адрес точки Б:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_to)
    def edit_to_step(message: types.Message):
        """
        Обрабатывает ввод нового адреса точки Б.
        """
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.to_addr = message.text.strip()
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note="Изменена точка Б"
            )
            bot.send_message(message.chat.id, f"✅ Точка Б обновлена для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== EDIT DATETIME =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_dt:"))
    def cb_edit_dt(call: types.CallbackQuery):
        """
        Callback-хендлер для редактирования даты/времени.
        """
        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        bot.set_state(call.from_user.id, RequestsStates.edit_dt, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, "Введите новую дату и время (ДД.MM.ГГГГ ЧЧ:ММ):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_dt)
    def edit_dt_step(message: types.Message):
        """
        Обрабатывает ввод новой даты и времени.
        """
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        try:
            dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Формат неверный. Пример: 25.08.2025 14:30")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.datetime = dt
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note="Изменена дата/время"
            )
            bot.send_message(message.chat.id, f"✅ Дата/время обновлены для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== EDIT: КОММЕНТАРИЙ =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_comment:"))
    def cb_edit_comment(call: types.CallbackQuery):
        """
        Начало редактирования комментария:
        - ставит RequestsStates.edit_comment,
        - кладет order_id в state,
        - просит ввести новый комментарий.
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        bot.set_state(call.from_user.id, RequestsStates.edit_comment, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, "Введите новый комментарий (можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_comment)
    def edit_comment_step(message: types.Message):
        """
        Сохраняет введённый комментарий в заявке и пишет запись в историю.
        """
        if not _ensure_dispatcher_msg(bot, message):
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.comment = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note="Изменен комментарий"
            )
            bot.send_message(message.chat.id, f"✅ Комментарий обновлён для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== EDIT: ТИП ГРУЗА =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_cargo:"))
    def cb_edit_cargo(call: types.CallbackQuery):
        """
        Начало редактирования типа груза:
        - ставит RequestsStates.edit_cargo,
        - кладет order_id в state,
        - просит ввести тип груза.
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        bot.set_state(call.from_user.id, RequestsStates.edit_cargo, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, "Введите тип груза (можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_cargo)
    def edit_cargo_step(message: types.Message):
        """
        Сохраняет новый тип груза в заявке и пишет запись в историю.
        """
        if not _ensure_dispatcher_msg(bot, message):
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.cargo_type = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note="Изменен тип груза"
            )
            bot.send_message(message.chat.id, f"✅ Тип груза обновлён для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== EDIT: ВЕС/ОБЪЁМ =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("edit_weight:"))
    def cb_edit_weight(call: types.CallbackQuery):
        """
        Начало редактирования веса/объёма:
        - ставит RequestsStates.edit_weight,
        - кладет order_id в state,
        - просит ввести строку веса/объёма.
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        bot.set_state(call.from_user.id, RequestsStates.edit_weight, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, "Введите вес/объем (строка, можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.edit_weight)
    def edit_weight_step(message: types.Message):
        """
        Сохраняет новое значение веса/объёма и пишет запись в историю.
        """
        if not _ensure_dispatcher_msg(bot, message):
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.weight_volume = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note="Изменён вес/объем"
            )
            bot.send_message(message.chat.id, f"✅ Вес/объем обновлён для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== ASSIGN: НАЗНАЧЕНИЕ ВОДИТЕЛЯ =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("assign_driver:"))
    def cb_assign_driver(call: types.CallbackQuery):
        """
        Старт назначения/переназначения водителя:
        - ставит RequestsStates.assign_driver,
        - кладет order_id в state,
        - показывает клавиатуру выбора водителей (ReplyKeyboard).
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        drivers = User.select().where(
            (User.role == int(UserRole.DRIVER)) & (User.is_active == True)
        )

        bot.set_state(call.from_user.id, RequestsStates.assign_driver, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(
            call.message.chat.id,
            "Выберите водителя:",
            reply_markup=get_drivers_keyboard(drivers)
        )
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.assign_driver)
    def assign_driver_step(message: types.Message):
        """
        Принимает выбор водителя из ReplyKeyboard, находит его в БД,
        проставляет водителя в заявке; если статус был NEW — делает CONFIRMED.
        Пишет запись в историю.
        """
        if not _ensure_dispatcher_msg(bot, message):
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        raw = (message.text or "").strip()

        # Разбор текста кнопки формата "Имя Фамилия (@username)" или "Имя Фамилия"
        driver = None
        if "(" in raw and ")" in raw and "@" in raw:
            try:
                uname = raw.split("(")[1].split(")")[0].strip()
                if uname.startswith("@"):
                    uname = uname[1:]
                driver = User.get_or_none((User.username == uname) & (User.role == int(UserRole.DRIVER)))
            except Exception:
                driver = None

        if not driver:
            parts = raw.split(" (@")[0].split()
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else None
            q = User.select().where((User.role == int(UserRole.DRIVER)) & (User.first_name == first))
            if last:
                q = q.where(User.last_name == last)
            driver = q.first()

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.driver = driver
            if order.status == int(OrderStatus.NEW):
                order.status = int(OrderStatus.CONFIRMED)
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note=f"Назначен водитель: {driver.first_name if driver else '—'}"
            )
            bot.send_message(message.chat.id, f"✅ Водитель обновлён для заявки #{order.id}")

        bot.delete_state(message.from_user.id, message.chat.id)

    # ===================== CANCEL: ОТМЕНА ЗАЯВКИ =====================
    @bot.callback_query_handler(func=lambda c: c.data.startswith("cancel_request:"))
    def cb_cancel_request(call: types.CallbackQuery):
        """
        Старт отмены заявки:
        - проверяет, что статус NEW/CONFIRMED,
        - ставит RequestsStates.cancel_reason,
        - просит ввести причину.
        """
        if not _ensure_dispatcher_call(bot, call):
            return

        try:
            order_id = int(call.data.split(":")[1])
        except Exception:
            bot.answer_callback_query(call.id, "Ошибка ID заявки.")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.answer_callback_query(call.id, "Заявка не найдена.")
            return

        if order.status not in [int(OrderStatus.NEW), int(OrderStatus.CONFIRMED)]:
            bot.answer_callback_query(call.id, "Отмена доступна только для новых/подтвержденных.")
            return

        bot.set_state(call.from_user.id, RequestsStates.cancel_reason, call.message.chat.id)
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["order_id"] = order_id

        bot.send_message(call.message.chat.id, f"Введите причину отмены для заявки #{order_id}:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=RequestsStates.cancel_reason)
    def cancel_reason_step(message: types.Message):
        """
        Принимает причину отмены, переводит заявку в CANCELLED, сохраняет причину и историю.
        """
        if not _ensure_dispatcher_msg(bot, message):
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            order_id = data.get("order_id")

        reason = (message.text or "").strip() or "Без причины"
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.status = int(OrderStatus.CANCELLED)
            order.cancel_reason = reason
            order.save()
            OrderStatusHistory.create(
                order=order,
                by_user=User.get(User.tg_id == message.from_user.id),
                status=order.status,
                note=f"Отменена: {reason}"
            )
            bot.send_message(message.chat.id, f"❌ Заявка #{order.id} отменена.\n🚫 Причина: {reason}")

        bot.delete_state(message.from_user.id, message.chat.id)


    @bot.message_handler(func=lambda m: m.text == "📂 Заявки по статусу")
    def show_status_lists_menu(message: types.Message):
        """
        Показывает диспетчеру 4 кнопки списков по статусу.
        (Добавьте пункт '📂 Заявки по статусу' в главное меню диспетчера.)
        """
        if not _ensure_dispatcher_msg(bot, message):
            return
        bot.send_message(message.chat.id, "Выберите список:", reply_markup=get_status_filter_keyboard())

    @bot.callback_query_handler(func=lambda c: c.data.startswith("list_status:"))
    def cb_list_by_status(call: types.CallbackQuery):
        """
        Выводит список заявок диспетчера по выбранному статусу.
        Использует уже существующий рендер карточки (_send_order_card).
        """
        if not _ensure_dispatcher_call(bot, call):
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
                  .where((Order.dispatcher == user) & (Order.status == status_val))
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
            # предполагаем, что у вас уже есть функция _send_order_card(bot, chat_id, order, role="dispatcher")
            _send_order_card(bot, call.message.chat.id, order, role="dispatcher")

        bot.answer_callback_query(call.id)

    # подключаем чат-хендлеры
    register_chat_handlers(bot)

    ####
    def _ensure_dispatcher(bot: TeleBot, chat_id: int, user_id: int) -> User | None:
        """
        Функция, которая проверяет роль диспетчера
        :param bot:
        :param chat_id:
        :param user_id:
        :return:
        """
        user = User.get_or_none(User.tg_id == user_id)
        if not user or int(user.role) != int(UserRole.DISPATCHER):
            bot.send_message(chat_id, "❌ Команда доступна только диспетчеру.")
            return None
        return user

    # ===================== ВСПОМОГАТЕЛЬНО =====================
    def _ensure_dispatcher_call(bot, call: types.CallbackQuery) -> bool:
        """
        Проверяет, что инициатор коллбэка — диспетчер.
        Возвращает True/False, при False отправляет ответ в callback_query.
        """
        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not user or user.role != int(UserRole.DISPATCHER):
            bot.answer_callback_query(call.id, "❌ Команда доступна только диспетчеру.")
            return False
        return True

    def _ensure_dispatcher_msg(bot, message: types.Message) -> bool:
        """
        Проверяет, что отправитель сообщения — диспетчер.
        Возвращает True/False, при False отвечает в чат.
        """
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user or user.role != int(UserRole.DISPATCHER):
            bot.send_message(message.chat.id, "❌ Команда доступна только диспетчеру.")
            return False
        return True
    #
    # def _ensure_driver_mixed(call_or_msg):
    #     """
    #     Вернуть User, если это водитель; иначе отправить ответ (callback_answer или message)
    #     и вернуть None.
    #     """
    #     from_user = getattr(call_or_msg, "from_user", None)
    #     if not from_user:
    #         return None
    #     tg_id = from_user.id
    #     user = User.get_or_none(User.tg_id == tg_id)
    #     if not user or int(user.role) != int(UserRole.DRIVER):
    #         # callback_query содержит .id
    #         if hasattr(call_or_msg, "id"):
    #             try:
    #                 bot.answer_callback_query(call_or_msg.id, "❌ Команда доступна только водителю.")
    #             except Exception:
    #                 pass
    #         else:
    #             try:
    #                 bot.send_message(call_or_msg.chat.id, "❌ Команда доступна только водителю.")
    #             except Exception:
    #                 pass
    #         return None
    #     return user