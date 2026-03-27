import os
import uuid
import asyncio
import edge_tts
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static/audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли текст для озвучки.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    msg = await message.answer("⏳ Озвучиваю...")
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        comm = edge_tts.Communicate(message.text, "ru-RU-DmitryNeural")
        await comm.save(path)
        await message.answer_voice(voice=types.FSInputFile(path))
        await msg.delete()
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

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

# --- ЗАПУСК БОТА ---
@app.on_event("startup")
async def startup_event():
    # Запускаем поллинг бота в фоне при старте FastAPI
    asyncio.create_task(dp.start_polling(bot))

# Убрали ручной uvicorn.run с портом 8000

