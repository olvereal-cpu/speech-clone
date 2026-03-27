import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОНФИГ ---
ADMIN_ID = 430747895
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
DONATE_URL = "https://yoomoney.ru/to/4100118943714856"

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH = os.path.join(BASE_DIR, "users.db")

for p in [STATIC_DIR, AUDIO_DIR, TEMPLATES_DIR]: os.makedirs(p, exist_ok=True)

# --- ИИ И БАЗА ---
genai.configure(api_key=os.getenv("GEMINI_KEY"))
model_ai = genai.GenerativeModel('gemini-1.5-flash')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()
init_db()

# --- ГОЛОСА (ПОЛНЫЙ СПИСОК ДЛЯ БОТА И САЙТА) ---
VOICES = {
    "🇷🇺 СНГ": [
        ("Дмитрий (RU)", "ru-RU-DmitryNeural"),
        ("Светлана (RU)", "ru-RU-SvetlanaNeural"),
        ("Даулет (KZ)", "kk-KZ-DauletNeural"),
        ("Остап (UA)", "uk-UA-OstapNeural"),
        ("Полина (UA)", "uk-UA-PolinaNeural")
    ],
    "🇺🇸 EN / EU": [
        ("Ava (US)", "en-US-AvaNeural"),
        ("Andrew (US)", "en-US-AndrewNeural"),
        ("Sonia (GB)", "en-GB-SoniaNeural"),
        ("Katja (DE)", "de-DE-KatjaNeural"),
        ("Denise (FR)", "fr-FR-DeniseNeural"),
        ("Elvira (ES)", "es-ES-ElviraNeural")
    ],
    "🇯🇵 ASIA": [
        ("Nanami (JP)", "ja-JP-NanamiNeural"),
        ("SunHi (KR)", "ko-KR-SunHiNeural"),
        ("Xiaoxiao (CN)", "zh-CN-XiaoxiaoNeural")
    ]
}

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(AUDIO_DIR, file_id)
    
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        return re.sub(r'\+([%s])' % vowels, r'\1' + chr(769), t)

    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")
    
    communicate = edge_tts.Communicate(fix_stress(text), voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- FastAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate")
async def api_gen(req: TTSRequest):
    try:
        fid = await generate_speech_logic(req.text, req.voice, req.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e: return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/chat")
async def api_chat(req: BaseModel): # Простой фикс для чата
    try:
        res = await asyncio.to_thread(model_ai.generate_content, req.message)
        return {"reply": res.text}
    except: return {"reply": "ИИ занят."}

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_texts = {}

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (m.from_user.id,)); conn.commit(); conn.close()
    kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="💰 Поддержать проект", url=DONATE_URL))
    await m.answer(f"Привет! Пришли текст, и я его озвучу.\nНа сайте доступно 10+ голосов!", reply_markup=kb.as_markup())

@dp.message(F.text)
async def handle_msg(m: types.Message):
    if m.text.startswith("/"): return
    user_texts[m.from_user.id] = m.text
    kb = InlineKeyboardBuilder()
    # Собираем кнопки из нашего списка VOICES
    for cat, voices in VOICES.items():
        for name, vid in voices:
            kb.row(types.InlineKeyboardButton(text=name, callback_data=f"v_{vid}"))
    await m.answer("Выберите голос для озвучки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def voice_call(c: types.CallbackQuery):
    voice = c.data.split("_")[1]
    text = user_texts.get(c.from_user.id, "Привет")
    msg = await c.message.answer("⌛ Генерирую аудио...")
    try:
        fid = await generate_speech_logic(text[:1000], voice, "natural")
        await c.message.answer_audio(types.FSInputFile(os.path.join(AUDIO_DIR, fid)), caption=f"✅ Готово! Голос: {voice}")
        await msg.delete()
    except Exception as e: await c.message.answer(f"Ошибка: {e}")

@app.on_event("startup")
async def on_startup(): asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))





