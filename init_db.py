import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

load_dotenv()

def create_database_if_not_exists():
    sync_url = os.getenv("SYNC_DATABASE_URL")
    if not sync_url:
        print("SYNC_DATABASE_URL topilmadi .env faylda!")
        return

    # postgresql://user:password@host:port/dbname formatidan ma'lumotlarni ajratish
    # Bu faqat localhost dagi oddiy ulanish uchun basic pars qilish
    try:
        parts = sync_url.replace("postgresql://", "").split("/")
        db_name = parts[-1]
        credentials_and_host = parts[0]
        
        creds, host_port = credentials_and_host.split("@")
        user, password = creds.split(":")
        host, port = host_port.split(":")
        
        # Standart `postgres` bazasiga ulanish
        conn = psycopg2.connect(
            dbname='postgres', 
            user=user, 
            password=password, 
            host=host, 
            port=port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        cur = conn.cursor()
        
        # Baza bor yoki yo'qligini tekshirish
        cur.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_name}'")
        exists = cur.fetchone()
        
        if not exists:
            cur.execute(f"CREATE DATABASE {db_name}")
            print(f"Database '{db_name}' muvaffaqiyatli yaratildi.")
        else:
            print(f"Database '{db_name}' allaqachon mavjud.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Baza yaratishda ulanishda xato: {e}")

if __name__ == "__main__":
    create_database_if_not_exists()
