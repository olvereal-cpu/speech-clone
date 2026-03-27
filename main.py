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

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
if GEMINI_API_KEY:
    try:
        google.generativeai.configure(api_key=GEMINI_API_KEY)
        model_ai = google.generativeai.GenerativeModel(
            model_name='gemini-2.5-flash', 
            system_instruction=(
                "Ты — Спич-Бро, официальный ИИ-помощник SpeechClone.online. "
                "Твоя задача: помогать с озвучкой, советовать голоса и ставить ударения. "
                "Пиши кратко, с юмором и эмодзи. Ударения: знак '+' перед гласной."
            )
        )
        print("✅ Спич-Бро на базе Gemini 2.5 Flash готов к работе!")
    except Exception as e:
        print(f"❌ Ошибка инициализации Gemini 2.5: {e}")
        model_ai = None
else:
    model_ai = None

# --- БАЗА ДАННЫХ ---
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

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
    rate = rates.get(mode, "+0%")
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- ЭНДПОИНТЫ САЙТА (ЯВНЫЕ) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(name="index.html", context={"request": request})

@app.get("/voices", response_class=HTMLResponse)
async def voices(request: Request): 
    return templates.TemplateResponse("voices.html", {"request": request})

@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request): 
    return templates.TemplateResponse("blog.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request): 
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request): 
    return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request): 
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer(request: Request): 
    return templates.TemplateResponse("disclaimer.html", {"request": request})

@app.get("/download", response_class=HTMLResponse)
async def download_page(request: Request, file: str = None):
    return templates.TemplateResponse("download.html", {"request": request, "file_name": file})

# --- API ---
@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        if not model_ai: return {"reply": "ИИ временно недоступен."}
        response = await asyncio.to_thread(model_ai.generate_content, request.message)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"Ошибка: {str(e)}"}

# Ловушка для остальных страниц (должна быть в самом конце)
@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try:
        return templates.TemplateResponse(f"{page}.html", {"request": request})
    except:
        return templates.TemplateResponse("index.html", {"request": request})

# --- ЧИСТЫЙ ЗАПУСК ---
async def start_services():
    print("🤖 Бот SpeechClone запускается...")
    # Запускаем поллинг бота как фоновую задачу
    asyncio.create_task(dp.start_polling(bot))
    
    import uvicorn
    # На Рендере важно брать PORT из переменной окружения
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
    print(f"🌐 Сайт запускается на порту {port}...")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Остановка всех служб")



