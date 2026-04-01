import asyncio
import sys
import logging

# Windows muhitida psycopg Driver bilan ishlashi uchun zarur:
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select
from core.config import settings
from core.database import AsyncSessionLocal
from db.models import User, SystemSetting
from bot.handlers import router

logger = logging.getLogger(__name__)


async def send_startup_notification(bot: Bot):
    """Bot ishga tushganda barcha foydalanuvchilarga xabar yuborish."""

    startup_message = (
        "🚀 <b>Bot ishga tushdi!</b>\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "📚 <b>MOHILANING TURKCHA Quiz Test</b> boti\n"
        "ishga tayyor va sizni kutmoqda!\n"
        "\n"
        "✅ Siz hozir quyidagilardan foydalanishingiz mumkin:\n"
        "\n"
        "   🔹 <b>Test ishlash</b> — bilimingizni sinang\n"
        "   🔹 <b>Natijalarni ko'rish</b> — o'z yutuqlaringizni kuzating\n"
        "   🔹 <b>Reytingni tekshirish</b> — boshqalar bilan solishtiring\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "👇 Boshlash uchun /start buyrug'ini yuboring!"
    )

    async with AsyncSessionLocal() as session:
        # Check setting first
        sys_res = await session.execute(select(SystemSetting))
        setting = sys_res.scalars().first()
        if setting and not setting.send_bot_startup_message:
            print("📨 Startup xabar o'chirilgan. Hech kimga yuborilmadi.")
            return

        result = await session.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.all()]

    sent_count = 0
    failed_count = 0

    for telegram_id in user_ids:
        try:
            await bot.send_message(chat_id=telegram_id, text=startup_message)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning(f"Xabar yuborilmadi (ID: {telegram_id}): {e}")

    print(f"📨 Startup xabar: {sent_count} ta foydalanuvchiga yuborildi, {failed_count} ta xatolik.")


async def main():
    # Logging sozlamalari
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )
    
    bot = Bot(
        token=settings.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    dp.include_router(router)

    print("Telegram Bot ishga tushmoqda...")

    # Bot ishga tushganda xabarni fonda yuboramiz (Pollingni to'sib qo'ymaslik uchun)
    asyncio.create_task(send_startup_notification(bot))

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
