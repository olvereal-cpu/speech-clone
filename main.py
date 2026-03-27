import os
import re
import uuid
import asyncio
import ssl
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_URL = "https://t.me/speechclone"
CHANNEL_ID = "@speechclone" 

# --- БАЗА ДАННЫХ (SQLite) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

init_db()

# --- НАСТРОЙКА GEMINI AI 2.5 ---
GOOGLE_API_KEY = os.getenv("GEMINI_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

selected_model = 'gemini-2.5-flash' 

model_ai = genai.GenerativeModel(
    model_name=selected_model,
    system_instruction=(
        "Ты — Спич-Бро, официальный ИИ-помощник сайта SpeechClone.online. "
        "Помогай с озвучкой текста, пиши коротко и с эмодзи. "
        "Ударения: ставь '+' перед гласной. Скачивание: ожидание 30 сек."
    )
)

# --- ФИКС SSL ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# --- ИНИЦИАЛИЗАЦИЯ FastAPI ---
app = FastAPI(redirect_slashes=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for path in ["static", "static/audio", "static/images/blog", "templates", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ГЕНЕРАЦИИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        stress_symbol = chr(769) 
        return re.sub(r'\+([%s])' % vowels, r'\1' + stress_symbol, t)

    processed_text = fix_stress(clean_text)
    rates = {"natural": "-5%", "slow": "-15%", "fast": "+15%"}
    rate = rates.get(mode, "+0%")

    try:
        communicate = edge_tts.Communicate(processed_text, voice, rate=rate)
        await communicate.save(file_path)
    except:
        communicate = edge_tts.Communicate(clean_text.replace("+", ""), voice)
        await communicate.save(file_path)
    return file_id

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_data = {}

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    user_name = message.from_user.first_name or "друг"
    await message.answer(f"👋 Привет, {user_name}! Пришли текст для озвучки.\n💡 Используй **+** для ударения.")

# --- АДМИНКА ---
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    count = len(get_all_users())
    await message.answer(f"📊 Всего пользователей: {count}")

@dp.message(Command("db"))
async def cmd_db(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if os.path.exists(DB_PATH):
        await message.answer_document(types.FSInputFile(DB_PATH), caption="📦 База данных.")
    else:
        await message.answer("❌ Ошибка: БД не найдена.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.answer("❌ Формат: `/broadcast Текст`")
    users = get_all_users()
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Готово: {success}/{len(users)}")

# --- ОСНОВНАЯ ЛОГИКА И ПОДПИСКА ---
@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться на Канал", url=CHANNEL_URL))
        return await message.answer("⚠️ Чтобы пользоваться ботом, подпишись на наш канал!", reply_markup=kb.as_markup())

    add_user(uid)
    user_data[uid] = {"text": message.text}
    builder = InlineKeyboardBuilder()
    
    # --- ПОЛНЫЙ СПИСОК ГОЛОСОВ ---
    # Русские
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Екатерина", callback_data="v_ru-RU-EkaterinaNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Дарья", callback_data="v_ru-RU-DariyaNeural"))
    # Казахские
    builder.row(types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"),
                types.InlineKeyboardButton(text="🇰🇿 Айгуль", callback_data="v_kk-KZ-AigulNeural"))
    # Английские
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Ava", callback_data="v_en-US-AvaNeural"),
                types.InlineKeyboardButton(text="🇺🇸 Andrew", callback_data="v_en-US-AndrewNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Emma", callback_data="v_en-US-EmmaNeural"),
                types.InlineKeyboardButton(text="🇬🇧 Sonia", callback_data="v_en-GB-SoniaNeural"))
    # Другие популярные
    builder.row(types.InlineKeyboardButton(text="🇩🇪 Katja", callback_data="v_de-DE-KatjaNeural"),
                types.InlineKeyboardButton(text="🇫🇷 Denise", callback_data="v_fr-FR-DeniseNeural"))
    
    builder.row(types.InlineKeyboardButton(text="⭐️ Поддержать", callback_data="donate_menu"))
    
    await message.answer("Выберите нейро-голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    if callback.from_user.id not in user_data: user_data[callback.from_user.id] = {}
    user_data[callback.from_user.id]["voice"] = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Обычный", callback_data="m_natural"),
                types.InlineKeyboardButton(text="Медленно", callback_data="m_slow"),
                types.InlineKeyboardButton(text="Быстро", callback_data="m_fast"))
    await callback.message.edit_text("Выберите скорость:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_data: return
    data = user_data[uid]
    status_msg = await callback.message.edit_text("⌛ Gemini 2.5 генерирует аудио...")
    try:
        file_id = await generate_speech_logic(data["text"][:1000], data.get("voice", "ru-RU-DmitryNeural"), mode)
        await callback.message.answer_audio(types.FSInputFile(os.path.join(BASE_DIR, "static/audio", file_id)))
        await status_msg.delete()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

# --- WEB API ---
@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: model_ai.generate_content(request.message))
        return {"reply": res.text if res else "..."}
    except Exception as e: 
        return {"reply": f"Ошибка Gemini 2.5: {str(e)}"}

@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request): 
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except:
        return HTMLResponse("<h1>Сайт загружается... Обновите страницу через минуту.</h1>")

@app.get("/get-audio/{f}")
async def get_audio(f: str): 
    return FileResponse(os.path.join(BASE_DIR, "static/audio", f))

@app.get("/{p}")
async def other_pages(request: Request, p: str):
    try: 
        return templates.TemplateResponse(f"{p}.html", {"request": request})
    except: 
        return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    if not os.environ.get("BOT_RUNNING"):
        os.environ["BOT_RUNNING"] = "true"
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            asyncio.create_task(dp.start_polling(bot))
        except: pass






