import os
import re
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
from aiogram import Bot, Dispatcher

# --- НАСТРОЙКИ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

# Создаем папки
for p in ["static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, p), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class GenerateRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

# --- API ---
@app.post("/api/generate")
async def generate(req: GenerateRequest):
    file_id = f"{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    rate = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}.get(req.mode, "+0%")
    try:
        communicate = edge_tts.Communicate(req.text, req.voice, rate=rate)
        await communicate.save(file_path)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- СТРАНИЦЫ ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request):
    file_name = request.query_params.get('file')
    # КРИТИЧЕСКИЙ ФИКС: формируем полный путь для кнопки скачивания
    file_url = f"/static/audio/{file_name}" if file_name else "#"
    return templates.TemplateResponse("download.html", {
        "request": request, 
        "file_url": file_url,
        "file_name": file_name
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)











