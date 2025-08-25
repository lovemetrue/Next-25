import os
from pathlib import Path
from peewee import SqliteDatabase

# имя файла по умолчанию
DB_NAME = "Next25.db"

# 1. Читаем путь из переменной окружения (если есть)
db_path = os.getenv("DB_PATH")

# 2. Если переменной нет → кладём рядом с кодом, как раньше
if not db_path:
    base_dir = Path(__file__).resolve().parent
    db_path = base_dir / DB_NAME
else:
    db_path = Path(db_path)

# 3. Создаём подключение
db = SqliteDatabase(str(db_path))



# # database/session.py
# from pathlib import Path
# from peewee import SqliteDatabase
#
# # База в каталоге database/
# DB_NAME = "Next25.db"
# BASE_DIR = Path(__file__).resolve().parent
# DB_PATH = BASE_DIR / DB_NAME
#
# db = SqliteDatabase(str(DB_PATH))
#
