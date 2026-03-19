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
    InlineKeyboardMarkup, InlineKeyboardButton
)

# Логи для мониторинга в панели Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- БАЗА ДАННЫХ (БЕЗ КОНФЛИКТОВ ПОТОКОВ) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
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

for folder in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Роут для Крона и Рендера
@app.get("/health")
async def health(): 
    return {"status": "alive", "msg": "Ready for ads"}

# Внутренний "будильник" (самопинг)
async def keep_alive_task():
    url = "https://speechclone.online/health"
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(url)
                logger.info("Self-ping: Service is awake.")
            except Exception as e:
                logger.error(f"Self-ping failed: {e}")
            await asyncio.sleep(600) # 10 минут

# API
class ChatMsg(BaseModel): message: str
class TTSReq(BaseModel): text: str; voice: str

@app.post("/api/chat")
async def api_chat(r: ChatMsg):
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=r.message)
    return {"reply": resp.text}

@app.post("/api/generate")
async def api_gen(r: TTSReq):
    f_id = f"{uuid.uuid4()}.mp3"
    f_path = os.path.join(BASE_DIR, "static/audio", f_id)
    await edge_tts.Communicate(r.text, r.voice).save(f_path)
    return {"audio_url": f"/static/audio/{f_id}"}

# Роуты сайта (7+ страниц)
@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/{page}", response_class=HTMLResponse)
async def all_pages(request: Request, page: str):
    if page == "favicon.ico": return JSONResponse({"status": "skip"})
    f = page if page.endswith(".html") else f"{page}.html"
    try: return templates.TemplateResponse(f, {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

VOICES = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural", "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural", "Sonia 🇬🇧": "en-GB-SoniaNeural", "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Denise 🇫🇷": "fr-FR-DeniseNeural", "Nanami 🇯🇵": "ja-JP-NanamiNeural", "Keita 🇯🇵": "ja-JP-KeitaNeural",
    "Xiaoxiao 🇨🇳": "zh-CN-XiaoxiaoNeural", "Gul 🇹🇷": "tr-TR-GulNeural"
}

def m_kb(u_id):
    v_keys = list(VOICES.keys())
    btns = [[KeyboardButton(text=v_keys[i]), KeyboardButton(text=v_keys[i+1]), KeyboardButton(text=v_keys[i+2])] for i in range(0, 9, 3)]
    btns.append([KeyboardButton(text="Даулет 🇰🇿"), KeyboardButton(text="Айгуль 🇰🇿")])
    if u_id == ADMIN_ID:
        btns.append([KeyboardButton(text="📊 Статистика"), KeyboardButton(text="⚙️ Каналы"), KeyboardButton(text="📢 Рассылка")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

async def check_sub(u_id):
    ch = db_query("SELECT chat_id, link FROM channels", fetch=True)
    unsub = []
    for cid, link in ch:
        try:
            m = await bot.get_chat_member(cid, u_id)
            if m.status in ["left", "kicked"]: unsub.append(link)
        except: unsub.append(link)
    return unsub

@dp.message(Command("start"))
async def st(m: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,))
    await m.answer("🎙 **SpeechClone Системa**\nВыбери голос и пришли текст.", reply_markup=m_kb(m.from_user.id))

# Админка
@dp.message(F.text == "📊 Статистика")
async def stats(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        r = db_query("SELECT COUNT(*) FROM users", fetch=True)
        await m.answer(f"👥 Пользователей: {r[0][0]}")

@dp.message(Command("send"))
async def broadcast(m: types.Message, command: CommandObject):
    if m.from_user.id == ADMIN_ID and command.args:
        users = db_query("SELECT user_id FROM users", fetch=True)
        c = 0
        for u in users:
            try:
                await bot.send_message(u[0], command.args)
                c += 1
                await asyncio.sleep(0.05)
            except: pass
        await m.answer(f"✅ Разослано: {c}")

@dp.message(Command("add_chan"))
async def add_c(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        p = m.text.split()
        if len(p) == 3:
            db_query("INSERT OR REPLACE INTO channels (chat_id, link) VALUES (?, ?)", (p[1], p[2]))
            await m.answer("✅ Канал добавлен")

@dp.message(Command("clear_chan"))
async def cl_c(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        db_query("DELETE FROM channels")
        await m.answer("🗑 Каналы очищены")

# Озвучка
@dp.message(F.text.in_(VOICES.keys()))
async def sv(m: types.Message):
    db_query("UPDATE users SET voice = ? WHERE user_id = ?", (VOICES[m.text], m.from_user.id))
    await m.answer(f"✅ Голос: {m.text}")

@dp.message(F.text)
async def tts_logic(m: types.Message):
    if m.text in VOICES or (m.from_user.id == ADMIN_ID and m.text in ["📊 Статистика", "⚙️ Каналы", "📢 Рассылка"]): return
    unsub = await check_sub(m.from_user.id)
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
        skb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Поделиться", switch_inline_query="Зацени бота!")]])
        await m.answer_voice(FSInputFile(f_path), caption="🎙 @speechclone", reply_markup=skb)
        await w.delete()
    except: await m.answer("Ошибка озвучки")

@app.on_event("startup")
async def on_start():
    init_db()
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(keep_alive_task()) # Защита от сна








