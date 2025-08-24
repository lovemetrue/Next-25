# handlers/debug.py
import logging
from telebot.types import Message
from telebot.handler_backends import State, StatesGroup

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)


class TestStates(StatesGroup):
    test = State()


def register_handlers(bot):
    @bot.message_handler(commands=['test_state'])
    def test_state_handler(message: Message) -> None:
        """Тестовый обработчик для проверки работы состояний"""
        bot.set_state(message.from_user.id, TestStates.test, message.chat.id)
        bot.send_message(message.chat.id, "Тестовое состояние установлено. Отправьте любое сообщение.")

    @bot.message_handler(state=TestStates.test)
    def test_state_message_handler(message: Message) -> None:
        """Обработчик для тестового состояния"""
        bot.send_message(message.chat.id, f"Состояние работает! Вы написали: {message.text}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # handlers/debug.py (продолжение)
    @bot.message_handler(commands=['current_state'])
    def current_state_handler(message: Message) -> None:
        """Показать текущее состояние"""
        current_state = bot.get_state(message.from_user.id, message.chat.id)
        if current_state:
            bot.send_message(message.chat.id, f"Текущее состояние: {current_state}")
        else:
            bot.send_message(message.chat.id, "Состояние не установлено")


    ##### old_despatcher.py

    # ====== ✏️ РЕДАКТИРОВАНИЕ ЗАЯВКИ (инлайн‑меню) ======
    @bot.callback_query_handler(func=lambda c: c.data == "edit_request")
    def cb_edit_request(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id, "Не удалось определить заявку.")
            return

        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.answer_callback_query(call.id, "Заявка не найдена.")
            return

        # доступно только в NEW/CONFIRMED
        if order.status not in [int(OrderStatus.NEW), int(OrderStatus.CONFIRMED)]:
            bot.answer_callback_query(call.id, "Редактирование доступно только для новых/подтвержденных.")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📍 Изменить точку А", callback_data="edit_from"),
            types.InlineKeyboardButton("📍 Изменить точку Б", callback_data="edit_to"),
        )
        markup.add(
            types.InlineKeyboardButton("📅 Изменить дату/время", callback_data="edit_dt"),
            types.InlineKeyboardButton("💬 Комментарий", callback_data="edit_comment"),
        )
        markup.add(
            types.InlineKeyboardButton("📦 Тип груза", callback_data="edit_cargo"),
            types.InlineKeyboardButton("⚖️ Вес/объем", callback_data="edit_weight"),
        )
        markup.add(
            types.InlineKeyboardButton("👨‍💼 Назначить/сменить водителя", callback_data="assign_driver"),
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"✏️ Что изменить в заявке #{order.id}?", reply_markup=markup)



    # --- точка А ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_from")
    def cb_edit_from(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_from:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите новый адрес точки А:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_from:"))
    def edit_from_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.from_addr = message.text.strip()
            order.save()
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменена точка А")
            bot.send_message(message.chat.id, f"✅ Точка А обновлена для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # --- точка Б ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_to")
    def cb_edit_to(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_to:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите новый адрес точки Б:")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_to:"))
    def edit_to_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.to_addr = message.text.strip()
            order.save()
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменена точка Б")
            bot.send_message(message.chat.id, f"✅ Точка Б обновлена для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # --- дата/время ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_dt")
    def cb_edit_dt(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_dt:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_dt:"))
    def edit_dt_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
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
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменена дата/время")
            bot.send_message(message.chat.id, f"✅ Дата/время обновлены для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # --- комментарий ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_comment")
    def cb_edit_comment(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_comment:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите новый комментарий (можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_comment:"))
    def edit_comment_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.comment = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменен комментарий")
            bot.send_message(message.chat.id, f"✅ Комментарий обновлён для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # --- тип груза ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_cargo")
    def cb_edit_cargo(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_cargo:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите тип груза (можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_cargo:"))
    def edit_cargo_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.cargo_type = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменен тип груза")
            bot.send_message(message.chat.id, f"✅ Тип груза обновлён для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # --- вес/объем ---
    @bot.callback_query_handler(func=lambda c: c.data == "edit_weight")
    def cb_edit_weight(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id)
            return
        bot.set_state(call.from_user.id, f"edit_weight:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Введите вес/объем (строка, можно пусто):")
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("edit_weight:"))
    def edit_weight_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            bot.send_message(message.chat.id, "Заявка не найдена.")
        else:
            order.weight_volume = (message.text or "").strip() or None
            order.save()
            OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                      status=order.status, note="Изменён вес/объем")
            bot.send_message(message.chat.id, f"✅ Вес/объем обновлён для заявки #{order.id}")
        bot.delete_state(message.from_user.id, message.chat.id)

    # ====== 👨‍💼 НАЗНАЧИТЬ/ПЕРЕНАЗНАЧИТЬ ВОДИТЕЛЯ ======
    @bot.callback_query_handler(func=lambda c: c.data == "assign_driver")
    def cb_assign_driver(call: types.CallbackQuery):
        order_id = _parse_order_id_from_text(call.message.text or "")
        if not order_id:
            bot.answer_callback_query(call.id, "Не удалось определить заявку.")
            return
        drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True))
        bot.set_state(call.from_user.id, f"assign_driver:{order_id}", call.message.chat.id)
        bot.send_message(call.message.chat.id, "Выберите водителя:", reply_markup=get_drivers_keyboard(drivers))
        bot.answer_callback_query(call.id)

    @bot.message_handler(state=lambda s: s and s.startswith("assign_driver:"))
    def assign_driver_step(message: types.Message):
        state = bot.get_state(message.from_user.id, message.chat.id) or ""
        order_id = int(state.split(":")[1])

    # handlers/dispatcher.py
    from telebot import TeleBot, types
    from datetime import datetime, timedelta
    from database.models import User, Order, OrderStatus, UserRole, OrderPrefix, Attachment
    from keyboards.request_actions import (get_prefix_keyboard,
                                           get_drivers_keyboard,
                                           get_request_filter_keyboard,
                                           get_request_actions_keyboard)
    import logging
    from keyboards.main_menu import get_main_menu
    from peewee import fn
    from states.request_states import RequestsStates

    PREFIX_MAP = {
        "с ндс": OrderPrefix.WITH_VAT,
        "без ндс": OrderPrefix.WITHOUT_VAT,
        "нал": OrderPrefix.CASH,
    }

    # Настройка логирования
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/bot.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    def register_dispatcher_handlers(bot: TeleBot):
        # ----------------- ВСПОМОГАТЕЛЬНОЕ -----------------

        def _parse_order_id_from_text(text: str) -> int | None:
            # Ожидаем, что в сообщении есть "Заявка #123"
            try:
                hash_pos = text.find("#")
                if hash_pos == -1:
                    return None
                num = ""
                for ch in text[hash_pos + 1:]:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                return int(num) if num else None
            except Exception:
                return None

        def _status_to_keyboard_code(status: int) -> str:
            mapping = {
                OrderStatus.NEW: "new",
                OrderStatus.CONFIRMED: "confirmed",
                OrderStatus.LOADING: "loading",
                OrderStatus.ENROUTE: "in_transit",
                OrderStatus.DELIVERED: "delivered",
                OrderStatus.CANCELLED: "cancelled",
                OrderStatus.ENROUTE_TO_LOADING: "enroute_to_loading",
            }
            return mapping.get(OrderStatus(status), "new")

        STATUS_TEXT_TO_ENUM = {
            "🆕 Новые": OrderStatus.NEW,
            "✅ Подтвержденные": OrderStatus.CONFIRMED,
            "🚛 В пути": OrderStatus.ENROUTE,
            "📦 На загрузке": OrderStatus.LOADING,
            "✅ Доставленные": OrderStatus.DELIVERED,
            "❌ Отмененные": OrderStatus.CANCELLED,
        }

        def _format_order_brief(o: Order) -> str:
            base = (f"🚛 Заявка #{o.id}\n"
                    f"Статус: {OrderStatus(o.status).label}\n"
                    f"{o.from_addr} → {o.to_addr}\n"
                    f"🕒 {o.datetime.strftime('%d.%m.%Y %H:%M')}")
            if o.status == int(OrderStatus.CANCELLED) and o.cancel_reason:
                base += f"\n🚫 Причина отмены: {o.cancel_reason}"
            return base

        def _ensure_dispatcher(bot: TeleBot, message: types.Message) -> User | None:
            user = User.get_or_none(User.tg_id == message.from_user.id)
            if not user or user.role != int(UserRole.DISPATCHER):
                bot.send_message(message.chat.id, "❌ Команда доступна только диспетчеру.")
                return None
            return user

        # Старт создания
        @bot.message_handler(func=lambda m: m.text == "➕ Создать заявку")
        def create_order_start(message: types.Message):
            bot.delete_state(message.from_user.id, message.chat.id)
            bot.send_message(message.chat.id, "Выберите префикс заявки:", reply_markup=get_prefix_keyboard())
            bot.set_state(message.from_user.id, "order_prefix", message.chat.id)

        # Префикс
        @bot.message_handler(state="order_prefix")
        def order_prefix_step(message: types.Message):
            text = (message.text or "").strip().lower()
            if text not in PREFIX_MAP:
                bot.send_message(message.chat.id, "❌ Выберите префикс с клавиатуры.")
                return

            bot.add_data(message.from_user.id, message.chat.id, order_prefix=int(PREFIX_MAP[text]))
            # Список водителей
            drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True))
            bot.send_message(message.chat.id, "Выберите водителя (или нажмите ❌ Без водителя):",
                             reply_markup=get_drivers_keyboard(drivers))
            bot.set_state(message.from_user.id, "order_driver", message.chat.id)

        # Водитель
        @bot.message_handler(state="order_driver")
        def order_driver_step(message: types.Message):
            raw = (message.text or "").strip()

            # ❌ Без водителя
            if raw == "❌ Без водителя":
                bot.add_data(message.from_user.id, message.chat.id, driver_id=None)
            else:
                # ожидаем формат "Имя Фамилия (@username)" или хотя бы с @username
                driver = None
                if "(" in raw and ")" in raw and "@":
                    # вытащим username из скобок
                    try:
                        uname = raw.split("(")[1].split(")")[0].strip()
                        if uname.startswith("@"):
                            uname = uname[1:]
                        driver = User.get_or_none((User.username == uname) & (User.role == int(UserRole.DRIVER)))
                    except Exception:
                        driver = None
                if not driver:
                    # fallback по имени
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

        # Точка А
        @bot.message_handler(state="order_from_addr")
        def order_from_step(message: types.Message):
            txt = (message.text or "").strip()
            if not txt:
                bot.send_message(message.chat.id, "❌ Укажите адрес отправления.")
                return
            bot.add_data(message.from_user.id, message.chat.id, from_addr=txt)
            bot.send_message(message.chat.id, "Введите адрес назначения (Точка Б):")
            bot.set_state(message.from_user.id, "order_to_addr", message.chat.id)

        # Точка Б
        @bot.message_handler(state="order_to_addr")
        def order_to_step(message: types.Message):
            txt = (message.text or "").strip()
            if not txt:
                bot.send_message(message.chat.id, "❌ Укажите адрес назначения.")
                return
            bot.add_data(message.from_user.id, message.chat.id, to_addr=txt)

            # ⚠️ СРАЗУ идём к типу груза (шаг даты вырезан)
            bot.send_message(message.chat.id, "Введите тип груза (опционально, можно оставить пустым):")
            bot.set_state(message.from_user.id, "order_cargo", message.chat.id)

        # Дата/время
        @bot.message_handler(state="order_dt")
        def order_dt_step(message: types.Message):

            bot.add_data(message.from_user.id, message.chat.id, datetime=dt)
            bot.send_message(message.chat.id, "Введите тип груза (опционально, можно оставить пустым):")
            bot.set_state(message.from_user.id, "order_cargo", message.chat.id)

        # Тип груза
        @bot.message_handler(state="order_cargo")
        def order_cargo_step(message: types.Message):
            cargo = (message.text or "").strip() or None
            bot.add_data(message.from_user.id, message.chat.id, cargo_type=cargo)
            bot.send_message(message.chat.id, "Введите вес/объём (опционально):")
            bot.set_state(message.from_user.id, "order_weight_volume", message.chat.id)

        # Вес/объём
        @bot.message_handler(state="order_weight_volume")
        def order_weight_volume_step(message: types.Message):
            wv = (message.text or "").strip() or None
            bot.add_data(message.from_user.id, message.chat.id, weight_volume=wv)
            bot.send_message(message.chat.id, "Комментарий (опционально):")
            bot.set_state(message.from_user.id, "order_comment", message.chat.id)

        # Комментарий
        @bot.message_handler(state="order_comment")
        def order_comment_step(message: types.Message):
            comment = (message.text or "").strip() or None
            bot.add_data(message.from_user.id, message.chat.id, comment=comment)
            bot.send_message(
                message.chat.id,
                "Прикрепите файл (фото/документ) или напишите «пропустить».",
            )
            bot.set_state(message.from_user.id, "order_file", message.chat.id)

        # Пропуск файла
        @bot.message_handler(state="order_file", content_types=["text"])
        def order_file_skip_or_unknown(message: types.Message):
            text = (message.text or "").strip().lower()
            if text in ("пропустить", "skip", "нет", "без файла"):
                with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                    _create_order_from_state(bot, message, data, first_file=None)
            else:
                bot.send_message(message.chat.id,
                                 "Если файла нет — напишите «пропустить», либо пришлите фото/документ.")

        # Приём фото/документа
        @bot.message_handler(state="order_file", content_types=["photo", "document"])
        def order_file_step(message: types.Message):
            file = _extract_attachment_from_message(message)
            if file is None:
                bot.send_message(message.chat.id, "❌ Неподдерживаемый тип файла. Пришлите изображение или документ.")
                return

            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                _create_order_from_state(bot, message, data, first_file=file)

        # ---------- утилита создания заказа ----------
        def _create_order_from_state(bot: TeleBot, message: types.Message, data: dict, first_file: dict | None):
            try:
                # обязательные поля
                prefix = data.get("order_prefix")
                from_addr = data.get("from_addr")
                to_addr = data.get("to_addr")

                # ⚡ дата исполнения автоматически, если не была где-то ранее вычислена
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

                # создаём заказ
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

                # сохраняем вложение (если есть)
                if first_file:
                    Attachment.create(
                        order=order,
                        uploaded_by=dispatcher,
                        file_id=first_file["file_id"],
                        file_type=first_file["file_type"],  # "image" или "document"
                        caption=first_file.get("caption"),
                    )

                bot.send_message(
                    message.chat.id,
                    f"✅ Заявка #{order.id} создана: «{from_addr} → {to_addr}»\n"
                    f"🕒 Дата: {exec_dt.strftime('%d.%m.%Y %H:%M')}\n"
                    f"🚛 Водитель: {(driver.first_name + (' ' + (driver.last_name or ''))).strip() if driver else 'не назначен'}"
                )

                # Сбросить состояние и показать меню по роли
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(message.chat.id, reply_markup=get_main_menu("dispatcher"))

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Ошибка при создании заявки: {e}")
                raise

        # ====== 👨‍💼 ВОДИТЕЛИ (список и активные заявки) ======

        @bot.message_handler(func=lambda m: m.text == "👨‍💼 Водители")
        def list_drivers(message: types.Message):
            dispatcher = _ensure_dispatcher(bot, message)
            if not dispatcher:
                return

            drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True)).order_by(
                User.first_name, User.last_name)
            if not drivers:
                bot.send_message(message.chat.id, "Пока нет зарегистрированных водителей.")
                return

            for d in drivers:
                # считаем активные заявки водителя (не доставлено/не отменено)
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
                kb_code = _status_to_keyboard_code(o.status)
                bot.send_message(
                    call.message.chat.id,
                    _format_order_brief(o),
                    reply_markup=get_request_actions_keyboard(kb_code, "dispatcher")
                )
            bot.answer_callback_query(call.id)

        # ====== 📊 СТАТИСТИКА (для диспетчера) ======
        @bot.message_handler(func=lambda m: m.text == "📊 Статистика")
        def dispatcher_stats(message: types.Message):
            dispatcher = _ensure_dispatcher(bot, message)
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

            # ТОП-водители по доставленным
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

        # ====== 📋 МОИ ЗАЯВКИ (фильтры + список) ======

        @bot.message_handler(func=lambda m: m.text == "📋 Мои заявки")
        def show_my_orders_entry(message: types.Message):
            dispatcher = _ensure_dispatcher(bot, message)
            if not dispatcher:
                return
            bot.send_message(message.chat.id, "Выберите фильтр:", reply_markup=get_request_filter_keyboard())
            bot.set_state(message.from_user.id, "filter_orders", message.chat.id)

        @bot.message_handler(state="filter_orders")
        def filter_orders_step(message: types.Message):
            dispatcher = _ensure_dispatcher(bot, message)
            if not dispatcher:
                return

            text = (message.text or "").strip()
            # Датовые фильтры:
            if text == "📅 Сегодня":
                start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                orders = (Order.select()
                          .where((Order.dispatcher == dispatcher) &
                                 (Order.datetime >= start) &
                                 (Order.datetime < end))
                          .order_by(Order.datetime.desc()))
            elif text == "📆 Неделя":
                start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                    days=datetime.now().weekday())
                end = start + timedelta(days=7)
                orders = (Order.select()
                          .where((Order.dispatcher == dispatcher) &
                                 (Order.datetime >= start) &
                                 (Order.datetime < end))
                          .order_by(Order.datetime.desc()))
            elif text == "📊 Все":
                orders = Order.select().where(Order.dispatcher == dispatcher).order_by(Order.datetime.desc())
                print(orders)
            elif text in STATUS_TEXT_TO_ENUM:
                status = int(STATUS_TEXT_TO_ENUM[text])
                orders = (Order.select()
                          .where((Order.dispatcher == dispatcher) & (Order.status == status))
                          .order_by(Order.datetime.desc()))
            else:
                bot.send_message(message.chat.id, "❌ Выберите пункт из меню фильтра.")
                return

            if not orders:
                bot.send_message(message.chat.id, "📭 Заявок по выбранному фильтру нет.")
                return

            for o in orders:
                kb_code = _status_to_keyboard_code(o.status)
                bot.send_message(
                    message.chat.id,
                    _format_order_brief(o),
                    reply_markup=get_request_actions_keyboard(kb_code, "dispatcher")
                )

            # Можно сбросить state, чтобы следующее сообщение не ловил обработчик фильтра
            # bot.delete_state(message.from_user.id, message.chat.id)

        @bot.message_handler(state=RequestsStates.filter_orders)
        def filter_orders_step(message):
            dispatcher = _ensure_dispatcher(bot, message)
            if not dispatcher:
                return

            text = (message.text or "").strip()

            # если нажали "Назад"
            if text == "⬅️ Назад":
                bot.delete_state(message.from_user.id, message.chat.id)
                _show_dispatcher_menu(bot, message.chat.id)
                return

        # глобальный обработчик "Назад" (работает, когда нажимают кнопку ReplyKeyboard '⬅️ Назад')
        @bot.message_handler(func=lambda m: m.text == "⬅️ Назад")
        def handler_back_to_menu(message):
            # Узнаём роль пользователя и текущий state
            user = User.get_or_none(User.tg_id == message.from_user.id)

            # Если диспетчер — возвращаем в его главное меню и сбрасываем state
            if user and user.role == int(UserRole.DISPATCHER):
                try:
                    bot.delete_state(message.from_user.id, message.chat.id)
                except Exception:
                    pass
                _show_dispatcher_menu(bot, message.chat.id)
                return

            # Если водитель — показать его меню (если нужно)
            if user and user.role == int(UserRole.DRIVER):
                try:
                    bot.delete_state(message.from_user.id, message.chat.id)
                except Exception:
                    pass
                bot.send_message(message.chat.id, "Главное меню:", reply_markup=get_main_menu("driver"))
                return

            # Для остальных — показать профиль/старт (fallback)
            try:
                bot.delete_state(message.from_user.id, message.chat.id)
            except Exception:
                pass
            bot.send_message(message.chat.id, "Главное меню:", reply_markup=get_main_menu(None))

        # ====== ✏️ РЕДАКТИРОВАНИЕ ЗАЯВКИ (инлайн‑меню) ======
        @bot.callback_query_handler(func=lambda c: c.data == "edit_request")
        def cb_edit_request(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id, "Не удалось определить заявку.")
                return

            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.answer_callback_query(call.id, "Заявка не найдена.")
                return

            # доступно только в NEW/CONFIRMED
            if order.status not in [int(OrderStatus.NEW), int(OrderStatus.CONFIRMED)]:
                bot.answer_callback_query(call.id, "Редактирование доступно только для новых/подтвержденных.")
                return

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("📍 Изменить точку А", callback_data="edit_from"),
                types.InlineKeyboardButton("📍 Изменить точку Б", callback_data="edit_to"),
            )
            markup.add(
                types.InlineKeyboardButton("📅 Изменить дату/время", callback_data="edit_dt"),
                types.InlineKeyboardButton("💬 Комментарий", callback_data="edit_comment"),
            )
            markup.add(
                types.InlineKeyboardButton("📦 Тип груза", callback_data="edit_cargo"),
                types.InlineKeyboardButton("⚖️ Вес/объем", callback_data="edit_weight"),
            )
            markup.add(
                types.InlineKeyboardButton("👨‍💼 Назначить/сменить водителя", callback_data="assign_driver"),
            )
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"✏️ Что изменить в заявке #{order.id}?", reply_markup=markup)

        # --- точка А ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_from")
        def cb_edit_from(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_from:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите новый адрес точки А:")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_from:"))
        def edit_from_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.from_addr = message.text.strip()
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменена точка А")
                bot.send_message(message.chat.id, f"✅ Точка А обновлена для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # --- точка Б ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_to")
        def cb_edit_to(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_to:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите новый адрес точки Б:")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_to:"))
        def edit_to_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.to_addr = message.text.strip()
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменена точка Б")
                bot.send_message(message.chat.id, f"✅ Точка Б обновлена для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # --- дата/время ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_dt")
        def cb_edit_dt(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_dt:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_dt:"))
        def edit_dt_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
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
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменена дата/время")
                bot.send_message(message.chat.id, f"✅ Дата/время обновлены для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # --- комментарий ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_comment")
        def cb_edit_comment(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_comment:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите новый комментарий (можно пусто):")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_comment:"))
        def edit_comment_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.comment = (message.text or "").strip() or None
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменен комментарий")
                bot.send_message(message.chat.id, f"✅ Комментарий обновлён для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # --- тип груза ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_cargo")
        def cb_edit_cargo(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_cargo:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите тип груза (можно пусто):")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_cargo:"))
        def edit_cargo_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.cargo_type = (message.text or "").strip() or None
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменен тип груза")
                bot.send_message(message.chat.id, f"✅ Тип груза обновлён для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # --- вес/объем ---
        @bot.callback_query_handler(func=lambda c: c.data == "edit_weight")
        def cb_edit_weight(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id)
                return
            bot.set_state(call.from_user.id, f"edit_weight:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Введите вес/объем (строка, можно пусто):")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("edit_weight:"))
        def edit_weight_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.weight_volume = (message.text or "").strip() or None
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note="Изменён вес/объем")
                bot.send_message(message.chat.id, f"✅ Вес/объем обновлён для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # ====== 👨‍💼 НАЗНАЧИТЬ/ПЕРЕНАЗНАЧИТЬ ВОДИТЕЛЯ ======
        @bot.callback_query_handler(func=lambda c: c.data == "assign_driver")
        def cb_assign_driver(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id, "Не удалось определить заявку.")
                return
            drivers = User.select().where((User.role == int(UserRole.DRIVER)) & (User.is_active == True))
            bot.set_state(call.from_user.id, f"assign_driver:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, "Выберите водителя:", reply_markup=get_drivers_keyboard(drivers))
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("assign_driver:"))
        def assign_driver_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])

            raw = (message.text or "").strip()
            driver = None
            if "(" in raw and ")" in raw and "@":
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
                # При назначении можно автоматически подтвердить, если было NEW
                if order.status == int(OrderStatus.NEW):
                    order.status = int(OrderStatus.CONFIRMED)
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status,
                                          note=f"Назначен водитель: {driver.first_name if driver else '—'}")
                bot.send_message(message.chat.id, f"✅ Водитель обновлён для заявки #{order.id}")
            bot.delete_state(message.from_user.id, message.chat.id)

        # ====== ❌ ОТМЕНА ЗАЯВКИ (с причиной) ======
        @bot.callback_query_handler(func=lambda c: c.data == "cancel_request")
        def cb_cancel_request(call: types.CallbackQuery):
            order_id = _parse_order_id_from_text(call.message.text or "")
            if not order_id:
                bot.answer_callback_query(call.id, "Не удалось определить заявку.")
                return
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.answer_callback_query(call.id, "Заявка не найдена.")
                return
            if order.status not in [int(OrderStatus.NEW), int(OrderStatus.CONFIRMED)]:
                bot.answer_callback_query(call.id, "Отмена доступна только для новых/подтвержденных.")
                return

            bot.set_state(call.from_user.id, f"cancel_reason:{order_id}", call.message.chat.id)
            bot.send_message(call.message.chat.id, f"Введите причину отмены для заявки #{order_id}:")
            bot.answer_callback_query(call.id)

        @bot.message_handler(state=lambda s: s and s.startswith("cancel_reason:"))
        def cancel_reason_step(message: types.Message):
            state = bot.get_state(message.from_user.id, message.chat.id) or ""
            order_id = int(state.split(":")[1])
            reason = (message.text or "").strip() or "Без причины"
            order = Order.get_or_none(Order.id == order_id)
            if not order:
                bot.send_message(message.chat.id, "Заявка не найдена.")
            else:
                order.status = int(OrderStatus.CANCELLED)
                order.cancel_reason = reason
                order.save()
                OrderStatusHistory.create(order=order, by_user=User.get(User.tg_id == message.from_user.id),
                                          status=order.status, note=f"Отменена: {reason}")
                bot.send_message(message.chat.id, f"❌ Заявка #{order.id} отменена.\n🚫 Причина: {reason}")
            bot.delete_state(message.from_user.id, message.chat.id)

        def _show_dispatcher_menu(bot, chat_id):
            """Показать главное меню диспетчера (создать заявку, водители, статистика)."""
            bot.send_message(chat_id, "Главное меню диспетчера:", reply_markup=get_main_menu("dispatcher"))

        def _extract_attachment_from_message(message: types.Message):
            """
            Возвращает dict с данными вложения или None.
            Формат: {"file_id": str, "file_type": "image"|"document", "caption": Optional[str]}
            Правила:
              - message.photo -> image
              - document с mime_type image/* -> image
              - прочие document -> document
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
                is_image = mt.startswith("image/")  # охватывает jpeg, png, webp, bmp, gif, tiff, heic и т.д.
                return {
                    "file_id": message.document.file_id,
                    "file_type": "image" if is_image else "document",
                    "caption": getattr(message, "caption", None)
                }

            return None