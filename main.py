import os
import uuid
import asyncio
import sqlite3
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

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- СИСТЕМА БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    cursor.execute('CREATE TABLE IF NOT EXISTS channels (chat_id TEXT PRIMARY KEY, link TEXT)')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(query, params)
    res = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return res

# --- FASTAPI ПРИЛОЖЕНИЕ ---
app = FastAPI()

for folder in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/health")
async def health(): return {"status": "alive", "msg": "Working for Oleg"}

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

# --- РОУТЫ САЙТА (БЕЗ УДАЛЕНИЙ) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request): return templates.TemplateResponse("about.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/donate", response_class=HTMLResponse)
async def donate(request: Request): return templates.TemplateResponse("donate.html", {"request": request})

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer(request: Request): return templates.TemplateResponse("disclaimer.html", {"request": request})

@app.get("/contacts", response_class=HTMLResponse)
async def contacts(request: Request): return templates.TemplateResponse("contacts.html", {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def dl_pg(request: Request):
    f = request.query_params.get('file')
    return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{f}" if f else "#"})

@app.get("/blog/{p}", response_class=HTMLResponse)
async def blog_posts(request: Request, p: str):
    f = f"blog/{p if p.endswith('.html') else p + '.html'}"
    return templates.TemplateResponse(f, {"request": request})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# МАКСИМАЛЬНЫЙ СПИСОК ГОЛОСОВ
VOICES = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural", "Светлана 🇷🇺": "ru-RU-SvetlanaNeural", "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural", "Айгуль 🇰🇿": "kk-KZ-AigulNeural", "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural", "Emma 🇺🇸": "en-US-EmmaNeural", "Brian 🇺🇸": "en-US-BrianNeural",
    "Sonia 🇬🇧": "en-GB-SoniaNeural", "Ryan 🇬🇧": "en-GB-RyanNeural", "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Conrad 🇩🇪": "de-DE-ConradNeural", "Denise 🇫🇷": "fr-FR-DeniseNeural", "Henri 🇫🇷": "fr-FR-HenriNeural",
    "Elsa 🇮🇹": "it-IT-ElsaNeural", "Diego 🇮🇹": "it-IT-DiegoNeural", "Alvaro 🇪🇸": "es-ES-AlvaroNeural",
    "Nanami 🇯🇵": "ja-JP-NanamiNeural", "Keita 🇯🇵": "ja-JP-KeitaNeural", "Xiaoxiao 🇨🇳": "zh-CN-XiaoxiaoNeural",
    "Yunxi 🇨🇳": "zh-CN-YunxiNeural", "SunHi 🇰🇷": "ko-KR-SunHiNeural", "Gul 🇹🇷": "tr-TR-GulNeural",
    "Zariyah 🇦🇪": "ar-EG-SalmaNeural"
}

def m_kb(u_id):
    # Формируем кнопки голосов (первые 12 для удобства)
    v_keys = list(VOICES.keys())
    btns = [[KeyboardButton(text=v_keys[i]), KeyboardButton(text=v_keys[i+1]), KeyboardButton(text=v_keys[i+2])] for i in range(0, 12, 3)]
    # Кнопки управления
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

# --- АДМИН-ЛОГИКА ---
@dp.message(F.text == "📊 Статистика")
async def stats(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        r = db_query("SELECT COUNT(*) FROM users", fetch=True)
        await m.answer(f"👥 Пользователей в базе: {r[0][0]}")

@dp.message(F.text == "⚙️ Каналы")
async def chan_adm(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        c = db_query("SELECT chat_id, link FROM channels", fetch=True)
        txt = "Каналы ОП:\n" + "\n".join([f"{i[0]} -> {i[1]}" for i in c])
        await m.answer(f"{txt}\n\n`/add_chan ID LINK` - добавить\n`/clear_chan` - очистить")

@dp.message(Command("send"))
async def broadcast(m: types.Message, command: CommandObject):
    if m.from_user.id == ADMIN_ID and command.args:
        users = db_query("SELECT user_id FROM users", fetch=True)
        count = 0
        for u in users:
            try:
                await bot.send_message(u[0], command.args)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await m.answer(f"✅ Рассылка завершена. Получили: {count}")

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

# --- ОСНОВНОЙ ФУНКЦИОНАЛ ---
@dp.message(F.text.in_(VOICES.keys()))
async def sv(m: types.Message):
    db_query("UPDATE users SET voice = ? WHERE user_id = ?", (VOICES[m.text], m.from_user.id))
    await m.answer(f"✅ Голос изменен на: {m.text}")

@dp.message(F.text)
async def tts_logic(m: types.Message):
    if m.text in VOICES or (m.from_user.id == ADMIN_ID and m.text in ["📊 Статистика", "⚙️ Каналы", "📢 Рассылка"]): return
    
    unsub = await check_sub(m.from_user.id)
    if unsub:
        ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 Подписаться", url=l)] for l in unsub])
        ikb.inline_keyboard.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check")])
        return await m.answer("❌ Сначала подпишись на каналы:", reply_markup=ikb)

    w = await m.answer("⏳ Магия озвучки...")
    try:
        res = db_query("SELECT voice FROM users WHERE user_id = ?", (m.from_user.id,), fetch=True)
        v = res[0][0] if res else "ru-RU-DmitryNeural"
        f_id = f"{uuid.uuid4()}.mp3"
        f_path = os.path.join(BASE_DIR, f"static/audio/{f_id}")
        await edge_tts.Communicate(m.text, v).save(f_path)
        
        skb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Поделиться с друзьями", switch_inline_query="Зацени бота!")]])
        await m.answer_voice(FSInputFile(f_path), caption="🎙 @speechclone", reply_markup=skb)
        await w.delete()
    except: await m.answer("Ошибка озвучки")

@dp.callback_query(F.data == "check")
async def check_cb(call: types.CallbackQuery):
    unsub = await check_sub(call.from_user.id)
    if not unsub:
        await call.message.answer("✅ Спасибо! Доступ открыт.")
    else:
        await call.answer("❌ Ты еще не подписан на всё!", show_alert=True)

@app.on_event("startup")
async def on_start():
    init_db()
    asyncio.create_task(dp.start_polling(bot))









