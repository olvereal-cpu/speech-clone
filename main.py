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
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyAZ71DeMfVZf9w6-mUWH7WO0oxG8kgA1MA")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# --- РАБОТА С БАЗОЙ (БЕЗ ВЫРЕЗАНИЙ) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

app = FastAPI()

# Создание структуры папок
for path in ["static", "static/audio", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- ЛОГИКА ОЗВУЧКИ (ДЛЯ САЙТА И БОТА) ---
async def internal_tts(text: str, voice: str, rate: str = "+0%"):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
    await communicate.save(file_path)
    return file_id, file_path

# --- API ---
class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

@app.post("/api/generate")
async def api_gen(request: TTSRequest):
    try:
        rates = {"natural": "+0%", "slow": "-15%", "fast": "+15%"}
        fid, _ = await internal_tts(request.text, request.voice, rates.get(request.mode, "+0%"))
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def api_chat(request: ChatRequest):
    try:
        client = genai.Client(api_key=GEMINI_KEY)
        response = client.models.generate_content(model="gemini-2.0-flash", contents=request.message)
        return {"reply": response.text}
    except:
        return {"reply": "Бро, я тут, но связи с космосом пока нет. Спроси позже!"}

# --- ВСЕ РОУТЫ (ВОССТАНОВЛЕНЫ) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/blog/{p}", response_class=HTMLResponse)
async def blog_post(request: Request, p: str):
    if p.endswith(".html"): p = p[:-5]
    return templates.TemplateResponse(f"blog/{p}.html", {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def dl(request: Request):
    f = request.query_params.get('file')
    return templates.TemplateResponse("download.html", {"request": request, "file_name": f, "file_url": f"/static/audio/{f}" if f else "#"})

# Юридические и инфо-страницы
@app.get("/privacy")
async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})
@app.get("/disclaimer")
async def disclaimer(request: Request): return templates.TemplateResponse("disclaimer.html", {"request": request})
@app.get("/about")
async def about(request: Request): return templates.TemplateResponse("about.html", {"request": request})
@app.get("/donate")
async def donate(request: Request): return templates.TemplateResponse("donate.html", {"request": request})
@app.get("/contacts")
async def contacts(request: Request): return templates.TemplateResponse("contacts.html", {"request": request})

# --- ТЕЛЕГРАМ БОТ (ГЕНЕРАТОР) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer("🎙 Пришли текст — я пришлю озвучку! Все голоса на speechclone.online")

@dp.message(F.text)
async def bot_handle(message: types.Message):
    if len(message.text) > 1500: return await message.answer("Много букв, Бро. Давай поменьше.")
    msg = await message.answer("⏳ Магия звука в процессе...")
    try:
        _, fpath = await internal_tts(message.text, "ru-RU-DmitryNeural")
        await message.answer_voice(FSInputFile(fpath), caption="Готово в @speechclone")
        await msg.delete()
    except: await message.answer("Что-то пошло не так...")

@app.on_event("startup")
async def on_start():
    init_db()
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)










