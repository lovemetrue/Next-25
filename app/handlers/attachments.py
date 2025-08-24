# handlers/export_orders.py
import io
import os
import tempfile
from datetime import datetime, timedelta
from typing import List, Optional

from telebot import TeleBot, types

# Excel
from openpyxl import Workbook

# PDF (reportlab) + регистрация TTF-шрифтов для кириллицы
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from database.models import Order, User, UserRole, OrderStatus, OrderPrefix, Attachment
from states.request_states import RequestsStates
# Путь(ы) где искать TTF-шрифты (попробуем несколько типичных)
_TRY_TTF_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
]


def _register_cyrillic_font() -> Optional[str]:
    """
    Пытается зарегистрировать TTF-шрифт, поддерживающий кириллицу.
    Возвращает имя зарегистрированного шрифта или None (если не удалось).
    """
    for p in _TRY_TTF_PATHS:
        try:
            if os.path.exists(p):
                font_name = "UserCyrFont"
                pdfmetrics.registerFont(TTFont(font_name, p))
                return font_name
        except Exception:
            continue
    # Не нашли/не зарегистрировали
    return None


# Попытка зарегистрировать шрифт при импорте модуля
_REGISTERED_FONT = _register_cyrillic_font()


def register_attachments_reports_handlers(bot: TeleBot):
    """
    Регистрирует хендлеры экспорта заявок в Excel / PDF:
    - Шаг 1: пользователь выбирает период (неделя / месяц / всё)
    - Шаг 2: пользователь выбирает формат (Excel / PDF)
    Экспортируем только текстовые поля таблицы orders, включая префикс заявки (OrderPrefix.label).
    Права:
      - MANAGER (руководитель) видит все заявки
      - DISPATCHER видит только свои заявки (Order.dispatcher == user)
      - другие роли — отказ
    """

    # -------------------- Вспомогательные --------------------

    def _get_user_from_update(update) -> Optional[User]:
        """
        Вернуть User по update (callback_query или message) или None.
        """
        from_user = getattr(update, "from_user", None)
        if not from_user:
            return None
        return User.get_or_none(User.tg_id == from_user.id)

    def _fetch_orders_for_user(user: User, period: str) -> List[Order]:
        """
        Вернуть список Order в соответствии с ролью user и периодом.
        period in {"week", "month", "all"}.
        """
        now = datetime.now()
        q = Order.select().order_by(Order.datetime.desc())
        if period == "week":
            since = now - timedelta(days=7)
            q = q.where(Order.datetime >= since)
        elif period == "month":
            since = now - timedelta(days=30)
            q = q.where(Order.datetime >= since)
        # фильтр по роли
        if int(user.role) == int(UserRole.MANAGER):
            return list(q)
        elif int(user.role) == int(UserRole.DISPATCHER):
            return list(q.where(Order.dispatcher == user))
        else:
            return []

    def _row_from_order(o: Order) -> List:
        """
        Собирает строку-представление заявки для таблицы/пдф.
        Включает: ID, префикс(с меткой), статус(метка), дата, откуда, куда, диспетчер, водитель, тип груза, вес/объём, комментарий
        """
        try:
            prefix_label = OrderPrefix(o.prefix).label if getattr(o, "prefix", None) is not None else ""
        except Exception:
            prefix_label = ""
        status_label = OrderStatus(o.status).label if getattr(o, "status", None) is not None else ""
        dt_text = o.datetime.strftime("%d.%m.%Y %H:%M") if getattr(o, "datetime", None) else ""
        dispatcher = (o.dispatcher.first_name if getattr(o, "dispatcher", None) else "") or ""
        driver = (o.driver.first_name if getattr(o, "driver", None) else "") or ""
        return [
            o.id,
            prefix_label,
            status_label,
            dt_text,
            o.from_addr or "",
            o.to_addr or "",
            dispatcher,
            driver,
            o.cargo_type or "",
            o.weight_volume or "",
            (o.comment or "")
        ]

    # -------------------- Генерация Excel (openpyxl -> temp file) --------------------

    def _generate_excel_file(orders: List[Order], tmp_path: str):
        """
        Записывает Excel-файл на tmp_path.
        """
        wb = Workbook()
        ws = wb.active
        ws.title = "orders"

        headers = ["ID", "Префикс", "Статус", "Дата", "Откуда", "Куда", "Диспетчер", "Водитель", "Тип груза", "Вес/объём", "Комментарий"]
        ws.append(headers)

        for o in orders:
            ws.append(_row_from_order(o))

        wb.save(tmp_path)

    # -------------------- Генерация PDF (reportlab -> temp file) --------------------

    def _generate_pdf_file(orders: List[Order], tmp_path: str):
        """
        Записывает PDF на tmp_path. Поддерживает кириллицу, если удалось зарегистрировать шрифт.
        """
        c = canvas.Canvas(tmp_path, pagesize=A4)
        width, height = A4
        x_margin = 40
        y = height - 40
        line_height = 12

        title_font = _REGISTERED_FONT if _REGISTERED_FONT else "Helvetica-Bold"
        normal_font = _REGISTERED_FONT if _REGISTERED_FONT else "Helvetica"

        # заголовок
        c.setFont(title_font, 14)
        c.drawString(x_margin, y, "Отчёт по заявкам")
        y -= 20

        c.setFont(normal_font, 9)

        for o in orders:
            row = _row_from_order(o)
            # формируем читаемую строку
            line = (
                f"#{row[0]} | {row[1]} | {row[2]} | {row[3]} | "
                f"{row[4]} → {row[5]} | Дисп.: {row[6]} | Вод.: {row[7]} | {row[8]} | {row[9]}"
            )
            # если очень длинная строка — разбиваем
            max_len = 180  # примерный лимит символов в строке
            if len(line) <= max_len:
                c.drawString(x_margin, y, line)
                y -= line_height
            else:
                # разбиваем по словам
                words = line.split(" ")
                cur = ""
                for w in words:
                    if len(cur) + len(w) + 1 <= max_len:
                        cur += (w + " ")
                    else:
                        c.drawString(x_margin, y, cur.strip())
                        y -= line_height
                        cur = w + " "
                if cur:
                    c.drawString(x_margin, y, cur.strip())
                    y -= line_height

            # комментарий (если есть) — отдельной строкой (обрезаем при необходимости)
            comment = row[10] or ""
            if comment:
                comment_preview = comment if len(comment) <= 200 else (comment[:197] + "...")
                c.drawString(x_margin + 10, y, f"Комментарий: {comment_preview}")
                y -= line_height

            # page break
            if y < 60:
                c.showPage()
                c.setFont(normal_font, 9)
                y = height - 40

        c.save()

    ### show attachments
    def _can_view_attachments(user: User, order: Order) -> bool:
        """
        Право просмотра вложений: руководитель (manager) видит все.
        Dispatcher видит заявки где он dispatcher.
        Driver — только свои.
        """
        if not user or not order:
            return False
        if int(user.role) == int(UserRole.MANAGER):
            return True
        if int(user.role) == int(UserRole.DISPATCHER):
            return (order.dispatcher and order.dispatcher.id == user.id)
        if int(user.role) == int(UserRole.DRIVER):
            return (order.driver and order.driver.id == user.id)
        # По умолчанию — запрет
        return False

    def _send_attachments_list(chat_id: int, order: Order):
        """
        Отправляет список вложений (фото/документы) по заявке order в chat_id.
        Если attachments нет — сообщает.
        """
        atts = list(Attachment.select().where(Attachment.order == order))
        if not atts:
            bot.send_message(chat_id, f"📎 В заявке #{order.id} нет вложений.")
            return

        bot.send_message(chat_id, f"📎 Вложения для заявки #{order.id} ({len(atts)}):")
        for a in atts:
            uploader = a.uploaded_by.first_name if getattr(a, "uploaded_by", None) else "—"
            caption = (a.caption or "").strip()
            meta = f"Загружено: {uploader}"
            # Если есть поле created_at
            if getattr(a, "created_at", None):
                meta += f" | {a.created_at.strftime('%d.%m.%Y %H:%M')}"
            full_caption = (caption + "\n\n" + meta).strip()
            try:
                if a.file_type == "image":
                    bot.send_photo(chat_id, a.file_id, caption=full_caption)
                else:
                    bot.send_document(chat_id, a.file_id, caption=full_caption)
            except Exception as e:
                logger.debug("Не удалось отправить вложение %s: %s", getattr(a, "id", "?"), e)
                # Вместо файла отправляем описание
                bot.send_message(chat_id, f"[Не удалось переслать файл]\n{full_caption}")

    # -------------------- INLINE: показать вложения по карточке --------------------
    @bot.callback_query_handler(func=lambda c: c.data.startswith("show_attachments:"))
    def cb_show_attachments_inline(call: types.CallbackQuery):
        """
        Inline callback для показа вложений по заявке.
        callback_data: show_attachments:{order_id}
        """
        bot.answer_callback_query(call.id)
        try:
            order_id = int(call.data.split(":", 1)[1])
        except Exception:
            bot.answer_callback_query(call.id, "Неверный идентификатор заявки.")
            return

        order = Order.get_or_none(Order.id == order_id)
        user = User.get_or_none(User.tg_id == call.from_user.id)
        if not order:
            bot.answer_callback_query(call.id, "Заявка не найдена.")
            return

        if not _can_view_attachments(user, order):
            bot.answer_callback_query(call.id, "❌ У вас нет права просматривать вложения этой заявки.")
            return

        _send_attachments_list(call.message.chat.id, order)

    # -------------------- REPLY FLOW: кнопка "📎 Вложения" --------------------
    @bot.message_handler(func=lambda m: m.text == "📎 Вложения")
    def attachments_entry(message: types.Message):
        """
        Reply-кнопка: запускает flow, где пользователь вводит ID заявки для показа вложений.
        """
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Ошибка: вы не зарегистрированы.")
            return

        bot.set_state(message.from_user.id, message.chat.id, RequestsStates.show_attachments)
        bot.send_message(message.chat.id, "🔎 Введите ID заявки (например: 123 или #123):")

    @bot.message_handler(state=RequestsStates.show_attachments, content_types=["text"])
    def attachments_input(message: types.Message):
        """
        Обработка введённого ID заявки — показывает вложения, если есть право.
        """
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Ошибка: вы не зарегистрированы.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        oid = _parse_order_id(message.text)
        if not oid:
            bot.send_message(message.chat.id, "❌ Не удалось распознать ID. Попробуйте ещё раз или отправьте /stop.")
            return

        order = Order.get_or_none(Order.id == oid)
        if not order:
            bot.send_message(message.chat.id, f"❌ Заявка #{oid} не найдена.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        if not _can_view_attachments(user, order):
            bot.send_message(message.chat.id, "❌ У вас нет права просматривать вложения этой заявки.")
            bot.delete_state(message.from_user.id, message.chat.id)
            return

        _send_attachments_list(message.chat.id, order)
        bot.delete_state(message.from_user.id, message.chat.id)

    # -------------------- HANDLERS --------------------

    @bot.message_handler(func=lambda m: m.text == "📤 Экспорт отчетов")
    def msg_export_menu(message: types.Message):
        """
        Старт: выбор периода экспорта.
        """
        user = _get_user_from_update(message)
        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден.")
            return

        if int(user.role) not in (int(UserRole.DISPATCHER), int(UserRole.MANAGER)):
            bot.send_message(message.chat.id, "❌ Доступен только диспетчеру/руководителю.")
            return

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("🗓 Неделя", callback_data="export_period:week"),
            types.InlineKeyboardButton("🗓 Месяц", callback_data="export_period:month"),
            types.InlineKeyboardButton("📊 Всё", callback_data="export_period:all"),
        )
        bot.send_message(message.chat.id, "Выберите период для экспорта:", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("export_period:"))
    def cb_export_period(call: types.CallbackQuery):
        """
        После выбора периода — показать выбор формата (Excel / PDF).
        """
        bot.answer_callback_query(call.id)
        user = _get_user_from_update(call)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден.")
            return

        if int(user.role) not in (int(UserRole.DISPATCHER), int(UserRole.MANAGER)):
            bot.answer_callback_query(call.id, "❌ Доступ запрещён.")
            return

        _, period = call.data.split(":", 1)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📑 Excel", callback_data=f"export_do:{period}:excel"),
            types.InlineKeyboardButton("📄 PDF", callback_data=f"export_do:{period}:pdf"),
        )
        try:
            bot.edit_message_text("Выберите формат экспорта:", call.message.chat.id, call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "Выберите формат экспорта:", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("export_do:"))
    def cb_export_do(call: types.CallbackQuery):
        """
        Формируем файл (Excel или PDF) для выбранного периода и отправляем как документ.
        Файл сначала пишется во временный файл, затем отправляется через bot.send_document(open(tmp_path,'rb')).
        """
        bot.answer_callback_query(call.id)
        user = _get_user_from_update(call)
        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден.")
            return

        if int(user.role) not in (int(UserRole.DISPATCHER), int(UserRole.MANAGER)):
            bot.answer_callback_query(call.id, "❌ Доступ запрещён.")
            return

        try:
            _, period, fmt = call.data.split(":", 2)
        except Exception:
            bot.answer_callback_query(call.id, "❌ Неверные параметры.")
            return

        orders = _fetch_orders_for_user(user, period)
        if not orders:
            bot.send_message(call.message.chat.id, "📭 За выбранный период заявок нет.")
            return

        # создаём временный файл с подходящим суффиксом
        suffix = ".xlsx" if fmt == "excel" else ".pdf"
        tmp = tempfile.NamedTemporaryFile(prefix=f"orders_{period}_", suffix=suffix, delete=False)
        tmp_path = tmp.name
        tmp.close()  # мы будем записывать в него отдельно

        try:
            if fmt == "excel":
                _generate_excel_file(orders, tmp_path)
            elif fmt == "pdf":
                _generate_pdf_file(orders, tmp_path)
            else:
                bot.send_message(call.message.chat.id, "❌ Неподдерживаемый формат.")
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                return

            # отправляем файл (открываем как rb)
            with open(tmp_path, "rb") as f:
                # не используем keyword 'filename' чтобы избежать ошибок совместимости
                bot.send_document(call.message.chat.id, f)

        except Exception as e:
            # логируем и сообщаем пользователю
            try:
                bot.send_message(call.message.chat.id, "❌ Ошибка при формировании/отправке файла.")
            except Exception:
                pass
            raise

        finally:
            # чистим временный файл
            try:
                os.remove(tmp_path)
            except Exception:
                pass

