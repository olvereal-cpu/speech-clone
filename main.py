import os
import uuid
import asyncio
import sqlite3
import edge_tts
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
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"

# ПОЛНЫЙ СПИСОК ГОЛОСОВ (включая новые)
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural",
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет (KZ)": "kk-KZ-DauletNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural",
    "🇺🇦 Остап (UA)": "uk-UA-OstapNeural",
    "🇹🇷 Ahmet (TR)": "tr-TR-AhmetNeural",
    "🇪🇸 Alvaro (ES)": "es-ES-AlvaroNeural",
    "🇩🇪 Conrad (DE)": "de-DE-ConradNeural",
    "🇵🇱 Marek (PL)": "pl-PL-MarekNeural",
    "🇫🇷 Remy (FR)": "fr-FR-RemyNeural",
    "🇯🇵 Keita (JP)": "ja-JP-KeitaNeural",
    "🇨🇳 Yunxi (CN)": "zh-CN-YunxiNeural"
}

# --- ПУТИ И БД ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static/audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.commit()
    conn.close()

def add_user(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (uid,))
    conn.commit()
    conn.close()

init_db()

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status not in ["left", "kicked"]
    except: return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys():
        kb.button(text=name, callback_data=f"v_{name}")
    kb.button(text="⭐ Поддержать (50 Stars)", callback_data="donate_stars")
    kb.adjust(2)
    await message.answer("👋 Привет! Выбери язык озвучки и пришли текст. Не забудь подписаться на канал!", reply_markup=kb.as_markup())

# --- ДОНАТЫ (ЗВЕЗДЫ) ---
@dp.callback_query(F.data == "donate_stars")
async def process_donate(call: types.CallbackQuery):
    await bot.send_invoice(
        call.from_user.id,
        title="Поддержка проекта",
        description="Донат 50 звезд на развитие Speech Clone",
        payload="stars_donate",
        currency="XTR",
        prices=[types.LabeledPrice(label="Звезды", amount=50)]
    )
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    await message.answer(f"📊 Всего пользователей: {count}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID or not command.args: return
    conn = sqlite3.connect(DB_PATH)
    users = [row[0] for row in conn.execute('SELECT user_id FROM users').fetchall()]
    conn.close()
    done = 0
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            done += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена: {done}/{len(users)}")

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_name = call.data.replace("v_", "")
    v_id = VOICES.get(v_name, "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET voice = ? WHERE user_id = ?', (v_id, call.from_user.id))
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Выбран голос: {v_name}")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться", url=CHANNEL_URL))
        return await message.answer("⚠️ Озвучка доступна только подписчикам канала!", reply_markup=kb.as_markup())

    add_user(uid)
    msg = await message.answer("⏳ Генерирую...")
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (uid,)).fetchone()
        v_id = res[0] if res else "ru-RU-DmitryNeural"
        conn.close()

        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        comm = edge_tts.Communicate(message.text, v_id)
        await comm.save(path)
        await message.answer_voice(voice=types.FSInputFile(path))
        await msg.delete()
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# --- FASTAPI (САЙТ) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str; voice: str; mode: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/blog", response_class=HTMLResponse)
async def blog_page(request: Request):
    return templates.TemplateResponse(request=request, name="blog.html")

@app.post("/api/generate")
async def generate(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        comm = edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%"))
        await comm.save(path)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))
