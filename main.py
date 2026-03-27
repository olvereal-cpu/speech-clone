import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from aiogram import Bot, Dispatcher

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ИНИЦИАЛИЗАЦИЯ ИИ (GEMINI 2.5 FLASH) ---
if GEMINI_API_KEY:
    try:
        google.generativeai.configure(api_key=GEMINI_API_KEY)
        model_ai = google.generativeai.GenerativeModel(
            model_name='gemini-2.5-flash', 
            system_instruction=(
                "Ты — Спич-Бро, официальный ИИ-помощник SpeechClone.online. "
                "Помогай с озвучкой и ударениями (+ перед гласной). Пиши кратко и с юмором."
            )
        )
    except Exception as e:
        model_ai = None
else:
    model_ai = None

# --- БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_at DATETIME)')
    conn.commit()
    conn.close()

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Папки статики
for p in ["static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, p), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel):
    message: str

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str

# --- ЛОГИКА ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- РОУТЫ ---
# --- ЯВНЫЕ РОУТЫ ДЛЯ МЕНЮ ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/voices", response_class=HTMLResponse)
async def voices(request: Request):
    return templates.TemplateResponse("voices.html", {"request": request})

@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    # Если у тебя файл называется blog.html или blog_index.html — поправь тут имя
    return templates.TemplateResponse("blog.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/contribute", response_class=HTMLResponse)
async def contribute(request: Request):
    return templates.TemplateResponse("contribute.html", {"request": request})

@app.get("/download", response_class=HTMLResponse)
async def download_page(request: Request, file: str = None):
    return templates.TemplateResponse("download.html", {"request": request, "file_name": file})

# --- API ДЛЯ ОЗВУЧКИ И ЧАТА ---

@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/chat")
async def chat(request: ChatRequest):
    if not model_ai: return {"reply": "Бро, ИИ спит."}
    try:
        res = await asyncio.to_thread(model_ai.generate_content, request.message)
        return {"reply": res.text}
    except:
        return {"reply": "Ошибка связи с Спич-Бро."}

# --- УНИВЕРСАЛЬНЫЙ РОУТ (В САМОМ КОНЦЕ) ---
@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    # Если зашли на страницу, которой нет в списке выше, пробуем найти файл
    try:
        return templates.TemplateResponse(f"{page}.html", {"request": request})
    except:
        # Если и файла нет — возвращаем на главную
        return templates.TemplateResponse("index.html", {"request": request})

# --- ЧИСТЫЙ ЗАПУСК ДЛЯ RENDER ---
async def start_services():
    init_db()
    asyncio.create_task(dp.start_polling(bot))
    
    import uvicorn
    # На Рендере достаточно указать хост, остальное он подхватит сам из окружения
    config = uvicorn.Config(app, host="0.0.0.0", loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        pass





