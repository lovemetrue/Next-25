# handlers/start.py
import re
import logging
from loguru import logger
from datetime import datetime
from telebot import TeleBot, types
import phonenumbers  # пакет phonenumberslite
from app.database.models import User, UserRole, db
from app.keyboards.main_menu import get_main_menu
from telebot.custom_filters import StateFilter
from telebot.handler_backends import StatesGroup, State

# === [NEW] попытка импортировать настройку из БД (опционально) ===
try:
    # Добавь простую KV-модель в database.models при желании:
    # class Setting(Model):
    #     key = CharField(unique=True)
    #     value = CharField(null=True)
    #     ...
    from database.models import Setting  # type: ignore
except Exception:
    Setting = None  # fallback на in-memory

# === [NEW] лимит диспетчеров ===
DEFAULT_MAX_DISPATCHERS = 3
_MAX_DISPATCHERS_CACHE = DEFAULT_MAX_DISPATCHERS  # на случай отсутствия модели Setting


def _get_max_dispatchers() -> int:
    """
    Возвращает максимальное количество активных диспетчеров.
    Сначала пытается прочитать из таблицы Setting(key='max_dispatchers'), иначе — из in-memory кэша.
    """
    global _MAX_DISPATCHERS_CACHE
    if Setting is not None:
        try:
            s = Setting.get_or_none(Setting.key == "max_dispatchers")
            if s and str(s.value).strip().isdigit():
                return int(s.value)
        except Exception:
            logger.exception("Failed to read Setting(max_dispatchers)")
    return _MAX_DISPATCHERS_CACHE


def _set_max_dispatchers(n: int) -> None:
    """
    Сохраняет максимальное количество активных диспетчеров.
    Если доступна модель Setting — пишет в БД, иначе обновляет in-memory кэш.
    """
    global _MAX_DISPATCHERS_CACHE
    if Setting is not None:
        try:
            s, created = Setting.get_or_create(key="max_dispatchers", defaults={"value": str(n)})
            if not created:
                s.value = str(n)
                s.save()
            return
        except Exception:
            logger.exception("Failed to upsert Setting(max_dispatchers)")
    _MAX_DISPATCHERS_CACHE = n


def _active_dispatchers_count() -> int:
    """Количество активных пользователей с ролью диспетчера."""
    try:
        return (User
                .select()
                .where((User.role == int(UserRole.DISPATCHER)) & (User.is_active == True))
                .count())
    except Exception:
        logger.exception("Failed to count active dispatchers")
        return 0


def _active_manager_exists() -> bool:
    """Есть ли активный руководитель в системе."""
    try:
        return (User
                .select()
                .where((User.role == int(UserRole.MANAGER)) & (User.is_active == True))
                .exists())
    except Exception:
        logger.exception("Failed to check active manager")
        return False

# Настройка логирования
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ====== Состояния FSM регистрации ======
class RegStates(StatesGroup):
    choose_role = State()
    phone_or_empid = State()
    confirm = State()


