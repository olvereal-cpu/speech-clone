import os
import uuid
import asyncio
import sqlite3
import re
import edge_tts
import google.generativeai as genai
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery

# --- 1. КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 
SITE_URL = "https://speechclone.online"

# --- 2. GEMINI 3.1 FLASH LITE PREVIEW ---
class ModelManager:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        # Твоя рабочая превью-модель
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        
    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text if resp else ""
        except Exception as e:
            print(f"Gemini Error: {e}")
            return ""

mm = ModelManager(GEMINI_API_KEY)

# --- 3. ПУТИ И ДАННЫЕ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(AUDIO_DIR, exist_ok=True)

VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural", "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural", "🇺🇦 Остап (UA)": "uk-UA-OstapNeural",
    "🇹🇷 Ahmet (TR)": "tr-TR-AhmetNeural", "🇪🇸 Alvaro (ES)": "es-ES-AlvaroNeural",
    "🇩🇪 Conrad (DE)": "de-DE-ConradNeural", "🇵🇱 Marek (PL)": "pl-PL-MarekNeural",
    "🇫🇷 Remy (FR)": "fr-FR-RemyNeural", "🇯🇵 Keita (JP)": "ja-JP-KeitaNeural",
    "🇨🇳 Yunxi (CN)": "zh-CN-YunxiNeural"
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit(); conn.close()

def slugify(text):
    res = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return res if len(res) > 2 else f"post-{uuid.uuid4().hex[:5]}"

init_db()

# --- 4. ТЕЛЕГРАМ БОТ (ГОЛОСА + STARS) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 Купить Stars (50 XTR)", callback_data="buy_stars"))
    await message.answer("🤖 Привет! Выбери голос и отправь текст для озвучки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def process_buy(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Донат", description="Поддержка проекта", payload="xtr", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_check(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_v(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id)); conn.commit(); conn.close()
    await call.message.answer(f"✅ Голос: {v_id}"); await call.answer()

@dp.message(F.text)
async def tts_msg(message: types.Message):
    if message.text.startswith("/"): return
    conn = sqlite3.connect(DB_PATH); res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone(); v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
    fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
    await edge_tts.Communicate(message.text, v_id).save(path)
    await message.answer_audio(audio=FSInputFile(path), reply_markup=InlineKeyboardBuilder().button(text="📥 Скачать на сайте", url=f"{SITE_URL}/wait-download?file={fid}").as_markup())

# --- 5. FASTAPI (ВСЕ РОУТЫ + ЧАТ) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class ChatReq(BaseModel): message: str
class GenReq(BaseModel): message: str; category: str = "ИИ"; color: str = "blue"

# ГЛАВНАЯ И БЛОГ
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 12').fetchall()]; conn.close()
    return templates.TemplateResponse(request, "index.html", {"request": request, "posts": posts})

@app.get("/blog", response_class=HTMLResponse)
async def blog_all(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall()]; conn.close()
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": posts, "is_single": False})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_one(request: Request, slug: str):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    p = conn.execute('SELECT * FROM posts WHERE slug = ?', (slug,)).fetchone(); conn.close()
    if not p: raise HTTPException(404)
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": [dict(p)], "is_single": True})

# ВСЕ РОУТЫ МЕНЮ
@app.get("/voices")
async def pg_v(r: Request): return templates.TemplateResponse(r, "voices.html", {"request": r})
@app.get("/about")
async def pg_a(r: Request): return templates.TemplateResponse(r, "about.html", {"request": r})
@app.get("/instructions")
async def pg_i(r: Request): return templates.TemplateResponse(r, "instructions.html", {"request": r})
@app.get("/privacy")
async def pg_p(r: Request): return templates.TemplateResponse(r, "privacy.html", {"request": r})
@app.get("/disclaimer")
async def pg_d(r: Request): return templates.TemplateResponse(r, "disclaimer.html", {"request": r})
@app.get("/faq")
async def pg_f(r: Request): return templates.TemplateResponse(r, "faq.html", {"request": r})
@app.get("/premium")
async def pg_pr(r: Request): return templates.TemplateResponse(r, "premium.html", {"request": r})
@app.get("/contact")
async def pg_co(r: Request): return templates.TemplateResponse(r, "contact.html", {"request": r})
@app.get("/admin/generate")
async def pg_adm(r: Request): return templates.TemplateResponse(r, "admin_generate.html", {"request": r})

# ЧАТ ДЛЯ САЙТА
@app.post("/api/chat")
async def api_chat(req: ChatReq):
    ans = await mm.generate(f"Ответь кратко как ассистент SpeechClone: {req.message}")
    return {"reply": ans or "Сервер ИИ временно недоступен."}

# ГЕНЕРАЦИЯ ПОСТОВ (БЕЗОПАСНАЯ)
@app.post("/api/admin/generate-post")
async def api_gen(req: GenReq):
    prompt = f"Напиши статью про {req.message}. Формат: TITLE:.. EXCERPT:.. KEYWORD:.. CONTENT:.."
    raw = await mm.generate(prompt)
    if not raw: return JSONResponse(500, {"error": "ИИ не ответил"})
    
    try:
        # Парсим с запасом на ошибки формата
        title = re.search(r"TITLE:(.*?)(?=EXCERPT|$)", raw, re.S).group(1).strip()
        kw = re.search(r"KEYWORD:(.*?)(?=CONTENT|$)", raw, re.S).group(1).strip()
        content = raw.split("CONTENT:")[1].strip()
        excerpt = "Интересная статья об ИИ и технологиях будущего."
        
        slug = slugify(title)
        # РАЗНЫЕ КАРТИНКИ через Unsplash Source
        img = f"https://images.unsplash.com/featured/?{kw}&sig={uuid.uuid4().hex[:5]}"
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO posts (title, slug, image, excerpt, content, date, author, category, color) VALUES (?,?,?,?,?,?,?,?,?)', 
                     (title, slug, img, excerpt, content, datetime.now().strftime("%d.%m.%Y"), "Gemini AI", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success", "slug": slug}
    except Exception as e:
        return JSONResponse(500, {"error": f"Ошибка парсинга: {e}"})

@app.get("/wait-download", response_class=HTMLResponse)
async def wait(request: Request, file: str):
    return templates.TemplateResponse(request, "wait_page.html", {"request": request, "file_url": f"/download?file={file}"})

@app.get("/download")
async def dl(file: str):
    p = os.path.join(AUDIO_DIR, file)
    if os.path.exists(p): return FileResponse(p, filename="speechclone.mp3")
    return HTMLResponse("Файл удален", 404)

@app.on_event("startup")
async def startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))













