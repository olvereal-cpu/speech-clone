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
    # status: 1 - активен, 0 - заблокировал
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, status INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, status) VALUES (?, 1)', (user_id,))
    cursor.execute('UPDATE users SET status = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def set_user_status(user_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET status = ? WHERE user_id = ?', (status, user_id))
    conn.commit()
    conn.close()

def get_stats_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE status = 1')
    active = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE status = 0')
    blocked = cursor.fetchone()[0]
    conn.close()
    return active, blocked

init_db()

# --- НАСТРОЙКА GEMINI AI ---
GOOGLE_API_KEY = os.getenv("GEMINI_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
model_ai = genai.GenerativeModel('gemini-1.5-flash')

# --- ФИКС SSL ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: pass
else: ssl._create_default_https_context = _create_unverified_https_context

# --- ИНИЦИАЛИЗАЦИЯ FastAPI ---
app = FastAPI(redirect_slashes=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for path in ["static", "static/audio", "static/images/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ОЗВУЧКИ ---
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
user_sessions = {}
admin_state = {}

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except: return False

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(types.InlineKeyboardButton(text="📥 Живая база (.txt)", callback_data="admin_db_txt"))
    builder.row(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast_start"))
    return builder.as_markup()

@dp.message(Command("adminka"))
async def cmd_adminka(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 **Панель управления SpeechClone**", reply_markup=get_admin_kb())

@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    if callback.data == "admin_stats":
        active, blocked = get_stats_data()
        await callback.message.answer(f"📈 **Данные:**\n✅ Живых: {active}\n🚫 Блокировали: {blocked}\n👥 Всего: {active + blocked}")
    elif callback.data == "admin_db_txt":
        conn = sqlite3.connect(DB_PATH)
        users = conn.execute('SELECT user_id FROM users WHERE status = 1').fetchall()
        conn.close()
        with open("alive_users.txt", "w") as f:
            for u in users: f.write(f"{u[0]}\n")
        await callback.message.answer_document(types.FSInputFile("alive_users.txt"), caption="📄 Список ID живых юзеров")
    elif callback.data == "admin_broadcast_start":
        admin_state[callback.from_user.id] = "wait_text"
        await callback.message.answer("📝 Введи текст рассылки (или 'отмена'):")
    await callback.answer()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(f"👋 Привет! Пришли текст для озвучки.\n💡 Используй **+** для ударения.")

@dp.message(F.text)
async def handle_all_messages(message: types.Message):
    uid = message.from_user.id
    
    # Логика рассылки
    if uid == ADMIN_ID and admin_state.get(uid) == "wait_text":
        if message.text.lower() == "отмена":
            admin_state.pop(uid); return await message.answer("Отменено.")
        admin_state.pop(uid)
        conn = sqlite3.connect(DB_PATH); all_u = conn.execute('SELECT user_id FROM users').fetchall(); conn.close()
        st_msg = await message.answer("🚀 Рассылка пошла...")
        done = 0
        for (u_id,) in all_u:
            try:
                await bot.send_message(u_id, message.text)
                set_user_status(u_id, 1); done += 1
                await asyncio.sleep(0.05)
            except: set_user_status(u_id, 0)
        return await st_msg.edit_text(f"✅ Готово. Получили: {done}")

    if message.text.startswith("/"): return
    if not await check_sub(uid):
        kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="Подписаться", url=CHANNEL_URL))
        return await message.answer("❌ Подпишись на канал!", reply_markup=kb.as_markup())

    add_user(uid)
    user_sessions[uid] = {"text": message.text}
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="Поддержать ⭐️", callback_data="donate_menu"))
    await message.answer("Выбери голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    user_sessions[callback.from_user.id]["voice"] = callback.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Обычный", callback_data="m_natural"),
           types.InlineKeyboardButton(text="Медленно", callback_data="m_slow"),
           types.InlineKeyboardButton(text="Быстро", callback_data="m_fast"))
    await callback.message.edit_text("Скорость:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_sessions: return
    data = user_sessions[uid]
    status = await callback.message.edit_text("⌛ Озвучиваю...")
    try:
        fid = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        await callback.message.answer_audio(types.FSInputFile(os.path.join(BASE_DIR, "static/audio", fid)))
        await status.delete()
    except Exception as e: await callback.message.answer(f"❌ Ошибка: {e}")

# --- САЙТ МАРШРУТЫ ---
@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    try:
        res = await asyncio.wait_for(asyncio.to_thread(model_ai.generate_content, request.message), timeout=10.0)
        return {"reply": res.text if res else "..."}
    except: return {"reply": "Ошибка."}

@app.post("/api/generate")
async def generate(request: TTSRequest):
    fid = await generate_speech_logic(request.text, request.voice, request.mode)
    return {"audio_url": f"/static/audio/{fid}"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-audio/{f}")
async def get_audio(f: str): return FileResponse(os.path.join(BASE_DIR, "static/audio", f))

@app.get("/blog")
async def blog_index(request: Request): return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{p}")
async def blog_post(request: Request, p: str): return templates.TemplateResponse(f"blog/{p}.html", {"request": request})

@app.get("/{p}")
async def other_p(request: Request, p: str):
    try: return templates.TemplateResponse(f"{p}.html", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    if not os.environ.get("BOT_RUNNING"):
        os.environ["BOT_RUNNING"] = "true"
        await bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(dp.start_polling(bot))




















