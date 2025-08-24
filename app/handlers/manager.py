# handlers/manager.py
from telebot import TeleBot, types
from loguru import logger
from peewee import fn
from datetime import datetime, timedelta
from typing import Optional
from app.database.models import User, UserRole, Order, OrderStatus, OrderPrefix
from app.keyboards.main_menu import get_main_menu
from app.keyboards.request_actions import (
    get_request_actions_keyboard,
)
from app.handlers.attachments import register_attachments_reports_handlers

def register_manager_handlers(bot: TeleBot):
    """Хэндлеры для руководителя"""

    # 📊 Общая статистика
    @bot.message_handler(func=lambda m: m.text == "📊 Общая статистика")
    def show_stats(message: types.Message):
        total_orders = Order.select().count()
        delivered_orders = Order.select().where(Order.status == int(OrderStatus.DELIVERED)).count()
        cancelled_orders = Order.select().where(Order.status == int(OrderStatus.CANCELLED)).count()

        drivers = User.select().where(User.role == int(UserRole.DRIVER)).count()
        dispatchers = User.select().where(User.role == int(UserRole.DISPATCHER)).count()

        text = (
            "📊 <b>Общая статистика</b>\n\n"
            f"Всего заявок: {total_orders}\n"
            f"✅ Доставлено: {delivered_orders}\n"
            f"❌ Отменено: {cancelled_orders}\n\n"
            f"🚛 Водителей: {drivers}\n"
            f"🧭 Диспетчеров: {dispatchers}\n"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    # 👥 Персонал
    @bot.message_handler(func=lambda m: m.text == "👥 Персонал")
    def show_personnel(message: types.Message):
        users = User.select().where(User.is_active == True)

        text = "👥 <b>Список пользователей:</b>\n\n"
        for u in users:
            role = UserRole(u.role).label
            text += f"ID {u.id}: {u.first_name} {u.last_name or ''} (@{u.username or '-'}) — {role}\n"

        text += "\nДля изменения или удаления используй команду:\n" \
                "<code>/user_edit ID</code> или <code>/user_delete ID</code> или <code>/user_activate ID</code>\n\n" \
                "Пример: /user_delete 1\n" \
                "Вывод: 🗑 Пользователь ID 1 деактивирован.\n"

        bot.send_message(message.chat.id, text, parse_mode="HTML")

    # 🚛 Все заявки
    @bot.message_handler(func=lambda m: m.text == "🚛 Все заявки")
    def show_all_requests(message: types.Message):
        orders = Order.select().order_by(Order.created_at.desc()).limit(10)

        if not orders:
            bot.send_message(message.chat.id, "❌ Заявок пока нет.")
            return

        text = "🚛 Последние заявки:\n\n"
        for o in orders:
            driver = o.driver.first_name if o.driver else "—"
            text += f"#{o.id} | {OrderStatus(o.status).label} | Водитель: {driver}\n"

        bot.send_message(message.chat.id, text)

    # 📈 Аналитика
    @bot.message_handler(func=lambda m: m.text == "📈 Аналитика")
    def show_analytics(message: types.Message):
        week_ago = datetime.now() - timedelta(days=7)
        weekly_orders = Order.select().where(Order.created_at >= week_ago).count()
        delivered_week = Order.select().where(
            (Order.status == int(OrderStatus.DELIVERED)) &
            (Order.created_at >= week_ago)
        ).count()

        text = (
            "📈 <b>Аналитика за неделю</b>\n\n"
            f"Создано заявок: {weekly_orders}\n"
            f"✅ Доставлено: {delivered_week}\n"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    # Удаление пользователя
    @bot.message_handler(commands=["user_delete"])
    def cmd_user_delete(message: types.Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            bot.send_message(message.chat.id, "❌ Укажи ID пользователя: /user_delete 5")
            return

        manager_id = message.from_user.id
        user_id = int(args[1])
        result = delete_user(user_id, manager_id)
        bot.send_message(message.chat.id, result)

    @bot.message_handler(commands=["user_activate"])
    def cmd_user_activate(message: types.Message):
        args = message.text.split()
        if len(args) < 2 or not args[1].isdigit():
            bot.send_message(message.chat.id, "❌ Укажи ID пользователя: /user_activate 5")
            return

        user_id = int(args[1])
        user = User.get_or_none(User.id == user_id)
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь ID {user_id} не найден.")
            return

        user.is_active = True
        user.save()

        bot.send_message(message.chat.id, f"🗑 Пользователь ID {user_id} активирован.")

    # Редактирование пользователя
    @bot.message_handler(commands=["user_edit"])
    def cmd_user_edit(message: types.Message):
        args = message.text.split()
        if len(args) < 4:
            bot.send_message(message.chat.id,
                             "❌ Использование: /user_edit ID field value\n"
                             "Пример: /user_edit 5 role driver")
            return

        user_id = int(args[1])
        field = args[2]
        value = args[3]

        user = User.get_or_none(User.id == user_id)
        if not user:
            bot.send_message(message.chat.id, f"❌ Пользователь ID {user_id} не найден.")
            return

        if field == "role":
            mapping = {"dispatcher": UserRole.DISPATCHER, "driver": UserRole.DRIVER, "manager": UserRole.MANAGER}
            if value not in mapping:
                bot.send_message(message.chat.id, "❌ Неверная роль. Доступно: dispatcher, driver, manager")
                return
            user.role = int(mapping[value])
        elif field == "phone":
            user.phone = value
        elif field == "employee_id":
            user.employee_id = value
        else:
            bot.send_message(message.chat.id, f"❌ Поле '{field}' не поддерживается.")
            return

        user.save()
        bot.send_message(message.chat.id, f"✅ Пользователь ID {user.id} обновлён.")



    # -------------------- Вспомогательные функции --------------------

    def _get_user_from_update(update) -> Optional[User]:
        """
        Возвращает объект User по update (callback_query или message),
        либо None и отправляет ответ (callback_answer / message) при ошибке.
        """
        from_user = getattr(update, "from_user", None)
        if not from_user:
            return None
        return User.get_or_none(User.tg_id == from_user.id)

    def _format_order_brief(o: Order) -> str:
        """
        Формирует короткую строку карточки заявки.
        """
        dt = getattr(o, "datetime", None)
        dt_text = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
        status_text = OrderStatus(o.status).label if o.status is not None else "—"
        driver_name = (f"{o.driver.first_name or ''} {(o.driver.last_name or '')}".strip() if o.driver else "—")
        dispatcher_name = (f"{o.dispatcher.first_name or ''}" if o.dispatcher else "—")
        return (f"📋 Заявка #{o.id}\n"
                f"{o.from_addr} → {o.to_addr}\n"
                f"🕒 {dt_text}\n"
                f"🚚 Водитель: {driver_name}\n"
                f"👤 Диспетчер: {dispatcher_name}\n"
                f"🚦 {status_text}")

    def _build_history_attachments_markup(order: Order) -> types.InlineKeyboardMarkup:
        """
        Возвращает InlineKeyboardMarkup из двух кнопок:
          - История (request_history:{id})
          - Вложения (show_attachments:{id})
        """
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("🕘 История", callback_data=f"request_history:{order.id}"),
            types.InlineKeyboardButton("📎 Вложения", callback_data=f"show_attachments:{order.id}")
        )
        return kb

    # -------------------- Показываем меню периодов (инлайн) --------------------

    @bot.callback_query_handler(func=lambda c: c.data == "all_requests_menu")
    def cb_all_requests_menu(call: types.CallbackQuery):
        """
        Показывает инлайн клавиатуру выбора периода: неделя / месяц / всё.
        callback_data для опций: mgr_requests:week / mgr_requests:month / mgr_requests:all
        """
        bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("🗓 За неделю", callback_data="mgr_requests:week"),
            types.InlineKeyboardButton("🗓 За месяц", callback_data="mgr_requests:month")
        )
        kb.add(types.InlineKeyboardButton("📊 За всё", callback_data="mgr_requests:all"))
        bot.send_message(call.message.chat.id, "Выберите период для списка заявок:", reply_markup=kb)

    # Также — поддержка текстовой/реплай кнопки "📋 Все заявки" если такая есть в меню:
    @bot.message_handler(func=lambda m: m.text == "📋 Все заявки")
    def msg_all_requests_menu(message: types.Message):
        """
        Точка входа если нажали текстовую кнопку "📋 Все заявки" — показывает тот же inline menu.
        """
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("🗓 За неделю", callback_data="mgr_requests:week"),
            types.InlineKeyboardButton("🗓 За месяц", callback_data="mgr_requests:month")
        )
        kb.add(types.InlineKeyboardButton("📊 За всё", callback_data="mgr_requests:all"))
        bot.send_message(message.chat.id, "Выберите период для списка заявок:", reply_markup=kb)

    # -------------------- Обработка выбора периода --------------------

    @bot.callback_query_handler(func=lambda c: c.data.startswith("mgr_requests:"))
    def cb_mgr_requests_period(call: types.CallbackQuery):
        """
        Обрабатывает выбор периода и выводит список заявок.
        Если вызывающий — MANAGER: показывает все заявки.
        Если DISPATCHER: показывает только заявки, где он — dispatcher.
        """
        bot.answer_callback_query(call.id)
        user = _get_user_from_update(call)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден.")
            return

        # Выбор периода
        try:
            _, period = call.data.split(":", 1)
        except Exception:
            bot.answer_callback_query(call.id, "Неверный параметр.")
            return

        now = datetime.now()
        if period == "week":
            since = now - timedelta(days=7)
            title = "Заявки за неделю"
        elif period == "month":
            since = now - timedelta(days=30)
            title = "Заявки за месяц"
        else:  # all
            since = None
            title = "Все заявки"

        # Формируем запрос в зависимости от роли
        if int(user.role) == int(UserRole.MANAGER):
            q = Order.select().order_by(Order.datetime.desc())
            if since:
                q = q.where(Order.datetime >= since)
        elif int(user.role) == int(UserRole.DISPATCHER):
            q = Order.select().where(Order.dispatcher == user).order_by(Order.datetime.desc())
            if since:
                q = q.where(Order.datetime >= since)
        else:
            bot.send_message(call.message.chat.id, "❌ Доступ запрещён для просмотра всех заявок.")
            return

        orders = list(q)
        if not orders:
            bot.send_message(call.message.chat.id, f"📭 {title}: заявок нет.")
            return

        # Отправляем заголовок и карточки
        bot.send_message(call.message.chat.id, f"📋 {title} — найдено: {len(orders)}")
        for o in orders:
            text = _format_order_brief(o)
            kb = _build_history_attachments_markup(o)
            bot.send_message(call.message.chat.id, text, reply_markup=kb)

    # --- конец register_manager_requests_handlers ---


    # 📌 Переназначение водителя
    @bot.callback_query_handler(func=lambda c: c.data == "reassign_driver")
    def cb_reassign_driver(call: types.CallbackQuery):
        order_id = call.message.text.split()[0].replace("#", "")  # допустим в тексте заявки есть #id
        order = Order.get_or_none(Order.id == int(order_id))
        if not order:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена.")
            return

        drivers = User.select().where(User.role == int(UserRole.DRIVER))
        kb = types.InlineKeyboardMarkup()
        for d in drivers:
            kb.add(types.InlineKeyboardButton(
                f"{d.first_name} {d.last_name or ''}", callback_data=f"assign_driver:{order.id}:{d.id}"
            ))
        bot.send_message(call.message.chat.id, "Выбери нового водителя:", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("assign_driver:"))
    def cb_assign_driver(call: types.CallbackQuery):
        _, order_id, driver_id = call.data.split(":")
        order = Order.get_or_none(Order.id == int(order_id))
        driver = User.get_or_none(User.id == int(driver_id))
        if not order or not driver:
            bot.answer_callback_query(call.id, "❌ Ошибка.")
            return

        order.assigned_driver = driver
        order.status = int(OrderStatus.CONFIRMED)
        order.save()

        bot.edit_message_text(f"✅ Заявка #{order.id} переназначена на {driver.first_name}",
                              call.message.chat.id, call.message.message_id)

    # ❌ Отмена заявки
    @bot.callback_query_handler(func=lambda c: c.data == "cancel_request")
    def cb_cancel_request(call: types.CallbackQuery):
        order_id = call.message.text.split()[0].replace("#", "")
        order = Order.get_or_none(Order.id == int(order_id))
        if not order:
            bot.answer_callback_query(call.id, "❌ Заявка не найдена.")
            return

        order.status = int(OrderStatus.CANCELLED)
        order.save()

        bot.edit_message_text(f"❌ Заявка #{order.id} отменена.",
                              call.message.chat.id, call.message.message_id)

    # 📤 Экспорт отчётов
    register_attachments_reports_handlers(bot)


def delete_user(user_id: int, manager_id: int) -> str:
    """
    Удаление пользователя по ID.
    - Руководитель не может удалить сам себя.
    - Пользователь помечается как неактивный (is_active = False).
    """

    if user_id == manager_id:
        return "❌ Вы не можете удалить самого себя."

    user = User.get_or_none(User.id == user_id)
    if not user:
        return f"❌ Пользователь ID {user_id} не найден."

    if not user.is_active:
        return f"⚠️ Пользователь ID {user_id} уже неактивен."

    user.is_active = False
    user.save()

    return f"🗑 Пользователь ID {user_id} ({user.first_name} {user.last_name or ''}) деактивирован."