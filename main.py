import os
import uuid
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

app = FastAPI(redirect_slashes=True)

# --- ТВОЙ ТОКЕН БОТА ---
BOT_TOKEN = "8337208157:AAEPSueD83LmT96Yr1ThAkX3V7HxvHWdh9U"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__io__))

# Папки
for path in ["static", "static/audio"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural" # По умолчанию "Табиғи"

# --- ЛОГИКА ОЗВУЧКИ (ПРЕСЕТЫ ГЛОСА) ---
async def generate_speech(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    
    # Настройки для оживления голоса:
    if mode == "natural":
        # Делаем голос чуть глубже и спокойнее (убираем эффект спешки)
        rate = "-10%" 
        pitch = "-5Hz"
    elif mode == "slow":
        # Максимальная четкость для обучения
        rate = "-25%"
        pitch = "0Hz"
    elif mode == "fast":
        # Энергичный тон для рекламы и Shorts
        rate = "+10%"
        pitch = "+2Hz"
    else:
        rate = "+0%"
        pitch = "+0Hz"

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(file_path)
    return file_id

# --- МАРШРУТЫ САЙТА ---

@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text or len(request.text) > 2000:
        raise HTTPException(status_code=400, detail="Text error")
    try:
        # Теперь передаем mode с фронтенда (natural/slow/fast)
        file_id = await generate_speech(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- ИНТЕГРАЦИЯ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎙 **SpeechClone AI Bot**\nОтправьте текст, и я озвучу его Даулетом в режиме 'Natural'.")

@dp.message()
async def handle_text(message: types.Message):
    if not message.text: return
    
    msg = await message.answer("⌛ Генерирую...")
    try:
        # Бот по умолчанию использует самый качественный пресет 'natural'
        file_id = await generate_speech(message.text, "kk-KZ-DauletNeural", "natural")
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        audio = types.FSInputFile(file_path)
        await message.answer_audio(audio, caption="✅ Озвучено через @speechclonebot")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"Ошибка: {str(e)}")

# Запуск бота при старте FastAPI
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))













