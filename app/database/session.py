# database/session.py
from pathlib import Path
from peewee import SqliteDatabase

# База в каталоге database/
DB_NAME = "Next'25.db"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / DB_NAME

db = SqliteDatabase(str(DB_PATH))

