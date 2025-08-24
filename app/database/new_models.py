

# database/models.py
from datetime import datetime
from enum import IntEnum
from typing import Optional

from peewee import (
    Model, SqliteDatabase, AutoField, IntegerField, CharField, BooleanField,
    DateTimeField, ForeignKeyField, TextField, FloatField
)

from app.session import db  # общий экземпляр базы


# ====== Базовая модель ======
class BaseModel(Model):
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    class Meta:
        database = db


# ====== Перечисления ======
class UserRole(IntEnum):
    DISPATCHER = 1
    DRIVER = 2
    MANAGER = 3

    @property
    def label(self) -> str:
        return {
            UserRole.DISPATCHER: "Диспетчер",
            UserRole.DRIVER: "Водитель",
            UserRole.MANAGER: "Руководитель",
        }[self]

    @staticmethod
    def from_code(code: str) -> "UserRole":
        mapping = {
            "dispatcher": UserRole.DISPATCHER,
            "driver": UserRole.DRIVER,
            "manager": UserRole.MANAGER,
        }
        if code not in mapping:
            raise ValueError("unknown role code")
        return mapping[code]


class OrderPrefix(IntEnum):
    WITH_VAT = 1        # с НДС
    WITHOUT_VAT = 2     # без НДС
    CASH = 3            # нал

    @property
    def label(self) -> str:
        return {
            OrderPrefix.WITH_VAT: "с НДС",
            OrderPrefix.WITHOUT_VAT: "без НДС",
            OrderPrefix.CASH: "нал",
        }[self]


class OrderStatus(IntEnum):
    NEW = 1
    CONFIRMED = 2
    ENROUTE_TO_LOADING = 3
    LOADING = 4
    ENROUTE = 5
    DELIVERED = 6
    CANCELLED = 7

    @property
    def label(self) -> str:
        return {
            OrderStatus.NEW: "новая",
            OrderStatus.CONFIRMED: "подтверждена",
            OrderStatus.ENROUTE_TO_LOADING: "в пути на загрузку",
            OrderStatus.LOADING: "на загрузке",
            OrderStatus.ENROUTE: "в пути",
            OrderStatus.DELIVERED: "доставлено",
            OrderStatus.CANCELLED: "отменена",
        }[self]


# ====== Пользователи ======
class User(BaseModel):
    id = AutoField()
    tg_id = IntegerField(unique=True, index=True)         # Telegram user id
    tg_chat_id = IntegerField(null=True)                  # последний чат (личка/группа)
    username = CharField(null=True)
    first_name = CharField(null=True)
    last_name = CharField(null=True)

    role = IntegerField(default=int(UserRole.DRIVER))     # UserRole
    phone = CharField(null=True, index=True)
    employee_id = CharField(null=True, index=True)

    is_active = BooleanField(default=True)

    class Meta:
        table_name = "users"


class Order(Model):
    """
    Заявка на перевозку
    """
    dispatcher = ForeignKeyField(User, backref="orders", on_delete="CASCADE")  # кто создал
    driver = ForeignKeyField(User, backref="driver_orders", null=True, on_delete="SET NULL")  # назначенный водитель

    prefix = IntegerField(default=int(OrderPrefix.WITH_VAT))  # OrderPrefix
    to_addr = CharField()
    datetime = DateTimeField()
    cargo_type = CharField(null=True)
    weight_volume = CharField(null=True)
    comment = TextField(null=True)

    status = CharField(default="new")  # new, confirmed, in_transit, delivered, canceled
    cancel_reason = TextField(null=True)

    file_path = CharField(null=True)  # накладные, фото и т.д.

    date_created = CharField(default=lambda: f"{datetime.now():{DATE_FORMAT}}")

    class Meta:
        database = db

# # ====== Заявка (перевозка) ======
# class Order(BaseModel):
#     id = AutoField()
#     prefix = IntegerField(default=int(OrderPrefix.WITH_VAT))  # OrderPrefix
#
#     created_by = ForeignKeyField(User, backref="orders_created", on_delete="RESTRICT")
#     assigned_driver = ForeignKeyField(User, backref="orders_assigned", null=True, on_delete="SET NULL")
#
#     # Параметры перевозки
#     point_a = CharField()  # адрес или геолокация в свободной форме
#     point_b = CharField()
#     exec_datetime = DateTimeField(null=True)  # дата/время выполнения
#     cargo_type = CharField(null=True)
#     weight = FloatField(null=True)    # кг/тонны по договорённости
#     volume = FloatField(null=True)    # м3
#     comment = TextField(null=True)
#
#     status = IntegerField(default=int(OrderStatus.NEW))  # OrderStatus
#     attachments_count = IntegerField(default=0)
#
#     class Meta:
#         table_name = "orders"
#         indexes = (
#             (("assigned_driver", "status"), False),
#         )


# ====== История статусов ======
class OrderStatusHistory(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="status_history", on_delete="CASCADE")
    by_user = ForeignKeyField(User, backref="status_changes", on_delete="SET NULL", null=True)
    status = IntegerField()  # OrderStatus
    note = TextField(null=True)

    class Meta:
        table_name = "order_status_history"

# database/models.py
class OrderMessage(BaseModel):
    order = ForeignKeyField(Order, backref="messages")
    sender = ForeignKeyField(User, backref="sent_messages")
    message = TextField()
    created_at = DateTimeField(default=datetime.now())

# ====== Вложения (фото, документы) ======
class Attachment(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="attachments", on_delete="CASCADE")
    uploaded_by = ForeignKeyField(User, backref="uploaded_files", on_delete="SET NULL", null=True)

    # Сохраняем всегда file_id телеграма, этого достаточно чтобы скачивать
    file_id = CharField()
    file_type = CharField()  # "photo" | "document" | ...
    caption = TextField(null=True)

    class Meta:
        table_name = "attachments"


# ====== Чат в рамках заявки ======
class ChatMessage(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="messages", on_delete="CASCADE")
    sender = ForeignKeyField(User, backref="messages", on_delete="SET NULL", null=True)
    text = TextField(null=True)
    file_id = CharField(null=True)  # если это медиа/документ
    msg_type = CharField(default="text")  # "text" | "photo" | "document" ...

    class Meta:
        table_name = "chat_messages"


# ====== Утилита инициализации таблиц ======
def create_all_tables():
    with db:
        db.create_tables([User, Order, OrderStatusHistory, Attachment, ChatMessage])

# ====== Утилита удаления строк в таблицах ======
def delete_the_row(row_id):
    """
    Удаляет строку из таблицы Users по ID
    """
    try:
        with db:
            # Удаляем напрямую по условию
            deleted_count = User.delete().where(User.id == row_id).execute()
            if deleted_count > 0:
                logger.info(f"Пользователь с ID {row_id} успешно удалён")
                return True
            else:
                logger.warning(f"Пользователь с ID {row_id} не найден")
                return False
    except Exception as e:
        logger.error(f"Ошибка при удалении пользователя с ID {row_id}: {e}")
        return False