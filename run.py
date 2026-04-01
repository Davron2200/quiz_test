import subprocess
import sys
import time
import os

def main():
    print("Quiz Bot va Admin panel ishga tushirilmoqda...")
    
    # Flask admin panelni ishga tushirish
    flask_process = subprocess.Popen([sys.executable, "main_flask.py"])
    
    # Bot bazaga va serverga to'liq ulanishi uchun biroz kutamiz
    time.sleep(2)
    
    # Telegram botni ishga tushirish
    bot_process = subprocess.Popen([sys.executable, "main_bot.py"])
    
    try:
        # Ikkala jarayonni ham kutamiz
        flask_process.wait()
        bot_process.wait()
    except KeyboardInterrupt:
        print("\nJarayon to'xtatilmoqda...")
        flask_process.terminate()
        bot_process.terminate()
        flask_process.wait()
        bot_process.wait()
        print("Barcha xizmatlar to'xtatildi.")

if __name__ == "__main__":
    main()