# ====== Публичная точка подключения хэндлеров ======
def register_handlers(bot: TeleBot) -> None:
    """
    Подключает хэндлеры регистрации к переданному экземпляру TeleBot.
    Предполагается, что в точке запуска бота добавлен state_storage.
    """
    # на всякий случай добавим StateFilter (безопасно вызывать многократно)
    try:
        bot.add_custom_filter(StateFilter(bot))
    except Exception as e:
        logger.debug(f"StateFilter already added or failed: {e}")

    # /start
    @bot.message_handler(commands=["start", "register"])
    def cmd_start(message: types.Message):
        """
        Точка входа регистрации. Если пользователь активен — показывает роль и меню.
        Иначе — переводит в выбор роли; кнопку менеджера скрываем, если уже существует активный руководитель.
        """
        user = _get_user_by_tg(message.from_user.id)
        if user and user.is_active:
            role_name = UserRole(user.role).label
            text = (
                f"👋 Здравствуйте, {message.from_user.first_name or 'друг'}!\n"
                f"Вы уже зарегистрированы как: <b>{role_name}</b>.\n\n"
            )
            bot.send_message(message.chat.id, text, parse_mode="HTML")
            return

        # начинаем регистрацию
        bot.set_state(message.from_user.id, RegStates.choose_role, message.chat.id)
        _ask_role(bot, message.chat.id)

        # Выбор роли (callback от инлайн-кнопок)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("role:"),
                                state=RegStates.choose_role)
    def cb_choose_role(call: types.CallbackQuery):
        """
        Обрабатывает выбор роли. Правила:
          - Если роль MANAGER уже занята активным пользователем — запрещаем.
          - Если выбран DISPATCHER и достигнут лимит — показываем предупреждение и остаёмся в выборе роли.
        """
        role_code = call.data.split(":", 1)[1]
        try:
            role = UserRole.from_code(role_code)
        except ValueError:
            bot.answer_callback_query(call.id, "Неизвестная роль.")
            return

        # Жёстко блокируем выбор MANAGER, если уже есть активный руководитель
        if role is UserRole.MANAGER and _active_manager_exists():
            bot.answer_callback_query(call.id, "❌ Руководитель уже создан. Выбери другую роль.")
            # переотрисуем клавиатуру (без кнопки руководителя)
            try:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=_roles_keyboard_hide_manager()
                )
            except Exception:
                pass
            return

        # Если выбран dispatcher — проверяем лимит
        if role is UserRole.DISPATCHER:
            max_d = _get_max_dispatchers()
            cur = _active_dispatchers_count()
            if cur >= max_d:
                bot.answer_callback_query(call.id,
                                          f"❌ Достигнут лимит активных диспетчеров: {max_d}. Обратитесь к руководителю.")
                return

        # сохраняем роль и двигаемся дальше
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data["role"] = int(role)

        bot.answer_callback_query(call.id)
        bot.set_state(call.from_user.id, RegStates.phone_or_empid, call.message.chat.id)
        _ask_phone_or_id(bot, call.message.chat.id)

    # Приём телефона (как контакт) или ID (текст)
    @bot.message_handler(content_types=["contact", "text"], state=RegStates.phone_or_empid)
    def msg_phone_or_id(message: types.Message):
        """
        Получаем номер телефона или табельный ID. Номер можно прислать как контакт.
        """
        emp_id: str | None = None
        phone_e164: str | None = None

        if message.content_type == "contact" and message.contact:
            if message.contact.user_id and message.contact.user_id != message.from_user.id:
                bot.reply_to(message, "Пожалуйста, отправьте номер <b>своего</b> телефона.", parse_mode="HTML")
                return

            raw = message.contact.phone_number
            phone_e164 = _process_contact_phone(raw)
            if not phone_e164:
                bot.reply_to(message, "Номер не распознан. Введите в формате +79991234567.")
                return
        else:
            raw = (message.text or "").strip()
            if _looks_like_phone(raw):
                phone_e164 = _normalize_phone(raw)
                if not phone_e164:
                    bot.reply_to(message, "Номер некорректный. Пример: +79991234567 или отправьте контакт.")
                    return
            # Если хочешь поддержать табельный ID — раскомментируй:
            # else:
            #     if len(raw) < 3:
            #         bot.reply_to(message, "ID сотрудника слишком короткий.")
            #         return
            #     emp_id = raw

        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            if phone_e164:
                data["phone"] = phone_e164
            if emp_id:
                data["employee_id"] = emp_id
            data["first_name"] = message.from_user.first_name or ""
            data["last_name"] = message.from_user.last_name or ""
            data["username"] = message.from_user.username or ""

        bot.set_state(message.from_user.id, RegStates.confirm, message.chat.id)
        _ask_confirm(bot, message.chat.id, message.from_user.id)
        # Подтверждение (инлайн-кнопки)

    @bot.callback_query_handler(func=lambda c: c.data in ("reg:confirm", "reg:edit", "reg:cancel"),
                                state=RegStates.confirm)
    def cb_confirm(call: types.CallbackQuery):
        """
        Подтверждение регистрации. Повторно проверяем лимиты:
          - MANAGER — запрещаем, если уже есть активный;
          - DISPATCHER — атомарно проверяем, что лимит ещё не превышен.
        """
        if call.data == "reg:edit":
            bot.answer_callback_query(call.id)
            bot.set_state(call.from_user.id, RegStates.phone_or_empid, call.message.chat.id)
            _ask_phone_or_id(bot, call.message.chat.id, text="Измените данные. Пришлите телефон сотрудника")
            return

        if call.data == "reg:cancel":
            bot.answer_callback_query(call.id, "Регистрация отменена.")
            bot.delete_state(call.from_user.id, call.message.chat.id)
            bot.edit_message_text("❌ Регистрация отменена.", call.message.chat.id, call.message.message_id)
            return

        # Подтверждение регистрации
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            role = UserRole(int(data["role"]))
            phone = data.get("phone")
            employee_id = data.get("employee_id")
            first_name = data.get("first_name", "")
            last_name = data.get("last_name", "")
            username = data.get("username", "")

        if not phone and not employee_id:
            bot.answer_callback_query(call.id, "Телефон обязателен для заполнения.")
            return

        # Жёсткая проверка MANAGER
        if role is UserRole.MANAGER and _active_manager_exists():
            bot.answer_callback_query(call.id, "❌ Руководитель уже создан.")
            # Возвращаем к выбору роли
            bot.set_state(call.from_user.id, RegStates.choose_role, call.message.chat.id)
            _ask_role(bot, call.message.chat.id)
            return

        try:
            with db.atomic():
                # При сохранении DISPETCHER — повторно проверяем лимит
                if role is UserRole.DISPATCHER:
                    max_d = _get_max_dispatchers()
                    cur = _active_dispatchers_count()
                    if cur >= max_d:
                        bot.answer_callback_query(call.id, f"❌ Лимит активных диспетчеров: {max_d}.")
                        bot.set_state(call.from_user.id, RegStates.choose_role, call.message.chat.id)
                        _ask_role(bot, call.message.chat.id)
                        return

                user = _get_user_by_tg(call.from_user.id)
                if user:
                    user.role = int(role)
                    user.phone = phone
                    user.employee_id = employee_id
                    user.first_name = first_name
                    user.last_name = last_name
                    user.username = username
                    user.is_active = True
                    user.updated_at = datetime.now()
                    user.save()
                else:
                    user = User.create(
                        tg_id=call.from_user.id,
                        tg_chat_id=call.message.chat.id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        role=int(role),
                        phone=phone,
                        employee_id=employee_id,
                        is_active=True,
                    )
        except Exception as e:
            logger.exception("Failed to upsert user")
            bot.answer_callback_query(call.id, "Ошибка сохранения. Попробуйте ещё раз позже.")
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text=(
                f"Роль: <b>{role.label}</b>\n"
                f"{'Телефон: ' + (user.phone or '') if user.phone else ''}"
                f"{'ID: ' + (user.employee_id or '') if user.employee_id else ''}"
            ),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
        )
        bot.delete_state(call.from_user.id, call.message.chat.id)
        bot.send_message(call.message.chat.id,
                         "✅ Регистрация завершена!",
                         reply_markup=get_main_menu(role.name.lower()))
    # Фоллбек по отмене
    @bot.message_handler(commands=["cancel"])
    def cmd_cancel(message: types.Message):
        bot.delete_state(message.from_user.id, message.chat.id)
        bot.send_message(message.chat.id, "Отменено. Можете начать заново командой /start.")



