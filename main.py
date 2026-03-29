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

# --- 2. GEMINI 3.1 FLASH LITE ---
class ModelManager:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        
    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text if resp else "Ошибка ИИ"
        except Exception as e: return f"Ошибка: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- 3. ДАННЫЕ И ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(AUDIO_DIR, exist_ok=True)

# Твои базовые статьи (чтобы блог не был пустым сразу)
STATIC_ARTICLES = [
    {
        "title": "Как работает клонирование голоса", "slug": "how-it-works", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?w=800",
        "excerpt": "Технологии ИИ в 2026 году...", "date": "01.03.2026", "author": "Admin", "category": "Гайд", "color": "blue"
    }
]

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
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

init_db()

# --- 4. БОТ (STARS + VOICE) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 Купить Stars", callback_data="buy_stars"))
    await message.answer("🤖 Привет! Выбери голос:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def pay_stars(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="50 Stars", description="Донат", payload="p", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_v(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id)); conn.commit(); conn.close()
    await call.message.answer(f"✅ Голос: {v_id}"); await call.answer()

@dp.message(F.text)
async def tts_h(message: types.Message):
    if message.text.startswith("/"): return
    conn = sqlite3.connect(DB_PATH); res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone(); v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
    fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
    await edge_tts.Communicate(message.text, v_id).save(path)
    await message.answer_audio(audio=FSInputFile(path), reply_markup=InlineKeyboardBuilder().button(text="📥 Скачать", url=f"{SITE_URL}/wait-download?file={fid}").as_markup())

# --- 5. FASTAPI (ВСЕ РОУТЫ) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class GenReq(BaseModel): message: str; category: str; color: str

def get_all_posts():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall()]; conn.close()
    return db_posts + STATIC_ARTICLES

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request, "posts": get_all_posts()[:10]})

@app.get("/blog", response_class=HTMLResponse)
async def blog(request: Request):
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": get_all_posts(), "is_single": False})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def post(request: Request, slug: str):
    p = next((x for x in get_all_posts() if x['slug'] == slug), None)
    if not p: raise HTTPException(404)
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": [p], "is_single": True})

# --- РОУТЫ МЕНЮ И ФУТЕРА ---
@app.get("/voices")
async def p_v(request: Request): return templates.TemplateResponse(request, "voices.html", {"request": request})
@app.get("/about")
async def p_a(request: Request): return templates.TemplateResponse(request, "about.html", {"request": request})
@app.get("/instructions")
async def p_i(request: Request): return templates.TemplateResponse(request, "instructions.html", {"request": request})
@app.get("/privacy")
async def p_p(request: Request): return templates.TemplateResponse(request, "privacy.html", {"request": request})
@app.get("/disclaimer")
async def p_d(request: Request): return templates.TemplateResponse(request, "disclaimer.html", {"request": request})
@app.get("/faq")
async def p_f(request: Request): return templates.TemplateResponse(request, "faq.html", {"request": request})
@app.get("/premium")
async def p_pr(request: Request): return templates.TemplateResponse(request, "premium.html", {"request": request})
@app.get("/admin/generate")
async def p_gen(request: Request): return templates.TemplateResponse(request, "admin_generate.html", {"request": request})

# ГЕНЕРАЦИЯ С РАЗНЫМИ КАРТИНКАМИ
@app.post("/api/admin/generate-post")
async def gen_post(req: GenReq):
    res = await mm.generate(f"Напиши статью: {req.message}. Формат: TITLE:.. EXCERPT:.. KEYWORD:.. CONTENT:..")
    try:
        title = re.search(r"TITLE:(.*?)(?=EXCERPT)", res, re.S).group(1).strip()
        kw = re.search(r"KEYWORD:(.*?)(?=CONTENT)", res, re.S).group(1).strip()
        content = res.split("CONTENT:")[1].strip()
        slug = slugify(str(uuid.uuid4())[:8] + "-" + title[:20])
        # Картинка зависит от ключевого слова (kw)
        img = f"https://images.unsplash.com/featured/?{kw}&sig={uuid.uuid4().hex[:5]}"
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO posts (title, slug, image, excerpt, content, date, author, category, color) VALUES (?,?,?,?,?,?,?,?,?)', 
                     (title, slug, img, "Статья от ИИ", content, "Сегодня", "Gemini", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success", "slug": slug}
    except: return JSONResponse(500, {"error": "Парсинг не удался"})

@app.get("/wait-download", response_class=HTMLResponse)
async def wait(request: Request, file: str):
    return templates.TemplateResponse(request, "wait_page.html", {"request": request, "file_url": f"/download?file={file}"})

@app.get("/download")
async def dl(file: str):
    return FileResponse(os.path.join(AUDIO_DIR, file), filename="voice.mp3")

@app.on_event("startup")
async def startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))