# handlers/attachments_reports.py
# import io
# from reportlab.pdfgen import canvas
# import xlsxwriter
#
# from datetime import datetime, timedelta
# from telebot import TeleBot, types
# from openpyxl import Workbook
# from reportlab.lib.pagesizes import A4
# from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
# from reportlab.lib.styles import getSampleStyleSheet
#
# from database.models import User, Order, Attachment, OrderStatusHistory, OrderMessage, OrderStatus, UserRole
# from states.request_states import RequestsStates
# import logging
#
# logger = logging.getLogger(__name__)
#
#
# def register_attachments_reports_handlers(bot: TeleBot):
#     """
#     Регистрирует:
#       - reply-flow: '📎 Вложения' -> ввод ID заявки -> вывод всех вложений
#       - inline callback: 'show_attachments:{order_id}' -> вывести вложения по заявке
#       - экспорт отчетов (Excel / PDF) через диалог
#       - команда/кнопка '📚 Полная история' — доступно только руководителю: получает Excel с чатами и вложениями
#     """
#     # -------------------- ЭКСПОРТ: клавиатура выбора периода --------------------
#     def _export_period_kb():
#         """
#         Inline keyboard для выбора периода экспорта.
#         """
#         kb = types.InlineKeyboardMarkup(row_width=1)
#         kb.add(
#             types.InlineKeyboardButton("7 дней", callback_data="export_period:7"),
#             types.InlineKeyboardButton("30 дней", callback_data="export_period:30"),
#         )
#         kb.add(
#             types.InlineKeyboardButton("За всё время", callback_data="export_period:all"),
#             types.InlineKeyboardButton("Выбрать период", callback_data="export_period:custom"),
#         )
#         return kb
#
#     @bot.message_handler(func=lambda m: m.text == "📤 Экспорт отчетов")
#     def export_entry(message: types.Message):
#         """
#         Reply-кнопка 'Экспорт отчетов' — запускает выбор периода.
#         Доступно для диспетчера и руководителя.
#         """
#         user = User.get_or_none(User.tg_id == message.from_user.id)
#         if not user or int(user.role) not in (int(UserRole.DISPATCHER), int(UserRole.MANAGER)):
#             bot.send_message(message.chat.id, "❌ Эта функция доступна только диспетчеру/руководителю.")
#             return
#
#         bot.send_message(message.chat.id, "Укажите период:", reply_markup=_export_period_kb())
#
#     def _format_orders(period: str):
#         """
#         Возвращает queryset заказов по периоду.
#         """
#         now = datetime.now()
#         if period == "week":
#             since = now - timedelta(days=7)
#             q = Order.select().where(Order.datetime >= since).order_by(Order.datetime.desc())
#         elif period == "month":
#             since = now - timedelta(days=30)
#             q = Order.select().where(Order.datetime >= since).order_by(Order.datetime.desc())
#         else:  # all
#             q = Order.select().order_by(Order.datetime.desc())
#         return list(q)
#
#     def _export_excel(orders: list[Order]) -> io.BytesIO:
#         """
#         Генерирует Excel (xlsx) со всеми полями заказов.
#         """
#         output = io.BytesIO()
#         workbook = xlsxwriter.Workbook(output, {"in_memory": True})
#         ws = workbook.add_worksheet("Orders")
#
#         headers = ["ID", "Дата", "Откуда", "Куда", "Статус", "Водитель", "Диспетчер"]
#         for col, h in enumerate(headers):
#             ws.write(0, col, h)
#
#         for row, o in enumerate(orders, start=1):
#             ws.write(row, 0, o.id)
#             ws.write(row, 1, o.datetime.strftime("%d.%m.%Y %H:%M") if o.datetime else "")
#             ws.write(row, 2, o.from_addr or "")
#             ws.write(row, 3, o.to_addr or "")
#             ws.write(row, 4, OrderStatus(o.status).label if o.status else "")
#             ws.write(row, 5, f"{o.driver if o.driver else ''} {o.driver.last_name if o.driver else ''}")
#             ws.write(row, 6, f"{o.dispatcher if o.dispatcher else ''}")
#
#         workbook.close()
#         output.seek(0)
#         return output
#
#     def _export_pdf(orders: list[Order]) -> io.BytesIO:
#         """
#         Генерирует PDF (A4) со всеми полями заказов.
#         """
#         output = io.BytesIO()
#         c = canvas.Canvas(output, pagesize=A4)
#         width, height = A4
#         y = height - 40
#
#         c.setFont("Helvetica-Bold", 14)
#         c.drawString(40, y, "Отчёт по заявкам")
#         y -= 30
#
#         c.setFont("Helvetica", 10)
#         for o in orders:
#             line = (
#                 f"#{o.id} | {o.datetime.strftime('%d.%m.%Y %H:%M') if o.datetime else '—'} | "
#                 f"{o.from_addr or '—'} → {o.to_addr or '—'} | "
#                 f"{OrderStatus(o.status).label if o.status else '—'} | "
#                 f"Водитель: {o.driver.first_name if o.driver else '—'} | "
#                 f"Диспетчер: {o.dispatcher.first_name if o.dispatcher else '—'}"
#             )
#             c.drawString(40, y, line)
#             y -= 15
#             if y < 40:
#                 c.showPage()
#                 y = height - 40
#                 c.setFont("Helvetica", 10)
#
#         c.save()
#         output.seek(0)
#         return output
#
#         # --- Хендлеры ---
#
#     @bot.message_handler(func=lambda m: m.text == "📤 Экспорт отчётов")
#     def msg_export_menu(message: types.Message):
#         """
#         Стартовое меню экспорта: выбор периода.
#         """
#         kb = types.InlineKeyboardMarkup(row_width=2)
#         kb.add(
#             types.InlineKeyboardButton("🗓 Неделя", callback_data="export_period:week"),
#             types.InlineKeyboardButton("🗓 Месяц", callback_data="export_period:month"),
#             types.InlineKeyboardButton("📊 Всё", callback_data="export_period:all"),
#         )
#         bot.send_message(message.chat.id, "Выберите период для экспорта:", reply_markup=kb)
#
#     @bot.callback_query_handler(func=lambda c: c.data.startswith("export_period:"))
#     def cb_export_period(call: types.CallbackQuery):
#         """
#         После выбора периода — предлагаем выбрать формат (Excel/PDF).
#         """
#         _, period = call.data.split(":", 1)
#         kb = types.InlineKeyboardMarkup(row_width=2)
#         kb.add(
#             types.InlineKeyboardButton("📑 Excel", callback_data=f"export_format:{period}:excel"),
#             types.InlineKeyboardButton("📄 PDF", callback_data=f"export_format:{period}:pdf"),
#         )
#         bot.edit_message_text(
#             "Выберите формат экспорта:",
#             call.message.chat.id,
#             call.message.message_id,
#             reply_markup=kb,
#         )
#
#     @bot.callback_query_handler(func=lambda c: c.data.startswith("export_format:"))
#     def cb_export_format(call: types.CallbackQuery):
#         """
#         Формируем и отправляем файл отчёта.
#         """
#         _, period, fmt = call.data.split(":", 2)
#         orders = _format_orders(period)
#
#         if not orders:
#             bot.answer_callback_query(call.id, "Нет заявок за выбранный период.")
#             return
#
#         if fmt == "excel":
#             file = _export_excel(orders)
#             bot.send_document(call.message.chat.id, file, visible_file_name=f"orders_{period}.xlsx")
#         elif fmt == "pdf":
#             file = _export_pdf(orders)
#             bot.send_document(call.message.chat.id, file, visible_file_name=f"orders_{period}.pdf")
#         else:
#             bot.answer_callback_query(call.id, "Неизвестный формат.")
#
#     # --- конец register_attachments_reports_handlers ---