import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"

# --- БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_at DATETIME DEFAULT CURRENT_TIMESTAMP)')
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

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
if GEMINI_API_KEY:
    google.generativeai.configure(api_key=GEMINI_API_KEY)
    model_ai = google.generativeai.GenerativeModel('gemini-1.5-flash')
else:
    model_ai = None

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

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    count = len(get_all_users())
    await message.answer(f"📊 Всего пользователей в базе: {count}")

@dp.message(Command("db"))
async def cmd_db(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if os.path.exists(DB_PATH):
        await message.answer_document(types.FSInputFile(DB_PATH), caption="📦 Бэкап базы данных.")
    else:
        await message.answer("❌ Файл базы данных не найден.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.answer("❌ Введи текст: `/broadcast Привет всем`")
    
    users = get_all_users()
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться на Speech Clone", url=CHANNEL_URL))
        text_sub = (
            "⚠️ **Доступ ограничен**\n\n"
            "Наш проект **полностью бесплатный**, и мы хотим сохранить его таким для всех! 🎁\n\n"
            "Единственное условие — подписка на наш канал. Это помогает нам развиваться.\n\n"
            "Подпишись, и все нейро-голоса станут доступны тебе сразу!"
        )
        return await message.answer(text_sub, reply_markup=kb.as_markup(), parse_mode="Markdown")

    add_user(uid)
    await message.answer("Текст принят! Я Спич-Бро. Если хочешь настроить голос и скачать MP3 — загляни на наш сайт SpeechClone.online!")

# --- FASTAPI САЙТ ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs(os.path.join(BASE_DIR, "static/audio"), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(BASE_DIR, "static/audio", fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        communicate = edge_tts.Communicate(request.text, request.voice, rate=rates.get(request.mode, "+0%"))
        await communicate.save(path)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/chat")
async def chat_api(request: ChatRequest):
    if not model_ai: return {"reply": "ИИ временно недоступен"}
    res = await asyncio.to_thread(model_ai.generate_content, request.message)
    return {"reply": res.text}

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try:
        return templates.TemplateResponse(f"{page}.html", {"request": request})
    except:
        return templates.TemplateResponse("index.html", {"request": request})

# --- ЗАПУСК ---
async def start_services():
    print("🚀 Запуск систем SpeechClone...")
    asyncio.create_task(dp.start_polling(bot))
    
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Остановка сервисов")


