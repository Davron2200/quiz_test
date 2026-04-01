import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate():
    sync_url = os.getenv('SYNC_DATABASE_URL')
    if not sync_url:
        print("SYNC_DATABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(sync_url)
        cur = conn.cursor()
        
        # Add column if not exists
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR;")
        
        conn.commit()
        cur.close()
        conn.close()
        print("Successfully added last_name column to users table.")
    except Exception as e:
        print(f"Error during migration: {e}")

if __name__ == "__main__":
    migrate()
