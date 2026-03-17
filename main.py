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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")

app = FastAPI()

# Папки для статики
os.makedirs(os.path.join(BASE_DIR, "static/audio"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "templates/blog"), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- БАЗА ДАННЫХ ---
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

# --- ИИ КЛИЕНТ ---
def get_ai():
    try:
        return genai.Client(api_key=GEMINI_KEY)
    except:
        return None

class ChatRequest(BaseModel):
    message: str

# --- API ---
@app.post("/api/generate")
async def generate(data: dict):
    text = data.get("text")
    voice = data.get("voice", "ru-RU-DmitryNeural")
    if not text: raise HTTPException(status_code=400)
    
    file_id = f"{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(file_path)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    client = get_ai()
    if not client: return {"reply": "🤖 Бро, ИИ сейчас спит. Попробуй позже."}
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=request.message
        )
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"🤖 Ошибка API: {str(e)[:50]}"}

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
    try: return templates.TemplateResponse(f"blog/{p}.html", {"request": request})
    except: raise HTTPException(status_code=404)

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request):
    file_name = request.query_params.get('file')
    # ИСПРАВЛЕНИЕ: Передаем file_url, чтобы в HTML была прямая ссылка на файл
    file_url = f"/static/audio/{file_name}" if file_name else "#"
    return templates.TemplateResponse("download.html", {
        "request": request, 
        "file_url": file_url,
        "file_name": file_name
    })

@app.get("/{p}", response_class=HTMLResponse)
async def catch_all(request: Request, p: str):
    if p in ["static", "api", "templates", "robots.txt", "sitemap.xml"]: return
    if p.endswith(".html"): p = p[:-5]
    try: return templates.TemplateResponse(f"{p}.html", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
























