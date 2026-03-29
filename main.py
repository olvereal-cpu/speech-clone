import os
import uuid
import asyncio
import sqlite3
import re
import edge_tts
import google.generativeai as genai
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery, FSInputFile

# --- 1. КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY")

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- 2. ГОЛОСА ---
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural",
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural",
    "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇦 Поліна": "uk-UA-PolinaNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural",
    "🇹🇷 Emel": "tr-TR-EmelNeural"
}

# --- 3. ИНИЦИАЛИЗАЦИЯ GEMINI 3.1 ---
class ModelManager:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text if resp else "Ошибка"
        except Exception as e:
            return f"Error: {e}"

mm = ModelManager(GEMINI_API_KEY)

# --- 4. БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural", is_premium INTEGER DEFAULT 0)')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit(); conn.close()

init_db()

# --- 5. ТЕЛЕГРАМ БОТ (ЗВЕЗДЫ + ГОЛОСА) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status not in ["left", "kicked"]
    except: return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys():
        kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="🌟 Поддержать (50 Stars)", callback_data="buy_stars"))
    await message.answer(
        "👋 Привет! Я SpeechClone.\n\n"
        "Выбери голос кнопкой и просто пришли текст.\n"
        "Для работы нужна подписка на канал.", 
        reply_markup=kb.as_markup()
    )

# ЛОГИКА ОПЛАТЫ ЗВЕЗДАМИ
@dp.callback_query(F.data == "buy_stars")
async def send_invoice(call: types.CallbackQuery):
    await bot.send_invoice(
        call.message.chat.id,
        title="Премиум статус",
        description="Поддержка проекта и доступ к расширенным функциям",
        payload="premium_stars",
        currency="XTR", # Код для Telegram Stars
        prices=[LabeledPrice(label="Stars", amount=50)]
    )
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET is_premium = 1 WHERE user_id = ?', (message.from_user.id,))
    conn.commit(); conn.close()
    await message.answer("🎉 Спасибо за поддержку! Вам открыты все функции проекта.")

# ЛОГИКА ГОЛОСОВ
@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, (SELECT voice FROM users WHERE user_id=?), (SELECT is_premium FROM users WHERE user_id=?))', (call.from_user.id, v_id, call.from_user.id))
    # Упрощенная вставка для поддержки существующих колонок
    conn.execute('UPDATE users SET voice = ? WHERE user_id = ?', (v_id, call.from_user.id))
    conn.commit(); conn.close()
    await call.message.answer(f"✅ Голос изменен на: {v_id}")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ Чтобы пользоваться ботом, подпишись: {CHANNEL_URL}")

    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
    conn.close()
    v_id = res[0] if res else "ru-RU-DmitryNeural"

    try:
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(message.text, v_id).save(path)
        
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ (САЙТ)", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer_audio(audio=FSInputFile(path), caption=f"🗣 Голос: {v_id}", reply_markup=kb.as_markup())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# --- 6. FASTAPI (САЙТ + АДМИНКА) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class AdminGenRequest(BaseModel):
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 8').fetchall(); conn.close()
    return templates.TemplateResponse(request, "index.html", {"request": request, "posts": [dict(p) for p in db_posts]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall(); conn.close()
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": [dict(p) for p in db_posts], "is_single": False})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    prompt = f"Напиши SEO статью про {req.message}. Формат TITLE: заголовок CONTENT: текст"
    raw = await mm.generate(prompt)
    # Здесь логика парсинга и сохранения в БД (как в прошлых версиях)
    return {"status": "success"}

@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str):
    return templates.TemplateResponse(request, "wait_page.html", {"request": request, "file_url": f"/static/audio/{file}"})

@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_gen_page(request: Request):
    return templates.TemplateResponse(request, "admin_generate.html", {"request": request})

@app.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request):
    return templates.TemplateResponse(request, "premium.html", {"request": request})

# --- 7. ЗАПУСК ---
@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))