# # ====== Вспомогательные функции UI ======
# def _ask_role(bot: TeleBot, chat_id: int):
#     kb = types.InlineKeyboardMarkup(row_width=1)
#     kb.add(
#         types.InlineKeyboardButton("🧭 Диспетчер", callback_data="role:dispatcher"),
#         types.InlineKeyboardButton("🚚 Водитель", callback_data="role:driver"),
#         types.InlineKeyboardButton("📊 Руководитель", callback_data="role:manager"),
#     )
#     bot.send_message(chat_id, "Выберите роль:", reply_markup=kb)


def _ask_phone_or_id(bot: TeleBot, chat_id: int, text: str | None = None):
    text = text or "Отправьте номер телефона через кнопку или напиши в чат"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, selective=True)
    kb.add(types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True))
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


def _ask_confirm(bot: TeleBot, chat_id: int, user_id: int):
    with bot.retrieve_data(user_id, chat_id) as data:
        role = UserRole(int(data["role"]))
        phone = data.get("phone", "—")
        emp = data.get("employee_id", "—")
        name = (data.get("first_name") or "") + " " + (data.get("last_name") or "")

    text = (
        "<b>Проверь данные:</b>\n"
        f"Роль: <b>{role.label}</b>\n"
        f"Телефон: <code>{phone}</code>\n"
        f"ID сотрудника: <code>{emp}</code>\n"
        f"Имя (из Telegram): <i>{name.strip() or '—'}</i>\n\n"
        "Подтвердить регистрацию?"
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data="reg:confirm"),
        types.InlineKeyboardButton("✏️ Изменить", callback_data="reg:edit"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="reg:cancel"),
    )
    # убираем клавиатуру контакта
    hide = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=hide)
    bot.send_message(chat_id, "Выберите действие:", reply_markup=kb)



