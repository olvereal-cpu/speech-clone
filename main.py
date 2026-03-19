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
from aiogram.types import (
    FSInputFile, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- ИСПРАВЛЕННАЯ РАБОТА С БАЗОЙ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT 'ru-RU-DmitryNeural')''  )
    # Таблица каналов (исправлен синтаксис SQLite)
    cursor.execute('''CREATE TABLE IF NOT EXISTS channels 
                      (chat_id TEXT PRIMARY KEY, link TEXT)''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def update_user_voice(user_id, voice):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET voice = ? WHERE user_id = ?', (voice, user_id))
    conn.commit()
    conn.close()

def get_user_voice(user_id):
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return res[0] if res else 'ru-RU-DmitryNeural'

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    return [r[0] for r in res]

def add_channel(chat_id, link):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO channels (chat_id, link) VALUES (?, ?)', (chat_id, link))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT chat_id, link FROM channels').fetchall()
    conn.close()
    return res

def clear_channels_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM channels')
    conn.commit()
    conn.close()

# --- FASTAPI ---
app = FastAPI()

# Создаем папки при старте
for p in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, p), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatMsg(BaseModel): message: str
class TTSReq(BaseModel): text: str; voice: str; mode: str = "natural"

@app.post("/api/chat")
async def api_chat(r: ChatMsg):
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=r.message)
    return {"reply": resp.text}

@app.post("/api/generate")
async def api_gen(r: TTSReq):
    f_id = f"{uuid.uuid4()}.mp3"
    f_path = os.path.join(BASE_DIR, f"static/audio/{f_id}")
    await edge_tts.Communicate(r.text, r.voice).save(f_path)
    return {"audio_url": f"/static/audio/{f_id}"}

# Роуты (убедись, что файлы есть в templates)
@app.get("/", response_class=HTMLResponse)
async def h(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/{page}", response_class=HTMLResponse)
async def pgs(request: Request, page: str):
    # Универсальный роут для about, privacy, contacts и т.д.
    f = f"{page}.html" if not page.endswith(".html") else page
    return templates.TemplateResponse(f, {"request": request})

@app.get("/blog/{p}", response_class=HTMLResponse)
async def blg(request: Request, p: str):
    f = f"blog/{p if p.endswith('.html') else p+'.html'}"
    return templates.TemplateResponse(f, {"request": request})

# --- БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

VOICE_DATA = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural", "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural", "Sonia 🇬🇧": "en-GB-SoniaNeural", "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Denise 🇫🇷": "fr-FR-DeniseNeural", "Nanami 🇯🇵": "ja-JP-NanamiNeural"
}

def m_kb():
    b = [[KeyboardButton(text=k) for k in list(VOICE_DATA.keys())[i:i+3]] for i in range(0, 9, 3)]
    b.append([KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Каналы")])
    return ReplyKeyboardMarkup(keyboard=b, resize_keyboard=True)

async def check_sub(u_id):
    ch = get_channels()
    to_sub = []
    for cid, link in ch:
        try:
            m = await bot.get_chat_member(cid, u_id)
            if m.status in ["left", "kicked"]: to_sub.append(link)
        except: to_sub.append(link)
    return to_sub

@dp.message(Command("start"))
async def st(m: types.Message):
    add_user(m.from_user.id)
    await m.answer("🎙 Выбери голос и пришли текст.", reply_markup=m_kb())

@dp.message(F.text.in_(VOICE_DATA.keys()))
async def sv(m: types.Message):
    update_user_voice(m.from_user.id, VOICE_DATA[m.text])
    await m.answer(f"✅ Выбран голос: {m.text}")

@dp.message(Command("add_chan"))
async def ac(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        p = m.text.split()
        if len(p) == 3: add_channel(p[1], p[2]); await m.answer("✅ Канал добавлен")

@dp.message(F.text)
async def tts(m: types.Message):
    if m.text in VOICE_DATA or m.from_user.id == ADMIN_ID and m.text in ["📊 Статистика", "⚙️ Каналы"]: return
    
    unsub = await check_sub(m.from_user.id)
    if unsub:
        ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Подписаться", url=l)] for l in unsub])
        return await m.answer("❌ Подпишись для работы:", reply_markup=ikb)

    w = await m.answer("⏳ Генерирую...")
    try:
        v = get_user_voice(m.from_user.id)
        f_id = f"{uuid.uuid4()}.mp3"
        f_path = os.path.join(BASE_DIR, f"static/audio/{f_id}")
        await edge_tts.Communicate(m.text, v).save(f_path)
        
        skb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Поделиться", switch_inline_query="Классный бот!")]])
        await m.answer_voice(FSInputFile(f_path), caption="🎙 @speechclone", reply_markup=skb)
        await w.delete()
    except: await m.answer("Ошибка")

@app.on_event("startup")
async def start_app():
    init_db()
    asyncio.create_task(dp.start_polling(bot))









