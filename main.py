import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- ПУТИ И НАСТРОЙКИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")

ADMIN_ID = 430747895
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_URL = "https://t.me/speechclone"
CHANNEL_ID = "@speechclone"

for p in [STATIC_DIR, AUDIO_DIR, TEMPLATES_DIR]:
    os.makedirs(p, exist_ok=True)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (uid,))
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

# --- GEMINI 2.5 FLASH ---
GOOGLE_API_KEY = os.getenv("GEMINI_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
model_ai = genai.GenerativeModel('gemini-2.5-flash')

# --- FastAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(AUDIO_DIR, file_id)
    
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        return re.sub(r'\+([%s])' % vowels, r'\1' + chr(769), t)

    processed_text = fix_stress(text)
    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")

    communicate = edge_tts.Communicate(processed_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_states = {}

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=uid)
        return m.status not in ["left", "kicked"]
    except: return False

@dp.message(Command("start"))
async def start(m: types.Message):
    add_user(m.from_user.id)
    await m.answer(f"Привет, {m.from_user.first_name}! Пришли текст для озвучки.")

@dp.message(Command("export"))
async def export_db(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    users = get_all_users()
    f_path = os.path.join(BASE_DIR, "export.txt")
    with open(f_path, "w") as f: f.write("\n".join(map(str, users)))
    await m.answer_document(types.FSInputFile(f_path), caption=f"Всего: {len(users)}")
    if os.path.exists(f_path): os.remove(f_path)

@dp.message(F.text)
async def handle_text(m: types.Message):
    if m.text.startswith("/"): return
    if m.from_user.id != ADMIN_ID and not await check_sub(m.from_user.id):
        kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="💎 Подписаться", url=CHANNEL_URL))
        return await m.answer("⚠️ Для работы нужна подписка!", reply_markup=kb.as_markup())

    user_states[m.from_user.id] = m.text
    kb = InlineKeyboardBuilder()
    
    # Кнопки с голосами (СНГ)
    kb.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
           types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    kb.row(types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"),
           types.InlineKeyboardButton(text="🇺🇦 Остап", callback_data="v_uk-UA-OstapNeural"))
    # English
    kb.row(types.InlineKeyboardButton(text="🇺🇸 Ava (EN)", callback_data="v_en-US-AvaNeural"),
           types.InlineKeyboardButton(text="🇬🇧 Sonia (EN)", callback_data="v_en-GB-SoniaNeural"))
    # Азия / Европа
    kb.row(types.InlineKeyboardButton(text="🇩🇪 Katja", callback_data="v_de-DE-KatjaNeural"),
           types.InlineKeyboardButton(text="🇯🇵 Nanami", callback_data="v_ja-JP-NanamiNeural"))
    
    await m.answer("Выберите голос:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def voice_callback(c: types.CallbackQuery):
    voice = c.data.split("_")[1]
    text = user_states.get(c.from_user.id, "Привет")
    msg = await c.message.edit_text("⌛ Генерация аудио...")
    try:
        fid = await generate_speech_logic(text[:1000], voice, "natural")
        await c.message.answer_audio(types.FSInputFile(os.path.join(AUDIO_DIR, fid)), caption="✅ Готово!")
        await msg.delete()
    except Exception as e: await c.message.answer(f"Ошибка: {e}")

# --- API ЭНДПОИНТЫ ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        res = await asyncio.to_thread(model_ai.generate_content, request.message)
        return {"reply": res.text}
    except: return {"reply": "Gemini 2.5 спит. Попробуй позже!"}

@app.post("/api/generate")
async def generate_endpoint(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {"request": request, "file": file})

# Обработка всех остальных страниц меню
@app.get("/{page_name}", response_class=HTMLResponse)
async def catch_all(request: Request, page_name: str):
    try: return templates.TemplateResponse(f"{page_name}.html", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)






