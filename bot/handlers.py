import asyncio
import random
import logging
from typing import Dict
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PollAnswer, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from bot.keyboards import get_main_menu, get_units_keyboard, get_sections_keyboard, get_reply_main_menu, get_results_level_keyboard, get_results_units_keyboard
from bot.states import QuizState, RegistrationState, AdminState, MentorState
from core.database import AsyncSessionLocal
from core.utils import CertificateGenerator
from db.models import User, Unit, Section, Question, AnswerOption, TestResult, Group, Attendance, Resource
from sqlalchemy import select, desc, func, and_
from sqlalchemy.orm import selectinload
from datetime import timezone, timedelta

TASHKENT_TZ = timezone(timedelta(hours=5))

def to_tashkent(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TASHKENT_TZ)

router = Router()
logger = logging.getLogger(__name__)

async def safe_call(coro):
    """Background tasks uchun xatoliklarni ushlab qoluvchi yordamchi."""
    try:
        await coro
    except Exception as e:
        logger.debug(f"Background API call error (expected): {e}")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user:
            await message.answer("Xush kelibsiz! Botdan foydalanish uchun ro'yxatdan o'ting.\n\nIsmingizni kiriting:")
            await state.set_state(RegistrationState.waiting_for_first_name)
            return

        # Agar ism/familiya bo'lmasa (avvalgi eski userlar bo'lsa) ro'yxatdan o'tkazish
        if not user.first_name or not user.last_name:
            await message.answer("Botdan to'liq foydalanish uchun ma'lumotlaringizni yangilang.\n\nIsmingizni kiriting:")
            await state.set_state(RegistrationState.waiting_for_first_name)
            return

    await message.answer(
        f"Assalomu alaykum, {user.first_name}!\n\n"
        "MOHILANING TURKCHA Quiz Test botiga xush kelibsiz. Quyidagilardan birini tanlang:",
        reply_markup=get_reply_main_menu(user)
    )

@router.message(RegistrationState.waiting_for_first_name)
async def process_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await message.answer("Familiyangizni kiriting:")
    await state.set_state(RegistrationState.waiting_for_last_name)

@router.message(RegistrationState.waiting_for_last_name)
async def process_last_name(message: Message, state: FSMContext):
    data = await state.get_data()
    first_name = data.get("first_name")
    last_name = message.text
    
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
        else:
            user.first_name = first_name
            user.last_name = last_name
            
        await session.commit()
    
    await state.clear()
    await message.answer(
        f"Assalomu alaykum, {first_name}!\n\n"
        "MOHILANING TURKCHA Quiz Test botiga xush kelibsiz. Quyidagilardan birini tanlang:",
        reply_markup=get_reply_main_menu(user)
    )

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
    await callback.message.answer("Quyidagilardan birini tanlang:", reply_markup=get_reply_main_menu(user))
    await callback.answer()

