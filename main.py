import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from contextlib import asynccontextmanager
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- КОНФИГ ---
ADMIN_ID = 430747895
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
DONATE_URL = "https://yoomoney.ru/to/4100118943714856"

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH = os.path.join(BASE_DIR, "users.db")

for p in [STATIC_DIR, AUDIO_DIR, TEMPLATES_DIR]: 
    os.makedirs(p, exist_ok=True)

# --- ИИ И БАЗА ---
GEMINI_KEY = os.getenv("GEMINI_KEY")
if not GEMINI_KEY:
    logger.warning("GEMINI_KEY не установлен! Функция чата будет недоступна.")
    model_ai = None
else:
    genai.configure(api_key=GEMINI_KEY)
    model_ai = genai.GenerativeModel('gemini-1.5-flash')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

init_db()

# --- ГОЛОСА (ПОЛНЫЙ СПИСОК ДЛЯ БОТА И САЙТА) ---
VOICES = {
    "🇷🇺 СНГ": [
        ("Дмитрий (RU)", "ru-RU-DmitryNeural"),
        ("Светлана (RU)", "ru-RU-SvetlanaNeural"),
        ("Даулет (KZ)", "kk-KZ-DauletNeural"),
        ("Остап (UA)", "uk-UA-OstapNeural"),
        ("Полина (UA)", "uk-UA-PolinaNeural")
    ],
    "🇺🇸 EN / EU": [
        ("Ava (US)", "en-US-AvaNeural"),
        ("Andrew (US)", "en-US-AndrewNeural"),
        ("Sonia (GB)", "en-GB-SoniaNeural"),
        ("Katja (DE)", "de-DE-KatjaNeural"),
        ("Denise (FR)", "fr-FR-DeniseNeural"),
        ("Elvira (ES)", "es-ES-ElviraNeural")
    ],
    "🇯🇵 ASIA": [
        ("Nanami (JP)", "ja-JP-NanamiNeural"),
        ("SunHi (KR)", "ko-KR-SunHiNeural"),
        ("Xiaoxiao (CN)", "zh-CN-XiaoxiaoNeural")
    ]
}

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    # Валидация длины текста
    if len(text) > 3000:
        raise ValueError("Текст слишком длинный (макс. 3000 символов)")
    
    if not text.strip():
        raise ValueError("Текст не может быть пустым")
    
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(AUDIO_DIR, file_id)
    
    def fix_stress(t):
        # Исправлено: используем raw string и правильную обработку
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        pattern = rf'\+([{vowels}])'
        return re.sub(pattern, lambda m: m.group(1) + '\u0301', t)

    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")
    
    try:
        communicate = edge_tts.Communicate(fix_stress(text), voice, rate=rate)
        await communicate.save(file_path)
        return file_id
    except Exception as e:
        # Удаляем файл в случае ошибки
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e

# --- МОДЕЛИ Pydantic ---
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=3000, description="Текст для озвучки")
    voice: str = Field(..., description="ID голоса")
    mode: str = Field(default="natural", description="Режим скорости: natural, slow, fast")

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Сообщение для ИИ")

# --- FastAPI ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте
    logger.info("Запуск приложения...")
    yield
    # При остановке
    logger.info("Остановка приложения...")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate")
async def api_gen(req: TTSRequest):
    try:
        fid = await generate_speech_logic(req.text, req.voice, req.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Ошибка генерации речи: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def api_chat(req: ChatRequest):  # Исправлено: используем ChatRequest вместо BaseModel
    if not model_ai:
        raise HTTPException(status_code=503, detail="Сервис ИИ временно недоступен (API ключ не настроен)")
    
    try:
        res = await asyncio.to_thread(model_ai.generate_content, req.message)
        if not res.text:
            return {"reply": "ИИ не смог сгенерировать ответ"}
        return {"reply": res.text}
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обработке запроса ИИ")

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_texts = {}

def save_user(user_id: int):
    """Сохранение пользователя в БД с обработкой ошибок"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")

@dp.message(Command("start"))
async def cmd_start(message: Message):
    save_user(message.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💰 Поддержать проект", url=DONATE_URL))
    await message.answer(
        f"Привет! Пришли текст, и я его озвучу.\nНа сайте доступно 100+ голосов!", 
        reply_markup=kb.as_markup()
    )

@dp.message(F.text)
async def handle_msg(message: Message):
    if message.text.startswith("/"):
        return
    
    # Проверка длины текста
    if len(message.text) > 3000:
        await message.answer("❌ Текст слишком длинный. Максимум 3000 символов.")
        return
    
    user_texts[message.from_user.id] = message.text
    kb = InlineKeyboardBuilder()
    
    # Собираем кнопки по категориям (построчно)
    for cat, voices in VOICES.items():
        for name, vid in voices:
            kb.button(text=name, callback_data=f"v_{vid}")
    
    # Распределяем по 2 кнопки в ряд
    kb.adjust(2)
    
    await message.answer("🎙 Выберите голос для озвучки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def voice_call(callback: CallbackQuery):
    voice = callback.data.split("_", 1)[1]  # Исправлено: split с limit
    text = user_texts.get(callback.from_user.id)
    
    if not text:
        await callback.answer("❌ Сессия истекла. Отправьте текст заново.", show_alert=True)
        return
    
    msg = await callback.message.answer("⌛ Генерирую аудио...")
    
    try:
        fid = await generate_speech_logic(text, voice, "natural")
        file_path = os.path.join(AUDIO_DIR, fid)
        
        await callback.message.answer_audio(
            FSInputFile(file_path), 
            caption=f"✅ Готово! Голос: {voice}\n🔊 {CHANNEL_URL}"
        )
        await msg.delete()
        
        # Удаляем файл после отправки (опционально, раскомментируйте если нужно)
        # await asyncio.sleep(5)
        # if os.path.exists(file_path):
        #     os.remove(file_path)
            
    except Exception as e:
        logger.error(f"Ошибка генерации для пользователя {callback.from_user.id}: {e}")
        await msg.edit_text(f"❌ Ошибка генерации: {str(e)[:200]}")
    
    await callback.answer()

# Запуск бота в отдельной задаче
async def start_bot():
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_bot())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))





