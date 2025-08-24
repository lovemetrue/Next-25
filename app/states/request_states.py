# states/requests_states.py
from telebot.handler_backends import StatesGroup, State

class DriverStates(StatesGroup):
    waiting_comment = State()
    waiting_photo = State()
    waiting_status = State()

class RequestsStates(StatesGroup):
    # создание заявки
    order_prefix = State()
    order_driver = State()
    order_from_addr = State()
    order_to_addr = State()
    order_cargo = State()
    order_weight_volume = State()
    order_comment = State()
    order_file = State()

    show_attachments = State()  # ожидание ввода ID заявки для просмотра вложений (reply flow)
    export_reports = State()  # ожидание выбора периода экспорта
    export_custom_from = State()  # ожидание начальной даты кастомного периода
    export_custom_to = State()  # ожидание конечной даты кастомного периода

    # фильтрация заявок
    filter_orders = State()

    # редактирование (универсально: храним в state имя + id: "edit_from:123")
    edit_from = State()
    edit_to = State()
    edit_dt = State()
    edit_comment = State()
    edit_cargo = State()
    edit_weight = State()

    # назначение и комментарий водителя
    assign_driver = State()
    driver_comment = State()
    driver_attach = State()

    # отмена с причиной
    cancel_reason = State()

    # чат по заявке
    chat = State()