async def _get_rating_text():
    async with AsyncSessionLocal() as session:
        stmt = select(User).options(selectinload(User.results))
        users_result = await session.execute(stmt)
        users = users_result.scalars().all()
        
        user_scores = {}
        for u in users:
            if not u.results:
                continue
                
            total_q = sum(r.total_questions for r in u.results)
            correct = sum(r.correct_answers for r in u.results)
            avg_score = (correct / total_q * 100) if total_q > 0 else 0
            
            # Weighted score: To'g'ri javoblar * (Foiz / 100)
            weighted_score = round(correct * (avg_score / 100), 1)
            
            if weighted_score > 0:
                full_name = f"{u.first_name or ''} {u.last_name or ''}".strip()
                if not full_name:
                    full_name = u.username or str(u.telegram_id)
                user_scores[full_name] = weighted_score
            
        sorted_users = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        
    text = "🏆 <b>Top-10 Foydalanuvchilar Reytingi:</b>\n\n"
    if not sorted_users:
        text += "Hali hech kim test ishlamagan!"
    else:
        for idx, (name, score) in enumerate(sorted_users, 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            text += f"{medal} {name} - <b>{score}</b> reyting balli\n"
    return text

@router.message(F.text == "🏆 Reyting")
async def show_rating_msg(message: Message):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
    text = await _get_rating_text()
    await message.answer(text, reply_markup=get_reply_main_menu(user))

@router.message(F.text == "🇺🇿 Tilni o'zgartirish")
async def change_lang_msg(message: Message):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
    await message.answer("Hozirda faqat O'zbek tili mavjud.\nTez orada boshqa tillar ham qo'shiladi!", reply_markup=get_reply_main_menu(user))

@router.message(F.text.in_(["𝗔𝟭", "𝗔𝟮", "𝗕𝟭", "𝗕𝟮"]))
async def show_level_units_msg(message: Message):
    # Map bold text to normal level strings
    level_map = {
        "𝗔𝟭": "A1",
        "𝗔𝟮": "A2",
        "𝗕𝟭": "B1",
        "𝗕𝟮": "B2"
    }
    level = level_map.get(message.text, message.text)
    
    async with AsyncSessionLocal() as session:
        units = (await session.execute(
            select(Unit).where(Unit.level == level).order_by(Unit.number)
        )).scalars().all()
    
    if not units:
        await message.answer(f"{level} darajasida hali mavzular yo'q.")
        return
        
    await message.answer(
        f"<b>{level}</b> darajasidagi mavzularni tanlang:", 
        reply_markup=get_units_keyboard(units)
    )

@router.callback_query(F.data.startswith("level_"))
async def show_level_units(callback: CallbackQuery):
    level = callback.data.split("_")[1]
    async with AsyncSessionLocal() as session:
        units = (await session.execute(
            select(Unit).where(Unit.level == level).order_by(Unit.number)
        )).scalars().all()
    
    if not units:
        await callback.answer(f"{level} darajasida hali mavzular yo'q.", show_alert=True)
        return
        
    await callback.message.edit_text(
        f"<b>{level}</b> darajasidagi mavzularni tanlang:", 
        reply_markup=get_units_keyboard(units)
    )

@router.message(F.text == "📊 Natijalar")
async def show_my_results_msg(message: Message):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
    await message.answer("Qaysi darajadagi natijalaringizni ko'rmoqchisiz?", reply_markup=get_results_level_keyboard())
    # Asosiy menyuni yangilash (agar admin qilingan bo'lsa)
    await message.answer("Menyu:", reply_markup=get_reply_main_menu(user))

@router.message(F.text == "👤 Profil")
async def show_profile(message: Message):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id).options(selectinload(User.group))
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user:
            await message.answer("Siz ro'yxatdan o'tmagansiz. /start buyrug'ini bosing.")
            return
            
        group_name = user.group.name if user.group else "Guruhsiz"
        coins = user.coins or 0
        
        # Jami ishlangan testlar va o'rtacha ballni hisoblash
        stmt_res = select(
            func.count(TestResult.id),
            func.avg(TestResult.score)
        ).where(TestResult.user_id == user.id)
        res_data = (await session.execute(stmt_res)).first()
        total_tests = res_data[0] or 0
        avg_score = round(res_data[1], 1) if res_data[1] else 0
        
        profile_text = (
            f"👤 <b>Mening Profilim</b>\n\n"
            f"🏷 Ism: <b>{user.first_name} {user.last_name or ''}</b>\n"
            f"👥 Guruh: <b>{group_name}</b>\n"
            f"💰 Tangalar: <b>{coins}</b>\n\n"
            f"📊 Statistika:\n"
            f"📝 Ishlangan testlar: <b>{total_tests} ta</b>\n"
            f"📈 O'rtacha natija: <b>{avg_score}%</b>"
        )
        
        await message.answer(profile_text, parse_mode="HTML", reply_markup=get_reply_main_menu(user))

@router.callback_query(F.data == "show_my_results")
async def show_my_results(callback: CallbackQuery):
    await callback.message.edit_text("Qaysi darajadagi natijalaringizni ko'rmoqchisiz?", reply_markup=get_results_level_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("res_level_"))
async def res_show_units(callback: CallbackQuery):
    level = callback.data.split("_")[2]
    async with AsyncSessionLocal() as session:
        # User id sini topamiz
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        if not user:
            await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
            return

        # Ushbu user va daraja bo'yicha kamida bitta natijasi bor unitlarni topamiz
        stmt = select(Unit).join(TestResult).where(
            TestResult.user_id == user.id,
            Unit.level == level
        ).distinct().order_by(Unit.number)
        
        units = (await session.execute(stmt)).scalars().all()

    if not units:
        await callback.answer(f"Sizda {level} darajasida hali natijalar yo'q.", show_alert=True)
        return

    await callback.message.edit_text(
        f"<b>{level}</b> darajasidagi mavzuni tanlang:",
        reply_markup=get_results_units_keyboard(units)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("res_unit_"))
async def res_show_details(callback: CallbackQuery):
    unit_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        
        unit = await session.get(Unit, unit_id)
        
        stmt = select(TestResult).where(
            TestResult.user_id == user.id,
            TestResult.unit_id == unit_id
        ).options(selectinload(TestResult.section)).order_by(desc(TestResult.created_at))
        
        results = (await session.execute(stmt)).scalars().all()

    if not results:
        await callback.answer("Ushbu mavzu bo'yicha natijalar topilmadi.", show_alert=True)
        return

    text = f"📊 <b>{unit.number}-dars: {unit.title}</b>\n"
    text += f"Daraja: <b>{unit.level}</b>\n"
    text += "──────────────────\n\n"
    
    for r in results:
        date_str = to_tashkent(r.created_at).strftime("%d.%m.%Y %H:%M")
        section_name = f" [{r.section.title}]" if r.section else ""
        text += f"📅 <code>{date_str}</code>{section_name}\n"
        text += f"✅ {r.correct_answers} | ❌ {r.wrong_answers} | 🎯 <b>{r.score}%</b>\n"
        text += "──────────────────\n"

    # Orqaga qaytish tugmasi
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="⬅️ Mavzularga qaytish", callback_data=f"res_level_{unit.level}")
    
    await callback.message.edit_text(text, reply_markup=back_kb.as_markup())
    await callback.answer()

@router.callback_query(F.data == "show_rating")
async def show_rating(callback: CallbackQuery):
    text = await _get_rating_text()
    await callback.message.answer(text)
    await callback.answer()
            
