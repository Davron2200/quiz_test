import os
from dotenv import load_dotenv

# Env faylni yuklash
load_dotenv()

class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")
    SYNC_DATABASE_URL = os.getenv("SYNC_DATABASE_URL")
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

settings = Settings()
