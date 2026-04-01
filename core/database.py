from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.config import settings

# Async PostgreSQL Engine yaratish (Pool sozlamalari bilan)
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800
)

# Async Session Maker konfiguratsiyasi
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False
)

# Har bir so'rov yoki process uchun sessionni olish generatori
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