active_timers: Dict[int, asyncio.Task] = {}

class DummyChat:
    def __init__(self, chat_id: int):
        self.id = chat_id

class DummyMessage:
    def __init__(self, chat_id: int):
        self.chat = DummyChat(chat_id)

async def send_question(message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    q_index = data['current_index']
    questions = data['questions']
    
    if q_index >= len(questions):
        # Test tugadi
        correct = data['correct_answers']
        wrong = data['wrong_answers']
        unit_id = data['unit_id']
        section_id = data.get('section_id')
        
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == message.chat.id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            earned_coins = 0
            if user:
                # Natijani saqlash
                score = (correct / len(questions)) * 100 if len(questions) > 0 else 0
                res = TestResult(
                    user_id=user.id,
                    unit_id=unit_id,
                    section_id=section_id,
                    total_questions=len(questions),
                    correct_answers=correct,
                    wrong_answers=wrong,
                    score=round(score, 2)
                )
                session.add(res)
                
                # Tangalar berish
                if score == 100:
                    earned_coins = 10
                elif score >= 80:
                    earned_coins = 5
                elif score >= 60:
                    earned_coins = 2
                
                if earned_coins > 0:
                    user.coins = (user.coins or 0) + earned_coins
                
                await session.commit()
                await session.refresh(user)
                
                # Sertifikat tekshiruvi (Barcha bo'limlar tugatilganmi?)
                all_sections_stmt = select(Section).where(Section.unit_id == unit_id)
                all_sections = (await session.execute(all_sections_stmt)).scalars().all()
                all_section_ids = [s.id for s in all_sections]
                
                # Foydalanuvchi ishlagan bo'limlar (Kamida 60% ball bilan)
                user_res_stmt = select(TestResult.section_id).where(
                    and_(
                        TestResult.user_id == user.id, 
                        TestResult.unit_id == unit_id,
                        TestResult.score >= 60
                    )
                )
                completed_section_ids = (await session.execute(user_res_stmt)).scalars().all()
                
                is_unit_completed = all(sid in completed_section_ids for sid in all_section_ids)
                
                if is_unit_completed:
                    unit_obj = await session.get(Unit, unit_id)
                    try:
                        cert_gen = CertificateGenerator()
                        full_name = f"{user.first_name} {user.last_name or ''}".strip()
                        # Blocking IO ni thread ga o'tkazamiz, bot to'xtab qolmasligi uchun
                        cert_path = await asyncio.to_thread(cert_gen.generate, full_name, unit_obj.title)
                        
                        await bot.send_document(
                            message.chat.id,
                            FSInputFile(cert_path),
                            caption=f"🎉 Tabriklaymiz! Siz <b>{unit_obj.number}-dars ({unit_obj.title})</b> bo'yicha barcha testlarni muvaffaqiyatli yakunladingiz va maxsus sertifikatga sazovor bo'ldingiz!",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Sertifikat generatsiyasida xato: {e}")
                
        await state.clear()
        
        coin_msg = f"\n💰 <b>+{earned_coins} tanga!</b> (Jami: {user.coins or 0})" if earned_coins > 0 else ""
        
        await bot.send_message(
            message.chat.id,
            f"✅ <b>Test Yakunlandi!</b>\n\n"
            f"Umumiy savollar: {len(questions)}\n"
            f"🟢 To'g'ri javoblar: {correct}\n"
            f"🔴 Xato javoblar: {wrong}"
            f"{coin_msg}",
            reply_markup=get_reply_main_menu(user),
            parse_mode="HTML"
        )
        return

    # Keyingi savolni yuborish (Telegram Quiz Poll formatida)
    q = questions[q_index]
    total = len(questions)
    poll_question = f"[{q_index + 1}/{total}] {q_index + 1}. {q['text']}"
    
    # Savol matni 300 belgidan oshmasligi kerak (Telegram cheklovi)
    if len(poll_question) > 300:
        poll_question = poll_question[:297] + "..."
    
    # Javob variantlari va to'g'ri javob indeksini aniqlash
    options = q.get('options', [])
    if not options:
        # Fallback agar state da ma'lumot yo'q bo'lsa (eski state lar bilan ishlash uchun)
        async with AsyncSessionLocal() as session:
            opts_stmt = select(AnswerOption).where(AnswerOption.question_id == q['id'])
            options_db = list((await session.execute(opts_stmt)).scalars().all())
            options = [{"text": o.text, "is_correct": o.is_correct} for o in options_db]
    
    # Aralashtirish
    shuffled_options = list(options)
    random.shuffle(shuffled_options)
    
    option_texts = []
    correct_option_index = 0
    for i, opt in enumerate(shuffled_options):
        # opt endi lug'at (dict)
        text = opt['text'] if isinstance(opt, dict) else opt.text
        # Telegram cheklovi: option matni 100 belgidan oshmasligi kerak
        if len(text) > 100:
            text = text[:97] + "..."
        
        is_corr = opt['is_correct'] if isinstance(opt, dict) else opt.is_correct
        
        option_texts.append(text)
        if is_corr:
            correct_option_index = i
    
    # Oldingi poll dagi "Stop" tugmasini olib tashlash (Faqat bitta tugma qolishi uchun)
    data = await state.get_data()
    old_poll_msg_id = data.get("current_poll_msg_id")
    
    chat_id = message.chat.id if hasattr(message.chat, 'id') else message.chat
    if old_poll_msg_id:
        # Keywords ishlatish shart! Fondagi xatolar botga xalaqit bermasligi uchun safe_call.
        asyncio.create_task(safe_call(bot.edit_message_reply_markup(chat_id=chat_id, message_id=old_poll_msg_id, reply_markup=None)))
    
    # Vaqt chegarasini Telegram quiz poll uchun moslashtirish (5-600 soniya)
    open_period = max(5, min(q['time_limit'], 600))
    
    # Quiz poll yuborish
    stop_btn = InlineKeyboardBuilder()
    stop_btn.button(text="🛑 Testni to'xtatish", callback_data="stop_quiz")

    try:
        sent_poll = await bot.send_poll(
            chat_id=message.chat.id,
            question=poll_question,
            options=option_texts,
            type="quiz",
            correct_option_id=correct_option_index,
            is_anonymous=False,
            open_period=open_period,
            reply_markup=stop_btn.as_markup()
        )
        
        # Poll ID va to'g'ri javob indeksini state ga saqlash
        await state.update_data(
            current_poll_id=sent_poll.poll.id,
            current_poll_msg_id=sent_poll.message_id,
            correct_option_index=correct_option_index
        )
        
        # Taymerni ishga tushirish
        user_id = message.chat.id
        if user_id in active_timers:
            active_timers[user_id].cancel()
            
        active_timers[user_id] = asyncio.create_task(
            question_timer(user_id, bot, state, open_period)
        )
    except Exception as e:
        logger.error(f"Poll yuborishda xato: {e}")
        await bot.send_message(message.chat.id, "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        await state.clear()

async def question_timer(user_id: int, bot: Bot, state: FSMContext, wait_time: int):
    try:
        await asyncio.sleep(wait_time + 1)  # Poll yopilgandan 1 soniya keyin
        # Vaqt tugadi — foydalanuvchi javob bermagan bo'lsa
        current_state = await state.get_state()
        if current_state == QuizState.testing.state:
            data = await state.get_data()
            if data.get('current_poll_id'):
                # Oldingi savoldan "Stop" tugmasini olib tashlash
                if data.get('current_poll_msg_id'):
                    try:
                        await bot.edit_message_reply_markup(user_id, data['current_poll_msg_id'], reply_markup=None)
                    except:
                        pass

                await state.update_data(
                    wrong_answers=data['wrong_answers'] + 1,
                    current_index=data['current_index'] + 1,
                    current_poll_id=None
                )
                await bot.send_message(user_id, "⏳ Vaqt tugadi! Javob qabul qilinmadi.")
                await send_question(DummyMessage(user_id), state, bot)
    except asyncio.CancelledError:
        pass
    finally:
        # Timer tugadi yoki bekor qilindi, dict dan o'chiramiz
        if user_id in active_timers:
            active_timers.pop(user_id, None)
@router.callback_query(F.data == "stop_quiz")
async def stop_quiz_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # Stop tugmasini darhol olib tashlash
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass

    # Taymerni to'xtatish
    user_id = callback.from_user.id
    if user_id in active_timers:
        active_timers[user_id].cancel()
        active_timers.pop(user_id, None)
    
    data = await state.get_data()
    if not data or 'questions' not in data:
        await callback.answer("Hozirda test ishlamayapsiz.")
        return
        
    # Pollni yopishga harakat qilish
    if data.get('current_poll_msg_id'):
        try:
            await bot.stop_poll(callback.message.chat.id, data['current_poll_msg_id'])
        except:
            pass

    await callback.message.answer("🛑 Test to'xtatildi.")
    
    # Testni yakunlash
    await state.update_data(current_index=999999)
    await send_question(DummyMessage(user_id), state, bot)
    await callback.answer()

@router.callback_query(F.data.startswith("unit_"))
async def show_sections(callback: CallbackQuery, state: FSMContext):
    unit_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        unit = await session.get(Unit, unit_id)
        if not unit or not unit.is_active:
            await callback.answer("Bu dars hozircha yopiq!", show_alert=True)
            return

        # Darslar ketma-ketligini tekshirish
        if unit.number > 1:
            user_stmt = select(User).where(User.telegram_id == callback.from_user.id)
            user = (await session.execute(user_stmt)).scalar_one_or_none()
            prev_unit_stmt = select(Unit).where(Unit.number == unit.number - 1)
            prev_unit = (await session.execute(prev_unit_stmt)).scalar_one_or_none()
            if prev_unit:
                res_stmt = select(TestResult).where(TestResult.user_id == user.id, TestResult.unit_id == prev_unit.id)
                res = (await session.execute(res_stmt)).scalars().first()
                if not res:
                    await callback.answer(f"Ushbu darsga o'tish uchun avval {prev_unit.number}-darsni tugatishingiz kerak!", show_alert=True)
                    return

        sections_stmt = select(Section).where(Section.unit_id == unit_id).order_by(Section.number)
        sections = (await session.execute(sections_stmt)).scalars().all()
        
    if not sections:
        await callback.answer("Bu darsda hali bo'limlar yo'q.", show_alert=True)
        return

    await callback.message.edit_text(f"<b>{unit.number}-dars: {unit.title}</b>\nBo'limni tanlang:", reply_markup=get_sections_keyboard(sections, unit_id))

@router.callback_query(F.data.startswith("section_"))
async def start_section_quiz(callback: CallbackQuery, state: FSMContext, bot: Bot):
    section_id = int(callback.data.split("_")[1])
    user_tg_id = callback.from_user.id
    
    async with AsyncSessionLocal() as session:
        section = await session.get(Section, section_id)
        if not section: return
        
        unit = await session.get(Unit, section.unit_id)
        
        # Savollarni olish (Variantlari bilan birga)
        q_stmt = select(Question).where(Question.section_id == section_id).options(selectinload(Question.options))
        questions_db = (await session.execute(q_stmt)).scalars().all()
        
    if not questions_db:
        await callback.answer("Bu bo'limda hozircha savollar yo'q.", show_alert=True)
        return
        
    # State ga yozish
    questions = []
    for q in questions_db:
        questions.append({
            "id": q.id, 
            "text": q.text, 
            "time_limit": q.time_limit,
            "options": [{"text": o.text, "is_correct": o.is_correct} for o in q.options]
        })
    random.shuffle(questions) # Savollarni aralashtirish
    await state.set_state(QuizState.testing)
    await state.update_data(
        unit_id=unit.id,
        section_id=section_id,
        questions=questions,
        current_index=0,
        correct_answers=0,
        wrong_answers=0
    )
    
    await callback.message.delete()
    
    await bot.send_message(
        user_tg_id,
        f"📚 <b>{unit.number}-dars: {unit.title}</b>\n"
        f"🔹 <b>Bo'lim: {section.title}</b>\n\n"
        f"Ushbu bo'limda jami <b>{len(questions)} ta</b> savol bor.\n"
        f"Omad! 👇"
    )
    await send_question(DummyMessage(user_tg_id), state, bot)

@router.poll_answer()
async def process_poll_answer(poll_answer: PollAnswer, state: FSMContext, bot: Bot):
    try:
        user_id = poll_answer.user.id
        
        # Taymerni to'xtatish
        if user_id in active_timers:
            active_timers[user_id].cancel()
            active_timers.pop(user_id, None)
        
        logger.info(f"Poll answer received from {user_id} for poll {poll_answer.poll_id}")
        
        current_state = await state.get_state()
        if current_state != QuizState.testing.state:
            logger.warning(f"User {user_id} in wrong state: {current_state}")
            return
        
        data = await state.get_data()
        
        # Bu poll bizning joriy pollimizmi tekshirish
        stored_poll_id = data.get('current_poll_id')
        
        if stored_poll_id is None or stored_poll_id != poll_answer.poll_id:
            # Race condition ehtimoli: savol endi yuborildi, hali ID saqlanmadi (yoki eski poll)
            # 0.3 soniya kutib qayta tekshiramiz
            await asyncio.sleep(0.3)
            data = await state.get_data()
            stored_poll_id = data.get('current_poll_id')
            
        if stored_poll_id != poll_answer.poll_id:
            logger.warning(f"Poll ID mismatch for user {user_id}: received {poll_answer.poll_id}, stored {stored_poll_id}")
            return

        logger.info(f"Processing answer for user {user_id}, question {data.get('current_index')}")
        
        # Oldingi savoldan "Stop" tugmasini darhol olib tashlash (fonda)
        if data.get('current_poll_msg_id'):
            asyncio.create_task(safe_call(bot.edit_message_reply_markup(chat_id=user_id, message_id=data['current_poll_msg_id'], reply_markup=None)))
        
        q_index = data['current_index']
        
        # Tanlangan javob indeksini to'g'ri javob bilan solishtirish
        selected_index = poll_answer.option_ids[0] if poll_answer.option_ids else -1
        correct_option_index = data.get('correct_option_index', 0)
        is_correct = (selected_index == correct_option_index)
        
        if is_correct:
            await state.update_data(
                correct_answers=data['correct_answers'] + 1,
                current_index=q_index + 1
            )
        else:
            await state.update_data(
                wrong_answers=data['wrong_answers'] + 1,
                current_index=q_index + 1
            )
        
        # Kichik pauza — foydalanuvchi natijani ko'rsin (0.5s yetarli)
        await asyncio.sleep(0.5)
        await send_question(DummyMessage(user_id), state, bot)
    except Exception as e:
        logger.error(f"process_poll_answer da xato: {e}")

@router.message(F.text == "🎛 Admin panel")
async def admin_panel(message: Message):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user or user.role != 'admin':
            return

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="admin_stats")
    builder.button(text="📢 Xabar yuborish", callback_data="admin_broadcast")
    builder.button(text="🔙 Chiqish", callback_data="back_to_main")
    builder.adjust(1)
    
    await message.answer("Boshqaruv paneli:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == callback.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user or user.role != 'admin':
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

        total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        total_results = (await session.execute(select(func.count(TestResult.id)))).scalar() or 0
        
        # Bugungi testlar
        from datetime import datetime
        today_start = datetime.now(TASHKENT_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        
        stmt_today = select(func.count(TestResult.id)).where(TestResult.created_at >= today_start)
        today_results = (await session.execute(stmt_today)).scalar() or 0

        text = (
            "📊 <b>Bot Statistikasi</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{total_users} ta</b>\n"
            f"📝 Jami bajarilgan testlar: <b>{total_results} ta</b>\n"
            f"📅 Bugun bajarilgan: <b>{today_results} ta</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data="admin_panel_back")
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "admin_panel_back")
async def admin_panel_back(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="admin_stats")
    builder.button(text="📢 Xabar yuborish", callback_data="admin_broadcast")
    builder.button(text="🔙 Chiqish", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text("Boshqaruv paneli:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast_message)
    await callback.message.answer("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing (Matn, rasm yoki video):\n\nBekor qilish uchun /cancel deb yozing.")
    await callback.answer()

@router.message(AdminState.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == message.from_user.id)
            user = (await session.execute(stmt)).scalar_one_or_none()
        await message.answer("Quyidagilardan birini tanlang:", reply_markup=get_reply_main_menu(user))
        return

    await state.clear()
    sent_msg = await message.answer("Xabar yuborish boshlandi...")
    
    async with AsyncSessionLocal() as session:
        stmt = select(User.telegram_id)
        users = (await session.execute(stmt)).scalars().all()
    
    count = 0
    for user_id in users:
        try:
            await message.copy_to(user_id)
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
            
    await sent_msg.edit_text(f"✅ Xabar jami {count} ta foydalanuvchiga yuborildi.")
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
    await message.answer("Quyidagilardan birini tanlang:", reply_markup=get_reply_main_menu(user))

@router.message(F.text == "👨‍🏫 O'qituvchi paneli")
async def mentor_panel(message: Message):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == message.from_user.id).options(selectinload(User.mentored_groups))
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user or (user.role != 'teacher' and user.role != 'admin'):
            return

        groups = user.mentored_groups
        if not groups:
            await message.answer("Sizga hali hech qaysi guruh biriktirilmagan.")
            return

        builder = InlineKeyboardBuilder()
        for group in groups:
            builder.button(text=f"👥 {group.name}", callback_data=f"mentor_group_{group.id}")
        builder.button(text="🔙 Chiqish", callback_data="back_to_main")
        builder.adjust(1)
        
        await message.answer("👨‍🏫 <b>O'qituvchi boshqaruv paneli</b>\n\nGuruhni tanlang:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mentor_group_"))
async def mentor_group_details(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        group = await session.get(Group, group_id, options=[selectinload(Group.users)])
        if not group:
            await callback.answer("Guruh topilmadi.")
            return
            
        users = group.users
        total_coins = sum(u.coins or 0 for u in users)
        
        text = (
            f"👥 <b>Guruh: {group.name}</b>\n"
            f"👨‍🎓 O'quvchilar soni: <b>{len(users)} ta</b>\n"
            f"💰 Jami to'plangan tangalar: <b>{total_coins} ta</b>\n\n"
            f"Tanlang:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Davomat qilish", callback_data=f"start_att_{group_id}")
        builder.button(text="📢 Guruhga xabar", callback_data=f"mentor_broadcast_{group_id}")
        builder.button(text="📊 O'quvchilar ro'yxati", callback_data=f"mentor_list_{group_id}")
        builder.button(text="📚 Resurslar", callback_data=f"mentor_res_{group_id}")
        builder.button(text="⏳ Kim ishlamadi?", callback_data=f"mentor_lazy_{group_id}")
        builder.button(text="🔙 Orqaga", callback_data="mentor_panel_home")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mentor_list_"))
async def mentor_student_list(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        group = await session.get(Group, group_id, options=[selectinload(Group.users)])
        users = group.users
        
        text = f"👥 <b>{group.name}</b> o'quvchilari:\n\n"
        builder = InlineKeyboardBuilder()
        for u in sorted(users, key=lambda x: x.coins or 0, reverse=True)[:30]:
            builder.button(text=f"{u.first_name} - {u.coins} 💰", callback_data=f"mentor_stud_det_{u.id}_{group_id}")
        builder.button(text="🔙 Orqaga", callback_data=f"mentor_group_{group_id}")
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("start_att_"))
async def start_attendance(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        group = await session.get(Group, group_id, options=[selectinload(Group.users)])
        if not group or not group.users:
            await callback.answer("Guruhda o'quvchilar yo'q.")
            return
            
        student_ids = [u.id for u in group.users]
        await state.update_data(att_students=student_ids, att_group_id=group_id, att_index=0)
        
        await send_next_attendance_step(callback.message, state)

async def send_next_attendance_step(message: Message, state: FSMContext):
    data = await state.get_data()
    students = data.get('att_students', [])
    index = data.get('att_index', 0)
    group_id = data.get('att_group_id')
    
    if index >= len(students):
        await message.edit_text("✅ Davomat yakunlandi!", reply_markup=None)
        async with AsyncSessionLocal() as session:
             user = (await session.execute(select(User).where(User.telegram_id == message.chat.id))).scalar_one_or_none()
        await message.answer("Boshqaruv paneli:", reply_markup=get_reply_main_menu(user))
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        student = await session.get(User, students[index])
        
    text = (
        f"📝 <b>Davomat ({index+1}/{len(students)})</b>\n\n"
        f"O'quvchi: <b>{student.first_name} {student.last_name or ''}</b>\n"
        f"ID: <code>{student.telegram_id}</code>\n\n"
        "Holatni tanlang:"
    )
    
    from bot.keyboards import get_attendance_status_keyboard
    await message.edit_text(text, reply_markup=get_attendance_status_keyboard(student.id, group_id), parse_mode="HTML")

@router.callback_query(F.data.startswith("att_"))
async def process_attendance(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    status = parts[1]
    user_id = int(parts[2])
    group_id = int(parts[3])
    
    async with AsyncSessionLocal() as session:
        from datetime import datetime
        today = datetime.now(TASHKENT_TZ).date()
        stmt = select(Attendance).where(Attendance.user_id == user_id, Attendance.date == today)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        
        if existing:
            existing.status = status
        else:
            new_att = Attendance(user_id=user_id, group_id=group_id, status=status, date=today)
            session.add(new_att)
        
        await session.commit()
    
    data = await state.get_data()
    await state.update_data(att_index=data.get('att_index', 0) + 1)
    await send_next_attendance_step(callback.message, state)

@router.callback_query(F.data == "mentor_panel_home")
async def mentor_panel_home(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == callback.from_user.id).options(selectinload(User.mentored_groups))
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user or (user.role != 'teacher' and user.role != 'admin'):
            await callback.answer("Ruxsat yo'q")
            return

        groups = user.mentored_groups
        builder = InlineKeyboardBuilder()
        for group in groups:
            builder.button(text=f"👥 {group.name}", callback_data=f"mentor_group_{group.id}")
        builder.button(text="🔙 Chiqish", callback_data="back_to_main")
        builder.adjust(1)
        
        await callback.message.edit_text("👨‍🏫 <b>O'qituvchi boshqaruv paneli</b>\n\nGuruhni tanlang:", reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "mentor_ignore")
async def mentor_ignore(callback: CallbackQuery):
    await callback.answer()

# --- Group Broadcast (Teacher) ---
@router.callback_query(F.data.startswith("mentor_broadcast_"))
async def start_mentor_broadcast(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(broadcast_group_id=group_id)
    await state.set_state(MentorState.waiting_for_group_broadcast)
    await callback.message.answer("📝 Guruh o'quvchilariga yubormoqchi bo'lgan xabaringizni yozing (Matn, rasm yoki video):\n\nBekor qilish uchun /cancel deb yozing.")
    await callback.answer()

@router.message(MentorState.waiting_for_group_broadcast)
async def process_mentor_broadcast(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return

    data = await state.get_data()
    group_id = data.get('broadcast_group_id')
    await state.clear()
    
    sent_msg = await message.answer("Xabar yuborish boshlandi...")
    
    async with AsyncSessionLocal() as session:
        stmt = select(User.telegram_id).where(User.group_id == group_id)
        users = (await session.execute(stmt)).scalars().all()
    
    count = 0
    for user_tg_id in users:
        try:
            await message.copy_to(user_tg_id)
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
            
# --- Student Analytics (Individual) ---
@router.callback_query(F.data.startswith("mentor_stud_det_"))
async def mentor_student_details(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[3])
    group_id = int(parts[4])
    
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        stmt = select(TestResult).where(TestResult.user_id == user_id).options(selectinload(TestResult.unit), selectinload(TestResult.section)).order_by(TestResult.created_at.desc())
        results = (await session.execute(stmt)).scalars().all()
        
        text = f"👤 <b>O'quvchi: {user.first_name} {user.last_name or ''}</b>\n\n"
        if not results:
            text += "Hali test ishlamagan."
        else:
            for r in results[:10]: # Oxirgi 10 tasi
                date_str = to_tashkent(r.created_at).strftime("%d.%m.%Y")
                unit_num = r.unit.number if r.unit else "?"
                text += f"📅 {date_str} | {unit_num}-dars: <b>{r.score}%</b>\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data=f"mentor_list_{group_id}")
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- Student Side: Resource View ---
@router.callback_query(F.data == "show_resources")
async def student_show_resources(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if not user or not user.group_id:
            await callback.answer("Siz hali hech qaysi guruhga biriktirilmagansiz.", show_alert=True)
            return
            
        stmt = select(Resource).where(Resource.group_id == user.group_id).order_by(Resource.created_at.desc())
        resources = (await session.execute(stmt)).scalars().all()
        
        if not resources:
            await callback.answer("Guruhda hali resurslar yo'q.", show_alert=True)
            return
            
        text = "📚 <b>Guruh materiallari:</b>\n\n"
        builder = InlineKeyboardBuilder()
        for r in resources:
            icon = "📄" if r.resource_type == "pdf" else "🔗" if r.resource_type == "link" else "🎬"
            builder.button(text=f"{icon} {r.title}", callback_data=f"view_res_{r.id}")
            
        builder.button(text="🔙 Orqaga", callback_data="back_to_main")
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("view_res_"))
async def student_view_resource(callback: CallbackQuery, bot: Bot):
    res_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        res = await session.get(Resource, res_id)
        if not res: return
        
        if res.resource_type in ["pdf", "video", "file"]:
            try:
                await bot.copy_message(callback.from_user.id, callback.message.chat.id, message_id=int(res.content)) 
                # Note: This copy_message logic might need adjustment if content is just file_id
                # Better: use send_document / send_video
                if res.resource_type == "pdf":
                    await bot.send_document(callback.from_user.id, res.content, caption=res.title)
                elif res.resource_type == "video":
                    await bot.send_video(callback.from_user.id, res.content, caption=res.title)
            except:
                # If content is a file_id
                if res.resource_type == "pdf":
                    await bot.send_document(callback.from_user.id, res.content, caption=res.title)
                elif res.resource_type == "video":
                    await bot.send_video(callback.from_user.id, res.content, caption=res.title)
                else:
                    await callback.message.answer(f"Resurs: {res.content}")
        else:
            await callback.message.answer(f"🔗 <b>{res.title}</b>\n\n{res.content}", parse_mode="HTML")
    await callback.answer()

# --- Inactivity Tracker (Who missed tests) ---
@router.callback_query(F.data.startswith("mentor_lazy_"))
async def mentor_lazy_list(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        # Guruhdagi barcha o'quvchilar
        group = await session.get(Group, group_id, options=[selectinload(Group.users)])
        
        # Oxirgi 7 kunda test ishlaganlar
        from datetime import datetime, timedelta
        seven_days_ago = datetime.now(TASHKENT_TZ) - timedelta(days=7)
        
        active_user_ids_stmt = select(TestResult.user_id).where(TestResult.created_at >= seven_days_ago).distinct()
        active_user_ids = (await session.execute(active_user_ids_stmt)).scalars().all()
        
        lazy_students = [u for u in group.users if u.id not in active_user_ids]
        
        text = f"⏳ <b>So'nggi 7 kunda test ishlamaganlar ({len(lazy_students)} ta):</b>\n\n"
        if not lazy_students:
            text += "✅ Hamma faol! Dam olishingiz mumkin."
        else:
            for i, u in enumerate(lazy_students, 1):
                text += f"{i}. <b>{u.first_name} {u.last_name or ''}</b>\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data=f"mentor_group_{group_id}")
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- Resource Management ---
@router.callback_query(F.data.startswith("mentor_res_"))
async def mentor_resources(callback: CallbackQuery):
    group_id = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        stmt = select(Resource).where(Resource.group_id == group_id).order_by(Resource.created_at.desc())
        resources = (await session.execute(stmt)).scalars().all()
        
        text = f"📚 <b>Guruh resurslari:</b>\n\n"
        if not resources:
            text += "Hali resurslar qo'shilmagan."
        else:
            for r in resources:
                icon = "📄" if r.resource_type == "pdf" else "🔗" if r.resource_type == "link" else "🎬"
                text += f"{icon} {r.title}\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Yangi qo'shish", callback_data=f"mentor_addres_{group_id}")
        builder.button(text="🔙 Orqaga", callback_data=f"mentor_group_{group_id}")
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data.startswith("mentor_addres_"))
async def start_add_resource(callback: CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(res_group_id=group_id)
    await state.set_state(MentorState.waiting_for_resource_title)
    await callback.message.answer("📝 Resurs nomini kiriting (masalan: '1-mavzu qo'shimcha material'):")
    await callback.answer()

@router.message(MentorState.waiting_for_resource_title)
async def process_res_title(message: Message, state: FSMContext):
    await state.update_data(res_title=message.text)
    await state.set_state(MentorState.waiting_for_resource_content)
    await message.answer("📎 Endi resursni yuboring (Fayl, Video yoki Havola (Link) matn ko'rinishida):")

@router.message(MentorState.waiting_for_resource_content)
async def process_res_content(message: Message, state: FSMContext):
    data = await state.get_data()
    group_id = data['res_group_id']
    title = data['res_title']
    
    res_type = "text"
    content = ""
    
    if message.document:
        res_type = "pdf" if message.document.mime_type == "application/pdf" else "file"
        content = message.document.file_id
    elif message.video:
        res_type = "video"
        content = message.video.file_id
    elif message.text:
        res_type = "link" if message.text.startswith("http") else "text"
        content = message.text
    else:
        await message.answer("Noma'lum format. Iltimos, fayl yoki matn ko'rinishida yuboring.")
        return

    async with AsyncSessionLocal() as session:
        new_res = Resource(group_id=group_id, title=title, resource_type=res_type, content=content)
        session.add(new_res)
        await session.commit()
    
    await state.clear()
    await message.answer("✅ Resurs muvaffaqiyatli qo'shildi!")
    
    # Guruh menyusiga qaytish
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.chat.id))).scalar_one_or_none()
    await message.answer("Menyu:", reply_markup=get_reply_main_menu(user))
