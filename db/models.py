from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, BigInteger, Float, text, Date
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Responsible teacher
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="group", foreign_keys="[User.group_id]")
    teacher = relationship("User", foreign_keys=[teacher_id], back_populates="mentored_groups")
    attendances = relationship("Attendance", back_populates="group", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False) # Roles: 'user', 'admin', 'teacher'
    coins = Column(Integer, default=0) # For gamification
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True) # User's group (cohort)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), nullable=True)

    results = relationship("TestResult", back_populates="user", cascade="all, delete-orphan")
    group = relationship("Group", foreign_keys=[group_id], back_populates="users")
    mentored_groups = relationship("Group", foreign_keys=[Group.teacher_id], back_populates="teacher")
    attendances = relationship("Attendance", back_populates="user", cascade="all, delete-orphan")

    @property
    def full_name(self):
        parts = []
        if self.first_name: parts.append(self.first_name)
        if self.last_name: parts.append(self.last_name)
        
        if parts:
            return " ".join(parts)
        
        if self.username:
            return self.username.replace("@", "")
            
        return str(self.telegram_id)

class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    number = Column(Integer, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)  # Ochiq yoki Yopiq holati
    level = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    questions = relationship("Question", back_populates="unit", cascade="all, delete-orphan", order_by="Question.id")
    sections = relationship("Section", back_populates="unit", cascade="all, delete-orphan", order_by="Section.number")
    results = relationship("TestResult", back_populates="unit", cascade="all, delete-orphan")

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    unit = relationship("Unit", back_populates="sections")
    questions = relationship("Question", back_populates="section", cascade="all, delete-orphan", order_by="Question.id")
    results = relationship("TestResult", back_populates="section", cascade="all, delete-orphan")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True) # Bo'lim ixtiyoriy bo'lishi mumkin (yoki migrate uchun nullable)
    text = Column(String, nullable=False)
    file_id = Column(String, nullable=True) # Telegram rasm uchun file id
    time_limit = Column(Integer, default=30) # Default 30 sekund javob berish uchun

    unit = relationship("Unit", back_populates="questions")
    section = relationship("Section", back_populates="questions")
    options = relationship("AnswerOption", back_populates="question", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "unit_id": self.unit_id,
            "section_id": self.section_id,
            "text": self.text,
            "time_limit": self.time_limit,
            "options": [opt.to_dict() for opt in self.options]
        }

class AnswerOption(Base):
    __tablename__ = "answer_options"
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    text = Column(String, nullable=False)
    is_correct = Column(Boolean, default=False)

    question = relationship("Question", back_populates="options")

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.text,
            "is_correct": self.is_correct
        }

class TestResult(Base):
    __tablename__ = "test_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    
    total_questions = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    wrong_answers = Column(Integer, default=0)
    score = Column(Float, default=0.0) # foiz yoki ball ko'rinishi

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="results")
    unit = relationship("Unit", back_populates="results")
    section = relationship("Section", back_populates="results")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    send_bot_startup_message = Column(Boolean, default=True)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))
    date = Column(Date, server_default=func.current_date())
    status = Column(String)  # 'present', 'absent', 'late'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="attendances")
    group = relationship("Group", back_populates="attendances")

class Resource(Base):
    __tablename__ = "resources"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    resource_type = Column(String, nullable=False) # 'pdf', 'link', 'video', 'text'
    content = Column(String, nullable=False) # File ID or URL or Text
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("Group", backref="resources")
