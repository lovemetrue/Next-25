# database/models.py
from datetime import datetime
from enum import IntEnum
from peewee import (
    Model, AutoField, IntegerField, CharField, BooleanField,
    DateTimeField, ForeignKeyField, TextField
)
from .session import db  # общий экземпляр базы

# ---------- Базовая модель ----------
class BaseModel(Model):
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    class Meta:
        database = db



### Модель для хранения кол-ва ролей
class Setting(BaseModel):
    key = CharField(unique=True)
    value = CharField(null=True)

# ---------- Перечисления ----------
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
            OrderStatus.LOADING: "на загрузке",
            OrderStatus.ENROUTE: "в пути",
            OrderStatus.DELIVERED: "доставлено",
            OrderStatus.CANCELLED: "отменена",
            OrderStatus.ENROUTE_TO_LOADING: "в пути на загрузку",

        }[self]


# ---------- Пользователи ----------
class User(BaseModel):
    id = AutoField()
    tg_id = IntegerField(unique=True, index=True)
    tg_chat_id = IntegerField(null=True)
    username = CharField(null=True)
    first_name = CharField(null=True)
    last_name = CharField(null=True)

    role = IntegerField(default=int(UserRole.DRIVER))  # UserRole
    phone = CharField(null=True, index=True)
    employee_id = CharField(null=True, index=True)

    is_active = BooleanField(default=True)

    class Meta:
        table_name = "users"



class Order(BaseModel):
    """
    Заявка на перевозку
    """
    id = AutoField()
    dispatcher = ForeignKeyField(User, backref="orders", on_delete="CASCADE")  # кто создал
    driver = ForeignKeyField(User, backref="driver_orders", null=True, on_delete="SET NULL")  # назначенный водитель

    prefix = IntegerField(default=int(OrderPrefix.WITH_VAT))  # OrderPrefix
    from_addr = CharField() #
    to_addr = CharField() #
    datetime = DateTimeField(default=datetime.now)  # ⚡️ Автоматически ставим дату создания
    cargo_type = CharField(null=True)
    weight_volume = CharField(null=True)
    comment = TextField(null=True)

    status = IntegerField(default=int(OrderStatus.NEW))  # OrderStatus
    cancel_reason = TextField(null=True)

    file_path = CharField(null=True)  # накладные, фото и т.д.

    class Meta:
        table_name = "orders"
        database = db

# ---------- История статусов ----------
class OrderStatusHistory(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="status_history", on_delete="CASCADE")
    by_user = ForeignKeyField(User, backref="status_changes", on_delete="SET NULL", null=True)
    status = IntegerField()  # OrderStatus
    note = TextField(null=True)

    class Meta:
        table_name = "order_status_history"


# ---------- Сообщения в заявке ----------
class OrderMessage(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="messages", on_delete="CASCADE")
    sender = ForeignKeyField(User, backref="sent_messages", on_delete="SET NULL", null=True)
    message = TextField(null=False)
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "order_messages"

# ---------- Вложения ----------
class Attachment(BaseModel):
    id = AutoField()
    order = ForeignKeyField(Order, backref="attachments", on_delete="CASCADE")
    uploaded_by = ForeignKeyField(User, backref="uploaded_files", on_delete="SET NULL", null=True)

    file_id = CharField()                 # Telegram file_id
    file_type = CharField()               # "photo" | "document"
    caption = TextField(null=True)

    class Meta:
        table_name = "attachments"

#
# # ---------- Чат по заявке ----------
# class ChatMessage(BaseModel):
#     id = AutoField()
#     order = ForeignKeyField(Order, backref="chat_messages", on_delete="CASCADE")
#     sender = ForeignKeyField(User, backref="chat_messages", on_delete="SET NULL", null=True)
#     text = TextField(null=True)
#     file_id = CharField(null=True)
#     msg_type = CharField(default="text")  # "text" | "photo" | "document" ...
#
#     class Meta:
#         table_name = "chat_messages"
#

# ---------- Инициализация ----------
def create_all_tables():
    with db:
        db.create_tables([User, Order, OrderStatusHistory, Attachment, OrderMessage])

# def create_driver_row(tg_id,
#                      tg_chat_id,
#                      username,
#                      first_name,
#                      last_namee,
#                      role,
#                      phone,
#                      employee_id,
#                      is_active):
#
#     with db.atomic():
#         User.create(tg_id = 123231123,
#                     tg_chat_id= 231231321,
#                     username="Driver",
#                     first_name= "Driver_one",
#                     last_name= "Driver_lastname",
#                     role=
#                     )