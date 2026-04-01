from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from db.models import Unit

def get_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Level buttons in 2x2 grid
    builder.button(text="𝗔𝟭", callback_data="level_A1")
    builder.button(text="𝗔𝟮", callback_data="level_A2")
    builder.button(text="𝗕𝟭", callback_data="level_B1")
    builder.button(text="𝗕𝟮", callback_data="level_B2")
    
    # Natijalar and Reyting full width
    builder.button(text="✅ Natijalarim", callback_data="show_my_results")
    builder.button(text="🏆 Reyting", callback_data="show_rating")
    builder.button(text="📚 Resurslar", callback_data="show_resources")
    
    builder.adjust(2, 2, 1, 1, 1)
    return builder.as_markup()

def get_reply_main_menu(user=None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    # Level buttons
    builder.button(text="𝗔𝟭")
    builder.button(text="𝗔𝟮")
    builder.button(text="𝗕𝟭")
    builder.button(text="𝗕𝟮")
    
    # Natijalar, Reyting and Profil
    builder.button(text="📊 Natijalar")
    builder.button(text="🏆 Reyting")
    builder.button(text="👤 Profil")
    builder.button(text="🇺🇿 Tilni o'zgartirish")
    
    if user and user.role == 'admin':
        builder.button(text="🎛 Admin panel")
    elif user and user.role == 'teacher':
        builder.button(text="👨‍🏫 O'qituvchi paneli")
    
    if user and (user.role == 'admin' or user.role == 'teacher'):
        builder.adjust(2, 2, 3, 1, 1)
    else:
        builder.adjust(2, 2, 2, 2)
    return builder.as_markup(resize_keyboard=True)

def get_units_keyboard(units: list[Unit]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for unit in units:
        text = f"{unit.number}-dars: {unit.title}"
        if not unit.is_active:
            text += " 🔒"
        builder.button(text=text, callback_data=f"unit_{unit.id}")
    builder.button(text="🔙 Orqaga", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_sections_keyboard(sections, unit_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sec in sections:
        builder.button(text=f"{sec.number}. {sec.title}", callback_data=f"section_{sec.id}")
    # We'll make it go back to the level menu for now, or we can use the level from the unit
    builder.button(text="🔙 Orqaga", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_question_keyboard(options: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for opt in options:
        builder.button(text=opt.text, callback_data=f"ans_{opt.id}")
    builder.adjust(1)
    return builder.as_markup()

def get_results_level_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="𝗔𝟭", callback_data="res_level_A1")
    builder.button(text="𝗔𝟮", callback_data="res_level_A2")
    builder.button(text="𝗕𝟭", callback_data="res_level_B1")
    builder.button(text="𝗕𝟮", callback_data="res_level_B2")
    builder.adjust(2)
    return builder.as_markup()

def get_results_units_keyboard(units: list[Unit]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for unit in units:
        builder.button(text=f"{unit.number}-dars: {unit.title}", callback_data=f"res_unit_{unit.id}")
    builder.button(text="⬅️ Orqaga", callback_data="show_my_results")
    builder.adjust(1)
    return builder.as_markup()

def get_attendance_status_keyboard(user_id: int, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Keldi", callback_data=f"att_present_{user_id}_{group_id}")
    builder.button(text="❌ Kelmadi", callback_data=f"att_absent_{user_id}_{group_id}")
    builder.button(text="⏳ Kechikdi", callback_data=f"att_late_{user_id}_{group_id}")
    builder.button(text="🔙 To'xtatish", callback_data=f"mentor_group_{group_id}")
    builder.adjust(2, 1, 1)
    return builder.as_markup()
