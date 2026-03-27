import os
import re
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
# ВСТАВЬ СВОЙ НОВЫЙ КЛЮЧ ТУТ:
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"

# --- ИНИЦИАЛИЗАЦИЯ ИИ (МОДЕЛЬ 2.5 FLASH) ---
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Прописываю именно ту модель, на которой мы работали в феврале
        model_ai = genai.GenerativeModel(
            model_name='gemini-2.5-flash', 
            system_instruction=(
                "Ты — Спич-Бро, официальный ИИ-помощник SpeechClone.online. "
                "Твоя задача: помогать с озвучкой, советовать голоса и ставить ударения. "
                "Пиши кратко, с юмором и эмодзи. Ударения: знак '+' перед гласной."
            )
        )
    except Exception as e:
        print(f"Ошибка инициализации Gemini 2.5: {e}")
        model_ai = None

# --- БАЗА ДАННЫХ (ФЕВРАЛЬСКАЯ СТРУКТУРА) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined_at DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- FASTAPI НАСТРОЙКИ ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Авто-создание папок статики
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

# --- ЛОГИКА ОЗВУЧКИ (EDGE TTS) ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    
    # Очистка текста и работа с ударениями (+)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    
    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")

    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- ЭНДПОИНТЫ САЙТА ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    if not model_ai:
        return {"reply": "Бро, проверь ключ API в main.py! 2.5 Flash не отвечает."}
    try:
        response = await asyncio.to_thread(model_ai.generate_content, request.message)
        return {"reply": response.text}
    except Exception as e:
        print(f"AI Error: {e}")
        return {"reply": "Ошибка связи с ИИ 2.5. Попробуй позже."}

# --- ДЛЯ БЛОГА И ДРУГИХ СТРАНИЦ (МЕНЮ) ---
@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try:
        return templates.TemplateResponse(f"{page}.html", {"request": request})
    except:
        return templates.TemplateResponse("index.html", {"request": request})

# 1. В начале импорты и ключи
import os
import asyncio
# ... (остальной код)

# 2. Потом база данных и настройки FastAPI (app = FastAPI)
# ...

# 3. Потом все функции сайта (@app.get, @app.post)
# ...

# 4. И В САМЫЙ НИЗ СТАВИШЬ ЭТОТ КУСОК:
async def start_services():
    # Запускаем бота в фоне
    print("🤖 Бот запускается...")
    asyncio.create_task(dp.start_polling(bot))
    
    # Запускаем веб-сервер через uvicorn
    import uvicorn
    # Берем порт из настроек системы, если его нет — ставим 5000
    port = int(os.environ.get("PORT", 5000)) 
    
    print(f"🌐 Сайт стартует на порту {port}...")
    
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=port, 
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Остановка...")





