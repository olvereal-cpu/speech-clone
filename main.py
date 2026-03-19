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
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  # Твой ID
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, 
                       voice TEXT DEFAULT 'ru-RU-DmitryNeural', 
                       join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def update_user_voice(user_id, voice):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET voice = ? WHERE user_id = ?', (voice, user_id))
    conn.commit()
    conn.close()

def get_user_voice(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    res = cursor.execute('SELECT voice FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return res[0] if res else 'ru-RU-DmitryNeural'

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    return [r[0] for r in res]

# --- ИНИЦИАЛИЗАЦИЯ FASTAPI ---
app = FastAPI()

# Авто-создание структуры папок для корректного деплоя
for folder in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str = "natural"

# --- API ЭНДПОИНТЫ ---
@app.post("/api/chat")
async def chat_api(request: ChatRequest):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=request.message)
        return {"reply": response.text}
    except:
        return {"reply": "Бро, Спич-Бро временно в раздумьях. Загляни чуть позже!"}

@app.post("/api/generate")
async def gen_api(request: TTSRequest):
    try:
        f_id = f"{uuid.uuid4()}.mp3"
        f_path = os.path.join(BASE_DIR, "static/audio", f_id)
        rates = {"natural": "+0%", "slow": "-15%", "fast": "+15%"}
        communicate = edge_tts.Communicate(request.text, request.voice, rate=rates.get(request.mode, "+0%"))
        await communicate.save(f_path)
        return {"audio_url": f"/static/audio/{f_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ВСЕ РОУТЫ САЙТА (ПОЛНЫЙ СПИСОК) ---
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
async def download_pg(request: Request):
    file_name = request.query_params.get('file')
    file_url = f"/static/audio/{file_name}" if file_name else "#"
    return templates.TemplateResponse("download.html", {"request": request, "file_url": file_url})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def blog_post(request: Request, post_name: str):
    f = post_name if post_name.endswith(".html") else f"{post_name}.html"
    return templates.TemplateResponse(f"blog/{f}", {"request": request})

# --- ТЕЛЕГРАМ БОТ (РАСШИРЕННЫЙ) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Словарь всех доступных голосов (Никита вместо Юрия)
VOICE_DATA = {
    "Дмитрий 🇷🇺": "ru-RU-DmitryNeural",
    "Светлана 🇷🇺": "ru-RU-SvetlanaNeural",
    "Никита 🇷🇺": "ru-RU-NikitaNeural",
    "Даулет 🇰🇿": "kk-KZ-DauletNeural",
    "Айгуль 🇰🇿": "kk-KZ-AigulNeural",
    "Ava 🇺🇸": "en-US-AvaNeural",
    "Andrew 🇺🇸": "en-US-AndrewNeural",
    "Sonia 🇬🇧": "en-GB-SoniaNeural",
    "Katja 🇩🇪": "de-DE-KatjaNeural",
    "Denise 🇫🇷": "fr-FR-DeniseNeural",
    "Nanami 🇯🇵": "ja-JP-NanamiNeural"
}

def main_kb():
    buttons = [
        [KeyboardButton(text="Дмитрий 🇷🇺"), KeyboardButton(text="Светлана 🇷🇺"), KeyboardButton(text="Никита 🇷🇺")],
        [KeyboardButton(text="Даулет 🇰🇿"), KeyboardButton(text="Айгуль 🇰🇿")],
        [KeyboardButton(text="Ava 🇺🇸"), KeyboardButton(text="Andrew 🇺🇸"), KeyboardButton(text="Sonia 🇬🇧")],
        [KeyboardButton(text="Katja 🇩🇪"), KeyboardButton(text="Denise 🇫🇷"), KeyboardButton(text="Nanami 🇯🇵")],
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📢 Рассылка")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    add_user(m.from_user.id)
    await m.answer("🎙 **SpeechClone Системa**\n\nВыбери голос кнопкой ниже и пришли текст для озвучки.", reply_markup=main_kb())

@dp.message(F.text.in_(VOICE_DATA.keys()))
async def set_voice(m: types.Message):
    update_user_voice(m.from_user.id, VOICE_DATA[m.text])
    await m.answer(f"✅ Теперь я говорю как: **{m.text}**")

@dp.message(F.text == "📊 Статистика")
async def admin_stats(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        users = get_all_users()
        await m.answer(f"👥 Всего в базе: {len(users)} пользователей.")

@dp.message(F.text == "📢 Рассылка")
async def ask_broadcast(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("Напиши `/send Твой текст` для массовой рассылки.")

@dp.message(Command("send"))
async def do_broadcast(m: types.Message):
    if m.from_user.id == ADMIN_ID:
        msg_text = m.text.replace("/send", "").strip()
        if not msg_text: return await m.answer("Ошибка: пустое сообщение.")
        users = get_all_users()
        count = 0
        for u_id in users:
            try:
                await bot.send_message(u_id, msg_text)
                count += 1
                await asyncio.sleep(0.05) 
            except: pass
        await m.answer(f"✅ Рассылка завершена. Доставлено: {count}.")

@dp.message(F.text)
async def tts_bot_handler(m: types.Message):
    # Пропускаем системные кнопки
    if m.text in VOICE_DATA or m.text in ["📊 Статистика", "📢 Рассылка"]: return
    
    wait_msg = await m.answer("⏳ Озвучиваю...")
    try:
        user_voice = get_user_voice(m.from_user.id)
        f_id = f"{uuid.uuid4()}.mp3"
        f_path = os.path.join(BASE_DIR, "static/audio", f_id)
        
        await edge_tts.Communicate(m.text, user_voice).save(f_path)
        
        # Находим имя для подписи
        current_voice_name = next((k for k, v in VOICE_DATA.items() if v == user_voice), "Стандартный")
        
        await m.answer_voice(FSInputFile(f_path), caption=f"🎙 Голос: {current_voice_name}\nСделано в @speechclone")
        await wait_msg.delete()
    except Exception as e:
        await m.answer("❌ Ошибка озвучки. Попробуй другой текст.")

# --- ЗАПУСК ---
@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(dp.start_polling(bot))









