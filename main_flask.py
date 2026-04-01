import asyncio
import sys

# Windows muhitida psycopg Driver bilan Asyncio ishlashi uchun zarur:
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import os
from dotenv import load_dotenv
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from core.database import AsyncSessionLocal
from db.models import User, Unit, Question, Section, AnswerOption, SystemSetting, TestResult, Group, Attendance
from datetime import timezone, timedelta

TASHKENT_TZ = timezone(timedelta(hours=5))

def to_tashkent(dt):
    """UTC vaqtni Toshkent vaqtiga o'tkazish"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TASHKENT_TZ)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

def run_async(coro):
    return asyncio.run(coro)

@app.route("/")
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    async def get_stats():
        async with AsyncSessionLocal() as db_session:
            # Overall users
            users_count = await db_session.scalar(select(func.count(User.id))) or 0
            
            # Level-wise stats
            stats = {
                "A1": {"units": 0, "questions": 0},
                "A2": {"units": 0, "questions": 0},
                "B1": {"units": 0, "questions": 0},
                "B2": {"units": 0, "questions": 0},
                "None": {"units": 0, "questions": 0}
            }
            
            # Count Units per level
            units_stmt = select(Unit.level, func.count(Unit.id)).where(Unit.is_active == True).group_by(Unit.level)
            units_res = await db_session.execute(units_stmt)
            for level, count in units_res.all():
                lvl = level if level else "None"
                if lvl in stats:
                    stats[lvl]["units"] = count
                else:
                    stats[lvl] = {"units": count, "questions": 0}
            
            # Count Questions per level (join with Unit)
            questions_stmt = select(Unit.level, func.count(Question.id)).join(Unit).where(Unit.is_active == True).group_by(Unit.level)
            questions_res = await db_session.execute(questions_stmt)
            for level, count in questions_res.all():
                lvl = level if level else "None"
                if lvl in stats:
                    stats[lvl]["questions"] = count
                    
            total_questions = sum(s["questions"] for s in stats.values())
            total_units = sum(s["units"] for s in stats.values())
            
            return users_count, stats, total_units, total_questions

    try:
        users_count, stats, total_units, total_questions = run_async(get_stats())
    except Exception as e:
        users_count, stats, total_units, total_questions = 0, {}, 0, 0
        print(f"Xato: {e}")

    return render_template("index.html", 
                           users=users_count, 
                           stats=stats,
                           total_units=total_units,
                           total_questions=total_questions)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            flash("Login yoki parol noto'g'ri", "error")
    return render_template("login.html")

@app.route("/attendance")
def attendance_list():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date") # YYYY-MM-DD
    
    async def get_attendance():
        async with AsyncSessionLocal() as db_session:
            groups = (await db_session.execute(select(Group))).scalars().all()
            
            stmt = select(Attendance).options(selectinload(Attendance.user), selectinload(Attendance.group))
            
            if group_id:
                stmt = stmt.where(Attendance.group_id == group_id)
            if date_str:
                from datetime import datetime
                try:
                    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    stmt = stmt.where(Attendance.date == target_date)
                except:
                    pass
            
            stmt = stmt.order_by(Attendance.date.desc(), Attendance.created_at.desc())
            results = (await db_session.execute(stmt)).scalars().all()
            
            return groups, results

    try:
        groups, attendance_records = run_async(get_attendance())
    except Exception as e:
        groups, attendance_records = [], []
        print(f"Attendance error: {e}")
    
    return render_template("attendance.html", 
                           groups=groups, 
                           records=attendance_records,
                           selected_group=group_id,
                           selected_date=date_str,
                           active_page='attendance')

@app.route("/units")
def units():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def get_units():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Unit).order_by(Unit.level, Unit.number))
            return result.scalars().all()
    
    units_list = run_async(get_units())
    return render_template("units.html", units_list=units_list)

@app.route("/units/add", methods=["POST"])
def add_unit():
    if not session.get("logged_in"): return redirect(url_for("login"))
    number = request.form.get("number", type=int)
    title = request.form.get("title")
    is_active = request.form.get("is_active") == "on"

    async def save_unit():
        level = request.form.get("level")
        async with AsyncSessionLocal() as db:
            try:
                new_unit = Unit(number=number, title=title, is_active=is_active, level=level)
                db.add(new_unit)
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print(f"Db Xato: {e}")
                return False
                
    if run_async(save_unit()):
        flash("Yangi mavzu qo'shildi!", "success")
    else:
        flash("Mavzu qo'shishda xatolik! Dars raqami takrorlanmasligi kerak.", "error")
        
    return redirect(url_for("units"))

@app.route("/units/toggle/<int:unit_id>", methods=["POST"])
def toggle_unit(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def update_status():
        async with AsyncSessionLocal() as db:
            unit = await db.get(Unit, unit_id)
            if unit:
                unit.is_active = not unit.is_active
                await db.commit()
                
    run_async(update_status())
    flash("Mavzu holati o'zgartirildi!", "success")
    return redirect(url_for("units"))

@app.route("/units/delete/<int:unit_id>", methods=["POST"])
def delete_unit(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def remove_unit():
        async with AsyncSessionLocal() as db:
            unit = await db.get(Unit, unit_id)
            if unit:
                await db.delete(unit)
                await db.commit()
                
    run_async(remove_unit())
    flash("Mavzu o'chirildi!", "success")
    return redirect(url_for("units"))

@app.route("/units/edit/<int:unit_id>", methods=["POST"])
def edit_unit(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    number = request.form.get("number", type=int)
    title = request.form.get("title")
    is_active = request.form.get("is_active") == "on"

    async def update_unit():
        level = request.form.get("level")
        async with AsyncSessionLocal() as db:
            unit = await db.get(Unit, unit_id)
            if unit:
                unit.number = number
                unit.title = title
                unit.is_active = is_active
                unit.level = level
                await db.commit()
                return True
            return False
            
    if run_async(update_unit()):
        flash("Mavzu muvaffaqiyatli tahrirlandi!", "success")
    else:
        flash("Tahrirlashda xatolik yuz berdi!", "error")
        
    return redirect(url_for("units"))

@app.route("/groups")
def groups():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def get_data():
        async with AsyncSessionLocal() as db:
            groups_res = await db.execute(select(Group).options(selectinload(Group.users), selectinload(Group.teacher)).order_by(Group.id.desc()))
            teachers_res = await db.execute(select(User).where(User.role == 'teacher').order_by(User.first_name))
            return groups_res.scalars().all(), teachers_res.scalars().all()
            
    groups_list, teachers_list = run_async(get_data())
    return render_template("groups.html", groups_list=groups_list, teachers_list=teachers_list)

@app.route("/groups/add", methods=["POST"])
def add_group():
    if not session.get("logged_in"): return redirect(url_for("login"))
    name = request.form.get("name")
    teacher_id = request.form.get("teacher_id", type=int)
    
    async def save_group():
        async with AsyncSessionLocal() as db:
            try:
                new_group = Group(
                    name=name,
                    teacher_id=teacher_id if teacher_id and teacher_id > 0 else None
                )
                db.add(new_group)
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print(e)
                return False
                
    if run_async(save_group()):
        flash("Yangi guruh qo'shildi!", "success")
    else:
        flash("Guruh qo'shishda xatolik (Bunday nomli guruh mavjud bo'lishi mumkin)!", "error")
        
    return redirect(url_for("groups"))

@app.route("/groups/edit/<int:group_id>", methods=["POST"])
def edit_group(group_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    name = request.form.get("name")
    teacher_id = request.form.get("teacher_id", type=int)
    
    async def update_group():
        async with AsyncSessionLocal() as db:
            group = await db.get(Group, group_id)
            if group:
                group.name = name
                group.teacher_id = teacher_id if teacher_id and teacher_id > 0 else None
                await db.commit()
                return True
            return False
            
    if run_async(update_group()):
        flash("Guruh nomi o'zgartirildi!", "success")
    else:
        flash("Xatolik yuz berdi!", "error")
        
    return redirect(url_for("groups"))

@app.route("/groups/delete/<int:group_id>", methods=["POST"])
def delete_group(group_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def remove_group():
        async with AsyncSessionLocal() as db:
            group = await db.get(Group, group_id)
            if group:
                await db.delete(group)
                await db.commit()
                
    run_async(remove_group())
    flash("Guruh o'chirildi!", "success")
    return redirect(url_for("groups"))

# AnswerOption already imported above

@app.route("/sections/<int:unit_id>")
def sections(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def get_data():
        async with AsyncSessionLocal() as db:
            unit = await db.get(Unit, unit_id)
            result = await db.execute(select(Section).where(Section.unit_id == unit_id).order_by(Section.number))
            return unit, result.scalars().all()
    
    unit, sections_list = run_async(get_data())
    return render_template("sections.html", unit=unit, sections_list=sections_list)

@app.route("/sections/add/<int:unit_id>", methods=["POST"])
def add_section(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    number = request.form.get("number", type=int)
    title = request.form.get("title")

    async def save_section():
        async with AsyncSessionLocal() as db:
            try:
                new_sec = Section(unit_id=unit_id, number=number, title=title)
                db.add(new_sec)
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print(e)
                return False
                
    if run_async(save_section()):
        flash("Yangi bo'lim qo'shildi!", "success")
    else:
        flash("Bo'lim qo'shishda xatolik!", "error")
        
    return redirect(url_for("sections", unit_id=unit_id))

@app.route("/sections/edit/<int:section_id>", methods=["POST"])
def edit_section(section_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    number = request.form.get("number", type=int)
    title = request.form.get("title")

    async def update_sec():
        async with AsyncSessionLocal() as db:
            sec = await db.get(Section, section_id)
            if sec:
                sec.number = number
                sec.title = title
                await db.commit()
                return sec.unit_id
            return None
                
    unit_id = run_async(update_sec())
    if unit_id:
        flash("Bo'lim tahrirlandi!", "success")
        return redirect(url_for("sections", unit_id=unit_id))
    flash("Xatolik yuz berdi!", "error")
    return redirect(url_for("units"))

@app.route("/sections/delete/<int:section_id>", methods=["POST"])
def delete_section(section_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def del_sec():
        async with AsyncSessionLocal() as db:
            sec = await db.get(Section, section_id)
            if sec:
                unit_id = sec.unit_id
                await db.delete(sec)
                await db.commit()
                return unit_id
            return None
                
    unit_id = run_async(del_sec())
    flash("Bo'lim o'chirildi!", "success")
    return redirect(url_for("sections", unit_id=unit_id) if unit_id else url_for("units"))

@app.route("/questions")
def questions():
    if not session.get("logged_in"): return redirect(url_for("login"))
    unit_id = request.args.get('unit_id')
    
    async def get_data():
        async with AsyncSessionLocal() as db:
            # Darslarni va ularning bo'limlarini olish
            units_stmt = select(Unit).options(selectinload(Unit.sections)).order_by(Unit.number)
            units = (await db.execute(units_stmt)).scalars().all()
            
            # Savollarni olish
            stmt = select(Question).options(
                selectinload(Question.unit), 
                selectinload(Question.section),
                selectinload(Question.options)
            )
            if unit_id:
                stmt = stmt.where(Question.unit_id == int(unit_id))
                
            questions = (await db.execute(stmt.order_by(Question.id.desc()))).scalars().all()
            return units, [q.to_dict() for q in questions]
            
    units, questions_list = run_async(get_data())
    return render_template("questions.html", units=units, questions_list=questions_list, current_unit_id=unit_id)

@app.route("/questions/add", methods=["POST"])
def add_question():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    unit_id = request.form.get("unit_id", type=int)
    section_id = request.form.get("section_id", type=int)
    text = request.form.get("text")
    time_limit = request.form.get("time_limit", type=int, default=30)
    correct_option = request.form.get("correct_option") # 1, 2, 3 or 4
    
    async def save_q():
        async with AsyncSessionLocal() as db:
            try:
                # Savolni yaratish
                new_q = Question(unit_id=unit_id, section_id=section_id, text=text, time_limit=time_limit)
                db.add(new_q)
                await db.flush() # id ni olish uchun
                
                # Variantlarni yaratish
                for i in range(1, 5):
                    opt_text = request.form.get(f"option_{i}")
                    if opt_text and opt_text.strip():
                        is_corr = (str(i) == correct_option)
                        db.add(AnswerOption(question_id=new_q.id, text=opt_text.strip(), is_correct=is_corr))
                        
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print(e)
                return False
                
    if run_async(save_q()):
        flash("Savol muvaffaqiyatli qo'shildi!", "success")
    else:
        flash("Savol qo'shishda xatolik yuz berdi.", "error")
        
    return redirect(url_for("questions"))

@app.route("/questions/delete/<int:q_id>", methods=["POST"])
def delete_question(q_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def del_q():
        async with AsyncSessionLocal() as db:
            q = await db.get(Question, q_id)
            if q:
                await db.delete(q)
                await db.commit()
                
    run_async(del_q())
    flash("Savol o'chirildi!", "success")
    return redirect(url_for("questions"))

@app.route("/questions/clear/<int:unit_id>", methods=["POST"])
def clear_unit_questions(unit_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def clear_q():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Question).where(Question.unit_id == unit_id).options(selectinload(Question.options))
            )
            questions = result.scalars().all()
            for q in questions:
                await db.delete(q)
            await db.commit()
            return len(questions)
                
    count = run_async(clear_q())
    flash(f"{count} ta savol o'chirildi!", "success")
    return redirect(url_for("questions"))

@app.route("/questions/clear_section/<int:section_id>", methods=["POST"])
def clear_section_questions(section_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def clear_s_q():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Question).where(Question.section_id == section_id).options(selectinload(Question.options))
            )
            questions = result.scalars().all()
            for q in questions:
                await db.delete(q)
            await db.commit()
            return len(questions)
                
    count = run_async(clear_s_q())
    flash(f"Bo'limdagi {count} ta savol o'chirildi!", "success")
    return redirect(url_for("questions"))

@app.route("/questions/edit/<int:q_id>", methods=["POST"])
def edit_question(q_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    unit_id = request.form.get("unit_id", type=int)
    section_id = request.form.get("section_id", type=int)
    text = request.form.get("text")
    time_limit = request.form.get("time_limit", type=int)
    correct_option = request.form.get("correct_option") # 1, 2, 3 or 4
    
    async def update_q():
        async with AsyncSessionLocal() as db:
            try:
                # Savolni olish (variantlari bilan birga)
                stmt = select(Question).where(Question.id == q_id).options(selectinload(Question.options))
                result = await db.execute(stmt)
                q = result.scalar_one_or_none()
                
                if q:
                    q.unit_id = unit_id
                    q.section_id = section_id
                    q.text = text
                    q.time_limit = time_limit
                    
                    # Variantlarni ID bo'yicha saralab olish, option_i bilan mos kelishi uchun
                    sorted_options = sorted(q.options, key=lambda x: x.id)
                    
                    for i, opt in enumerate(sorted_options, 1):
                        opt_text = request.form.get(f"option_{i}")
                        if opt_text:
                            opt.text = opt_text.strip()
                            opt.is_correct = (str(i) == correct_option)
                        else:
                            await db.delete(opt)
                            
                    # Agar qo'shimcha yangi variantlar bo'lsa
                    current_count = len(sorted_options)
                    for i in range(current_count + 1, 5):
                        opt_text = request.form.get(f"option_{i}")
                        if opt_text and opt_text.strip():
                            is_corr = (str(i) == correct_option)
                            db.add(AnswerOption(question_id=q.id, text=opt_text.strip(), is_correct=is_corr))

                    await db.commit()
                    return True
                return False
            except Exception as e:
                await db.rollback()
                print(e)
                return False
                
    if run_async(update_q()):
        flash("Savol tahrirlandi!", "success")
    else:
        flash("Savolni tahrirlashda xatolik yuz berdi.", "error")
        
    return redirect(url_for("questions"))

import openpyxl

@app.route("/questions/import_excel", methods=["POST"])
def import_excel():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    file = request.files.get("excel_file")
    unit_id = request.form.get("unit_id", type=int)
    section_id = request.form.get("section_id", type=int)
    
    if not file or not unit_id or not section_id:
        flash("Fayl, dars yoki bo'lim tanlanmadi!", "error")
        return redirect(url_for("questions"))
        
    async def process_excel():
        async with AsyncSessionLocal() as db:
            try:
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                
                # Excel tuzilishi: Savol, Vaqt(sek), To'g'ri_Variant, Var1, Var2, Var3, Var4
                # Birinchi qator sarlavha deb qabul qilinadi
                for row in list(sheet.iter_rows(values_only=True))[1:]:
                    if not row or not row[0]: continue
                    
                    text = str(row[0])
                    time_limit = int(row[1]) if row[1] else 30
                    
                    # Excelda son bo'lsa 1.0 bo'lib kelishi mumkin, shuni to'g'irlaymiz
                    try:
                        correct_opt_idx = str(int(float(row[2]))) if row[2] else "1"
                    except:
                        correct_opt_idx = str(row[2]) if row[2] else "1"
                        
                    opts = [str(row[3]) if row[3] else None, 
                            str(row[4]) if row[4] else None, 
                            str(row[5]) if len(row) > 5 and row[5] else None, 
                            str(row[6]) if len(row) > 6 and row[6] else None]
                            
                    new_q = Question(unit_id=unit_id, section_id=section_id, text=text, time_limit=time_limit)
                    db.add(new_q)
                    await db.flush()
                    
                    for i, opt_text in enumerate(opts, 1):
                        if opt_text:
                            is_corr = (str(i) == correct_opt_idx)
                            db.add(AnswerOption(question_id=new_q.id, text=opt_text.strip(), is_correct=is_corr))
                            
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                print("Excel xato:", e)
                return False
                
    if run_async(process_excel()):
        flash("Excel fayl orqali savollar yuklandi!", "success")
    else:
        flash("Excel faylni o'qishda yoki yuklashda xato yuz berdi. Formatni tekshiring.", "error")
        
    return redirect(url_for("questions"))

@app.route("/users")
def users():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def get_data():
        async with AsyncSessionLocal() as db:
            users_res = await db.execute(select(User).options(selectinload(User.group)).order_by(User.created_at.desc()))
            groups_res = await db.execute(select(Group).order_by(Group.name))
            return users_res.scalars().all(), groups_res.scalars().all()
            
    users_list, groups_list = run_async(get_data())
    return render_template("users.html", users_list=users_list, groups_list=groups_list)

@app.route("/api/user/group/<int:user_id>", methods=["POST"])
def update_user_group(user_id):
    if not session.get("logged_in"): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.get_json()
    group_id = data.get("group_id")
    
    async def save_group():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user:
                user.group_id = group_id if group_id and group_id > 0 else None
                await db.commit()
                return True
            return False
            
    if run_async(save_group()):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Foydalanuvchi topilmadi"})

@app.route("/rating")
def rating():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def get_rating_data():
        async with AsyncSessionLocal() as db:
            # Barcha foydalanuvchilarni natijalar bilan birga olish
            stmt = select(User).options(selectinload(User.results))
            result = await db.execute(stmt)
            users_list = result.scalars().all()
            
            rating_stats = []
            for u in users_list:
                total_q = sum(r.total_questions for r in u.results)
                correct = sum(r.correct_answers for r in u.results)
                avg_score = round((correct / total_q * 100), 1) if total_q > 0 else 0
                
                # Formula: To'g'ri javoblar * (Foiz / 100)
                weighted_score = round(correct * (avg_score / 100), 1)
                
                rating_stats.append({
                    'user': u,
                    'total_tests': len(u.results),
                    'total_correct': correct,
                    'total_questions': total_q,
                    'avg_score': avg_score,
                    'weighted_score': weighted_score
                })
            
            # Ballar o'rniga adolatli Reyting Balli (weighted_score) bo'yicha saralash
            rating_stats.sort(key=lambda x: x['weighted_score'], reverse=True)
            return rating_stats
            
    rating_data = run_async(get_rating_data())
    return render_template("rating.html", rating_data=rating_data)

@app.route("/api/user_tests/<int:user_id>")
def api_user_tests(user_id):
    if not session.get("logged_in"): return jsonify({"error": "Unauthorized"}), 401
    
    async def get_user_tests():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if not user:
                return None, []
            
            stmt = select(TestResult).where(
                TestResult.user_id == user_id
            ).options(
                selectinload(TestResult.unit),
                selectinload(TestResult.section)
            ).order_by(TestResult.created_at.desc())
            
            results = (await db.execute(stmt)).scalars().all()
            
            tests = []
            for r in results:
                unit_name = f"{r.unit.number}-dars: {r.unit.title}" if r.unit else "Noma'lum"
                section_name = r.section.title if r.section else "-"
                tests.append({
                    'unit': unit_name,
                    'section': section_name,
                    'total': r.total_questions,
                    'correct': r.correct_answers,
                    'wrong': r.wrong_answers,
                    'score': r.score,
                    'date': to_tashkent(r.created_at).strftime("%d.%m.%Y %H:%M") if r.created_at else "-"
                })
            
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
            return full_name, tests
    
    full_name, tests = run_async(get_user_tests())
    if full_name is None:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"name": full_name, "tests": tests})

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    async def handle_settings():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SystemSetting))
            setting = result.scalars().first()
            if not setting:
                setting = SystemSetting(send_bot_startup_message=True)
                db.add(setting)
                await db.commit()
                await db.refresh(setting)
                
            if request.method == "POST":
                send_msg = request.form.get("send_bot_startup_message") == "on"
                setting.send_bot_startup_message = send_msg
                await db.commit()
                return True, setting
            return False, setting
            
    is_updated, setting = run_async(handle_settings())
    if is_updated:
        flash("Sozlamalar saqlandi!", "success")
        return redirect(url_for("settings_page"))
        
    return render_template("settings.html", setting=setting)

@app.route("/api/user/role/<int:user_id>", methods=["POST"])
def toggle_user_role(user_id):
    if not session.get("logged_in"): 
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    new_role = data.get("role")
    
    if new_role not in ["admin", "user", "teacher"]:
        return jsonify({"error": "Invalid role"}), 400

    async def update_role():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user:
                user.role = new_role
                await db.commit()
                return True
            return False

    success = run_async(update_role())
    if success:
        return jsonify({"success": True, "role": new_role})
    else:
        return jsonify({"error": "User not found"}), 404

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    print("Flask Server ishga tushmoqda...")
    app.run(host="0.0.0.0", port=5050, debug=True)
