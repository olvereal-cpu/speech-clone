import os
import re
import uuid
import asyncio
import ssl
import sqlite3
import edge_tts
import random
from google import genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_URL = "https://t.me/speechclone"
CHANNEL_ID = "@speechclone" 
# Твой ключ Gemini
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")

# --- БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

app = FastAPI(redirect_slashes=True)

# Авто-создание всех нужных папок
for path in ["static", "static/audio", "static/images/blog", "templates/blog"]:
    full_p = os.path.join(BASE_DIR, path)
    if not os.path.exists(full_p):
        os.makedirs(full_p, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- МОДЕЛИ ДАННЫХ ---
class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    # Очистка текста от лишних символов
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    rates = {"natural": "-5%", "slow": "-15%", "fast": "+15%"}
    rate = rates.get(mode, "+0%")
    
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id

# --- API ЭНДПОИНТЫ ---
@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=request.message
        )
        return {"reply": response.text}
    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "Бро, я сейчас немного занят обновлением мозгов. Зайди через минуту!"}

# --- РОУТЫ СТРАНИЦ ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/blog", response_class=HTMLResponse)
async def blog_index(request: Request):
    return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{p}", response_class=HTMLResponse)
async def blog_post(request: Request, p: str):
    if p.endswith(".html"): p = p[:-5]
    try:
        return templates.TemplateResponse(f"blog/{p}.html", {"request": request})
    except:
        raise HTTPException(status_code=404)

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request):
    file_name = request.query_params.get('file')
    file_url = f"/static/audio/{file_name}" if file_name else "#"
    return templates.TemplateResponse("download.html", {
        "request": request, 
        "file_name": file_name,
        "file_url": file_url
    })

@app.get("/{p}", response_class=HTMLResponse)
async def other_pages(request: Request, p: str):
    if p in ["static", "api", "templates", "robots.txt", "sitemap.xml"]:
        return
    if p.endswith(".html"): p = p[:-5]
    try:
        return templates.TemplateResponse(f"{p}.html", {"request": request})
    except:
        return templates.TemplateResponse("index.html", {"request": request})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Перейти на сайт", url="https://speechclone.online"))
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я бот SpeechClone. Я помогаю озвучивать текст и отвечать на вопросы.\n"
        "Заходи на наш сайт для полной озвучки!",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        users = get_all_users()
        await message.answer(f"📊 Всего пользователей в базе: {len(users)}")

@dp.message()
async def handle_all_messages(message: types.Message):
    # Простой эхо-ответ или можно подключить Gemini сюда тоже
    await message.answer("Я тебя услышал! Если хочешь озвучку — используй сайт speechclone.online")

# --- ЗАПУСК ---
@app.on_event("startup")
async def startup_event():
    init_db()
    # Запуск бота в отдельной задаче, чтобы не вешать сервер
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)










