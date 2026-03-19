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
from pydantic import BaseModel
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

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural", stars INTEGER DEFAULT 0)')
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

@app.get("/health")
async def health(): return {"status": "alive"}

# --- РОУТЫ ВСЕХ СТРАНИЦ МЕНЮ ---
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

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer(request: Request): return templates.TemplateResponse("disclaimer.html", {"request": request})

# 4 ПУНКТА ДОНАТА (Звезды и обычные)
@app.get("/donate", response_class=HTMLResponse)
async def donate(request: Request): 
    return templates.TemplateResponse("donate.html", {
        "request": request,
        "items": [
            {"id": "support", "name": "Поддержка проекта", "price": "Любая сумма"},
            {"id": "vip", "name": "VIP-статус (Без ОП)", "price": "500 Stars"},
            {"id": "limits", "name": "Снятие лимитов", "price": "200 Stars"},
            {"id": "stars_pack", "name": "Пакет Звезд (100 шт)", "price": "150 Stars"}
        ]
    })

@app.get("/download-page", response_class=HTMLResponse)
async def download_pg(request: Request):
    f = request.query_params.get('file')
    return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{f}" if f else "#"})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def blog_post(request: Request, post_name: str):
    file_path = post_name if post_name.endswith(".html") else f"{post_name}.html"
    try: return templates.TemplateResponse(f"blog/{file_path}", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

# --- ТЕЛЕГРАМ БОТ (СО ЗВЕЗДАМИ) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

VOICES = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural", "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural", "Sonia 🇬🇧": "en-GB-SoniaNeural", "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Denise 🇫🇷": "fr-FR-DeniseNeural", "Nanami 🇯🇵": "ja-JP-NanamiNeural", "Keita 🇯🇵": "ja-JP-KeitaNeural",
    "Xiaoxiao 🇨🇳": "zh-CN-XiaoxiaoNeural", "Gul 🇹🇷": "tr-TR-GulNeural", "Zariyah 🇦🇪": "ar-EG-SalmaNeural"
}

def m_kb(u_id):
    v_keys = list(VOICES.keys())
    btns = [[KeyboardButton(text=v_keys[i]), KeyboardButton(text=v_keys[i+1]), KeyboardButton(text=v_keys[i+2])] for i in range(0, 9, 3)]
    btns.append([KeyboardButton(text="⭐ Купить Звезды"), KeyboardButton(text="💎 VIP Доступ")])
    if u_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Каналы"), KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

# Обработка платежа (Звезды)
@dp.message(F.text == "⭐ Купить Звезды")
async def buy_stars(m: types.Message):
    await m.answer_invoice(
        title="Пополнение баланса (Звезды)",
        description="100 Звезд для использования расширенных функций бота.",
        payload="stars_pack_100",
        currency="XTR", # Код для Telegram Stars
        prices=[LabeledPrice(label="100 Stars", amount=100)]
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    db_query("UPDATE users SET stars = stars + 100 WHERE user_id = ?", (m.from_user.id,))
    await m.answer("✅ Оплата прошла успешно! 100 Звезд зачислены.")

# Остальная логика (Старт, ОП, Озвучка)
@dp.message(Command("start"))
async def st(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,))
    await m.answer("🎙 **SpeechClone Системa**\nВыбери голос и пришли текст.", reply_markup=m_kb(m.from_user.id))

@dp.message(F.text.in_(VOICES.keys()))
async def sv(m: types.Message):
    db_query("UPDATE users SET voice = ? WHERE user_id = ?", (VOICES[m.text], m.from_user.id))
    await m.answer(f"✅ Голос: {m.text}")

@dp.message(F.text)
async def tts_logic(m: types.Message):
    if m.text in VOICES or m.text in ["📊 Статистика", "⚙️ Каналы", "📢 Рассылка", "⭐ Купить Звезды", "💎 VIP Доступ"]: return
    
    # Проверка подписки (ОП)
    ch = db_query("SELECT chat_id, link FROM channels", fetch=True)
    unsub = []
    for cid, link in ch:
        try:
            member = await bot.get_chat_member(cid, m.from_user.id)
            if member.status in ["left", "kicked"]: unsub.append(link)
        except: unsub.append(link)
    
    if unsub:
        ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 Подписаться", url=l)] for l in unsub])
        return await m.answer("❌ Подпишись для доступа:", reply_markup=ikb)

    w = await m.answer("⏳ Генерирую...")
    try:
        res = db_query("SELECT voice FROM users WHERE user_id = ?", (m.from_user.id,), fetch=True)
        v = res[0][0] if res else "ru-RU-DmitryNeural"
        f_id = f"{uuid.uuid4()}.mp3"
        f_path = os.path.join(BASE_DIR, "static/audio", f_id)
        await edge_tts.Communicate(m.text, v).save(f_path)
        await m.answer_voice(FSInputFile(f_path), caption="🎙 @speechclone")
        await w.delete()
    except: await m.answer("Ошибка озвучки")

# --- АДМИНКА ---
@dp.message(F.text == "📊 Статистика")
async def stats(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        r = db_query("SELECT COUNT(*) FROM users", fetch=True)
        await m.answer(f"👥 Пользователей: {r[0][0]}")

@dp.message(Command("send"))
async def broadcast(m: types.Message, command: CommandObject):
    if m.from_user.id == ADMIN_ID and command.args:
        users = db_query("SELECT user_id FROM users", fetch=True)
        for u in users:
            try: await bot.send_message(u[0], command.args)
            except: pass
        await m.answer("✅ Разослано")

# --- ЗАПУСК ---
async def keep_alive():
    url = "https://speechclone.online/health"
    async with httpx.AsyncClient() as client:
        while True:
            try: await client.get(url)
            except: pass
            await asyncio.sleep(600)

@app.on_event("startup")
async def on_start():
    init_db()
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(keep_alive())








