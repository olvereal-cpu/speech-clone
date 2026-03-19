import os
import uuid
import asyncio
import sqlite3
import logging
import httpx
import edge_tts
from google import genai
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    FSInputFile, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- ОБНОВЛЕННАЯ БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Таблица пользователей с поддержкой баланса Звёзд (stars)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, 
                       voice TEXT DEFAULT "ru-RU-DmitryNeural", 
                       stars INTEGER DEFAULT 0,
                       is_vip INTEGER DEFAULT 0)''')
    # Таблица каналов для обязательной подписки
    cursor.execute('CREATE TABLE IF NOT EXISTS channels (chat_id TEXT PRIMARY KEY, link TEXT)')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.execute(query, params)
    res = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

# --- FASTAPI ---
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Все 8 роутов меню + Блог
@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request): return templates.TemplateResponse("about.html", {"request": request})

@app.get("/services", response_class=HTMLResponse)
async def services(request: Request): return templates.TemplateResponse("services.html", {"request": request})

@app.get("/contacts", response_class=HTMLResponse)
async def contacts(request: Request): return templates.TemplateResponse("contacts.html", {"request": request})

@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request): return templates.TemplateResponse("faq.html", {"request": request})

@app.get("/api-docs", response_class=HTMLResponse)
async def api_docs(request: Request): return templates.TemplateResponse("api.html", {"request": request})

@app.get("/donate", response_class=HTMLResponse)
async def donate(request: Request): return templates.TemplateResponse("donate.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def blog_post(request: Request, post_name: str):
    f = post_name if post_name.endswith(".html") else f"{post_name}.html"
    try: return templates.TemplateResponse(f"blog/{f}", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

VOICES = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", 
    "Ava 🇺🇸": "en-US-AvaNeural", "Sonia 🇬🇧": "en-GB-SoniaNeural", 
    "Katja 🇩🇪": "de-DE-KatjaNeural", "Denise 🇫🇷": "fr-FR-DeniseNeural", 
    "Nanami 🇯🇵": "ja-JP-NanamiNeural", "Gul 🇹🇷": "tr-TR-GulNeural"
}

def m_kb(u_id):
    btns = [[KeyboardButton(text=k)] for k in VOICES.keys()]
    btns.append([KeyboardButton(text="⭐ Купить Звезды"), KeyboardButton(text="💎 VIP Статус")])
    if u_id == ADMIN_ID: btns.append([KeyboardButton(text="📊 Стат"), KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# Платежи Stars
@dp.message(F.text == "⭐ Купить Звезды")
async def buy_stars(m: types.Message):
    await m.answer_invoice(title="100 Stars", description="Пополнение баланса", payload="stars_100", currency="XTR", prices=[LabeledPrice(label="XTR", amount=100)])

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    db_query("UPDATE users SET stars = stars + 100 WHERE user_id = ?", (m.from_user.id,))
    await m.answer("✅ Баланс пополнен!")

@dp.message(Command("start"))
async def st(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,))
    await m.answer("🎙 SpeechClone: Пришли текст для озвучки.", reply_markup=m_kb(m.from_user.id))

@dp.message(F.text)
async def handle_msg(m: types.Message):
    if m.text in VOICES:
        db_query("UPDATE users SET voice = ? WHERE user_id = ?", (VOICES[m.text], m.from_user.id))
        return await m.answer(f"✅ Голос: {m.text}")
    
    # Озвучка (упрощенно)
    res = db_query("SELECT voice FROM users WHERE user_id = ?", (m.from_user.id,), fetch=True)
    v = res[0][0] if res else "ru-RU-DmitryNeural"
    f_path = f"static/audio/{uuid.uuid4()}.mp3"
    await edge_tts.Communicate(m.text, v).save(f_path)
    await m.answer_voice(FSInputFile(f_path))

@app.on_event("startup")
async def on_start():
    init_db()
    asyncio.create_task(dp.start_polling(bot))







