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
from aiogram.types import FSInputFile

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

# Папки для статики и шаблонов
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- БАЗА ДАННЫХ ---
DB_PATH = os.path.join(BASE_DIR, "users.db")
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

# --- МОДЕЛИ ---
class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- API ЭНДПОИНТЫ ---
@app.post("/api/generate")
async def generate(request: TTSRequest):
    f_id = f"{uuid.uuid4()}.mp3"
    f_path = os.path.join(BASE_DIR, "static/audio", f_id)
    rates = {"natural": "+0%", "slow": "-15%", "fast": "+15%"}
    communicate = edge_tts.Communicate(request.text, request.voice, rate=rates.get(request.mode, "+0%"))
    await communicate.save(f_path)
    return {"audio_url": f"/static/audio/{f_id}"}

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        response = client.models.generate_content(model="gemini-2.5-flash", contents=request.message)
        return {"reply": response.text}
    except:
        return {"reply": "Бро, я на связи! Спроси что-нибудь еще."}

# --- ВСЕ РОУТЫ (ПРОВЕРЬ НАЛИЧИЕ ФАЙЛОВ В TEMPLATES) ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/donate", response_class=HTMLResponse)
async def donate(request: Request):
    return templates.TemplateResponse("donate.html", {"request": request})

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer(request: Request):
    return templates.TemplateResponse("disclaimer.html", {"request": request})

@app.get("/contacts", response_class=HTMLResponse)
async def contacts(request: Request):
    return templates.TemplateResponse("contacts.html", {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request):
    f = request.query_params.get('file')
    return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{f}" if f else "#"})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def blog(request: Request, post_name: str):
    f = post_name if post_name.endswith(".html") else f"{post_name}.html"
    return templates.TemplateResponse(f"blog/{f}", {"request": request})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(F.text)
async def bot_tts(m: types.Message):
    f_id = f"{uuid.uuid4()}.mp3"
    f_path = os.path.join(BASE_DIR, "static/audio", f_id)
    await edge_tts.Communicate(m.text, "ru-RU-DmitryNeural").save(f_path)
    await m.answer_voice(FSInputFile(f_path))

# --- ЗАПУСК ---
@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(dp.start_polling(bot))









