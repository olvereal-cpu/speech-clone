import os
import uuid
import asyncio
import sqlite3
import edge_tts
from google import genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Юзеры
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT 'ru-RU-DmitryNeural')''')
    # Каналы для подписки
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels 
                      (id INTEGER PRIMARY KEY AUTO_INCREMENT, chat_id TEXT, link TEXT)''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT chat_id, link FROM channels').fetchall()
    conn.close()
    return res

def add_channel(chat_id, link):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT INTO channels (chat_id, link) VALUES (?, ?)', (chat_id, link))
    conn.commit()
    conn.close()

def delete_channels():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM channels')
    conn.commit()
    conn.close()

# --- FASTAPI ---
app = FastAPI()
for p in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, p), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.post("/api/chat")
async def chat_api(r: BaseModel):
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=r.message)
    return {"reply": resp.text}

@app.get("/")
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})
# ... (остальные роуты /about, /privacy и т.д. остаются без изменений)

# --- ТЕЛЕГРАМ БОТ С ПРОВЕРКОЙ ПОДПИСКИ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

VOICE_DATA = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural", "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural", "Sonia 🇬🇧": "en-GB-SoniaNeural", "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Denise 🇫🇷": "fr-FR-DeniseNeural", "Nanami 🇯🇵": "ja-JP-NanamiNeural"
}

def main_kb():
    btns = [[KeyboardButton(text=k) for k in list(VOICE_DATA.keys())[i:i+3]] for i in range(0, 9, 3)]
    btns.append([KeyboardButton(text="Даулет 🇰🇿"), KeyboardButton(text="Айгуль 🇰🇿")])
    btns.append([KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Каналы")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

async def check_sub(user_id):
    channels = get_channels()
    unsub = []
    for chat_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ["left", "kicked"]: unsub.append(link)
        except: unsub.append(link)
    return unsub

@dp.message(Command("start"))
async def start(m: types.Message):
    add_user(m.from_user.id)
    await m.answer("🎙 Добро пожаловать! Выбери голос и пришли текст.", reply_markup=main_kb())

@dp.message(F.text == "⚙️ Каналы")
async def channel_mgmt(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("Чтобы добавить канал, пиши:\n`/add_chan -100123 link`\nЧтобы очистить список: `/clear_chan`")

@dp.message(Command("add_chan"))
async def add_chan_cmd(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.split()
    if len(parts) == 3:
        add_channel(parts[1], parts[2])
        await m.answer("✅ Канал добавлен")

@dp.message(Command("clear_chan"))
async def clear_chan_cmd(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    delete_channels(); await m.answer("🗑 Список каналов пуст")

@dp.message(F.text)
async def handle_all(m: types.Message):
    if m.text in VOICE_DATA:
        # Обновление голоса в БД (логика из прошлого шага)
        return

    # ПРОВЕРКА ПОДПИСКИ
    not_subbed = await check_sub(m.from_user.id)
    if not_subbed:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Подписаться", url=l)] for l in not_subbed])
        return await m.answer("❌ Чтобы использовать бота, подпишись на наши каналы:", reply_markup=kb)

    # ОЗВУЧКА
    wait = await m.answer("⏳ Генерирую...")
    # ... (логика edge_tts как в прошлом коде)
    await wait.delete()

@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(dp.start_polling(bot))









