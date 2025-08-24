import re
import phonenumbers
from datetime import datetime
from typing import Union, Tuple


def validate_phone_number(phone: str) -> bool:
    """
    Валидация номера телефона.
    Поддерживает международные форматы и российские номера.
    """
    try:
        # Пытаемся распарсить номер с кодом региона Россия по умолчанию
        parsed_number = phonenumbers.parse(phone, "RU")
        return phonenumbers.is_valid_number(parsed_number)
    except phonenumbers.NumberParseException:
        # Если не удалось распарсить, пробуем простую проверку регулярным выражением
        pattern = r'^(\+7|7|8)?[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}$'
        return bool(re.match(pattern, phone))


def validate_email(email: str) -> bool:
    """Валидация email адреса"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_date(date_string: str, format: str = "%d.%m.%Y") -> bool:
    """Валидация даты"""
    try:
        datetime.strptime(date_string, format)
        return True
    except ValueError:
        return False


def validate_time(time_string: str, format: str = "%H:%M") -> bool:
    """Валидация времени"""
    try:
        datetime.strptime(time_string, format)
        return True
    except ValueError:
        return False


def validate_datetime(datetime_string: str, format: str = "%d.%m.%Y %H:%M") -> bool:
    """Валидация даты и времени"""
    try:
        datetime.strptime(datetime_string, format)
        return True
    except ValueError:
        return False


def validate_weight(weight: Union[str, int, float]) -> Tuple[bool, str]:
    """
    Валидация веса груза.
    Возвращает (is_valid, error_message)
    """
    try:
        weight_value = float(weight)
        if weight_value <= 0:
            return False, "Вес должен быть положительным числом"
        if weight_value > 100000:  # 100 тонн
            return False, "Слишком большой вес"
        return True, ""
    except (ValueError, TypeError):
        return False, "Вес должен быть числом"


def validate_volume(volume: Union[str, int, float]) -> Tuple[bool, str]:
    """
    Валидация объема груза.
    Возвращает (is_valid, error_message)
    """
    try:
        volume_value = float(volume)
        if volume_value <= 0:
            return False, "Объем должен быть положительным числом"
        if volume_value > 1000:  # 1000 м³
            return False, "Слишком большой объем"
        return True, ""
    except (ValueError, TypeError):
        return False, "Объем должен быть числом"


def validate_address(address: str) -> Tuple[bool, str]:
    """
    Валидация адреса.
    Проверяет, что адрес не пустой и имеет минимальную длину.
    """
    if not address or not address.strip():
        return False, "Адрес не может быть пустым"

    if len(address.strip()) < 5:
        return False, "Адрес слишком короткий"

    if len(address.strip()) > 500:
        return False, "Адрес слишком длинный"

    return True, ""


def validate_name(name: str) -> Tuple[bool, str]:
    """
    Валидация имени или фамилии.
    """
    if not name or not name.strip():
        return False, "Имя не может быть пустым"

    if len(name.strip()) < 2:
        return False, "Имя слишком короткое"

    if len(name.strip()) > 50:
        return False, "Имя слишком длинное"

    # Проверка на недопустимые символы
    if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-]+$', name):
        return False, "Имя содержит недопустимые символы"

    return True, ""


def validate_username(username: str) -> bool:
    """
    Валидация имени пользователя Telegram.
    """
    if not username:
        return False

    pattern = r'^[a-zA-Z0-9_]{5,32}$'
    return bool(re.match(pattern, username))


def validate_request_prefix(prefix: str) -> bool:
    """
    Валидация префикса заявки.
    """
    valid_prefixes = ['с_ндс', 'без_ндс', 'нал', 'с НДС', 'без НДС']
    return prefix.lower() in [p.lower() for p in valid_prefixes]


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """
    Санитизация пользовательского ввода.
    Удаляет потенциально опасные символы и обрезает длину.
    """
    if not text:
        return ""

    # Удаляем опасные символы
    sanitized = re.sub(r'[<>{}&|;`$]', '', text)

    # Обрезаем длину
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized.strip()


def validate_date_range(start_date_str: str, end_date_str: str,
                        format: str = "%d.%m.%Y") -> Tuple[bool, str]:
    """
    Валидация диапазона дат.
    Проверяет, что даты валидны и конечная дата не раньше начальной.
    """
    try:
        start_date = datetime.strptime(start_date_str, format)
        end_date = datetime.strptime(end_date_str, format)

        if end_date < start_date:
            return False, "Конечная дата не может быть раньше начальной"

        # Проверяем, что диапазон не слишком большой (максимум 1 год)
        if (end_date - start_date).days > 365:
            return False, "Диапазон дат не может превышать 1 год"

        return True, ""
    except ValueError:
        return False, "Неверный формат даты. Используйте ДД.ММ.ГГГГ"