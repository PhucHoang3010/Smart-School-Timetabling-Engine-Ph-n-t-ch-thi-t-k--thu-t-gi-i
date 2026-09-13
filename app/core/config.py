import os
from dotenv import load_dotenv

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development").lower()
DEFAULT_POSTGRES_URL = "postgresql://postgres:postgres@localhost:5432/timetabling_db"
if APP_ENV in {"dev", "development", "test"} and "DATABASE_URL" not in os.environ:
    DATABASE_URL = "sqlite:///./timetabling.db"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_POSTGRES_URL)

DAYS = list(range(2, 8))
SLOTS = list(range(1, 11))
MAX_CONSECUTIVE_SLOTS = 3