# ====== Вспомогательные функции UI ======
def _ask_role(bot: TeleBot, chat_id: int):
    """
    Показывает клавиатуру выбора роли. Если активный руководитель уже есть — кнопку «Руководитель» не показываем.
    """
    kb = _roles_keyboard_hide_manager() if _active_manager_exists() else _roles_keyboard_full()
    bot.send_message(chat_id, "Выберите роль:", reply_markup=kb)


def _roles_keyboard_full() -> types.InlineKeyboardMarkup:
    """Полная клавиатура выбора роли (все роли)."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🧭 Диспетчер", callback_data="role:dispatcher"),
        types.InlineKeyboardButton("🚚 Водитель", callback_data="role:driver"),
        types.InlineKeyboardButton("📊 Руководитель", callback_data="role:manager"),
    )
    return kb


def _roles_keyboard_hide_manager() -> types.InlineKeyboardMarkup:
    """Клавиатура выбора роли без кнопки «Руководитель» (если менеджер уже существует)."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🧭 Диспетчер", callback_data="role:dispatcher"),
        types.InlineKeyboardButton("🚚 Водитель", callback_data="role:driver"),
    )
    return kb


# ====== Вспомогательные функции данных ======
def _get_user_by_tg(tg_id: int) -> User | None:
    try:
        return User.get_or_none(User.tg_id == tg_id)
    except Exception:
        logger.exception("User lookup failed")
        return None


def _looks_like_phone(raw: str) -> bool:
    raw = raw.strip().replace(" ", "")
    return raw.startswith("+") or raw.isdigit()


def _normalize_phone(raw: str) -> str | None:
    try:
        candidate = phonenumbers.parse(raw, None)  # None => строгий международный
        if phonenumbers.is_valid_number(candidate):
            return phonenumbers.format_number(candidate, phonenumbers.PhoneNumberFormat.E164)
        return None
    except Exception:
        return None


def _process_contact_phone(raw: str) -> str | None:
    """Обработка номера телефона из контакта Telegram (уже в правильном формате)"""
    if not raw:
        return None

    # Очищаем номер от лишних символов
    clean = re.sub(r"[^\d+]", "", raw.strip())

    # Номер из контакта обычно уже начинается с +
    if clean.startswith("+") and len(clean) >= 8:
        return clean

    # Если вдруг нет +, пробуем добавить (для России/Казахстана)
    if clean.startswith("7") and len(clean) == 11:
        return "+" + clean
    elif clean.startswith("8") and len(clean) == 11:
        return "+7" + clean[1:]

    # Если совсем не похож на номер
    if len(clean) < 8:
        return None

    return clean

