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

CHANNEL_ID = "@speechclone"
SITE_URL = "https://speechclone.online"

# --- 2. ИНИЦИАЛИЗАЦИЯ GEMINI 3.1 FLASH LITE ---
class ModelManager:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        
    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text if resp else "Ошибка ИИ"
        except Exception as e: 
            return f"Ошибка API: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- 3. ПУТИ И ГОЛОСА ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(AUDIO_DIR, exist_ok=True)

# ВЕСЬ СПИСОК ГОЛОСОВ ДЛЯ БОТА
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural", "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural", "🇺🇦 Остап": "uk-UA-OstapNeural",
    "🇹🇷 Ahmet": "tr-TR-AhmetNeural", "🇪🇸 Alvaro": "es-ES-AlvaroNeural",
    "🇩🇪 Conrad": "de-DE-ConradNeural", "🇵🇱 Marek": "pl-PL-MarekNeural",
    "🇫🇷 Remy": "fr-FR-RemyNeural", "🇯🇵 Keita": "ja-JP-KeitaNeural",
    "🇨🇳 Yunxi": "zh-CN-YunxiNeural"
}

# --- 4. БД И СЛАГИ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit(); conn.close()

def slugify(text):
    chars = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"}
    res = "".join(chars.get(c, c) for c in text.lower())
    return re.sub(r'[^a-z0-9]+', '-', res).strip('-')

init_db()

# --- 5. ТЕЛЕГРАМ БОТ (STARS + ОЗВУЧКА) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 Поддержать (Stars)", callback_data="buy_stars"))
    await message.answer("🤖 Выбери голос и отправь текст:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def send_invoice(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Stars", description="50 Stars", payload="pay", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id)); conn.commit(); conn.close()
    await call.message.answer(f"✅ Голос: {v_id}"); await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    try:
        conn = sqlite3.connect(DB_PATH); res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone(); v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(message.text, v_id).save(path)
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ MP3", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer_audio(audio=FSInputFile(path), caption=f"🗣 {v_id}", reply_markup=kb.as_markup())
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

# --- 6. FASTAPI (ВСЕ РОУТЫ) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class AdminGenRequest(BaseModel): message: str; category: str = "Технологии"; color: str = "blue"

# ГЛАВНЫЕ СТРАНИЦЫ
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 12').fetchall()]; conn.close()
    return templates.TemplateResponse(request, "index.html", {"request": request, "posts": posts})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall()]; conn.close()
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": posts, "is_single": False})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    post = conn.execute('SELECT * FROM posts WHERE slug = ?', (slug,)).fetchone(); conn.close()
    if not post: raise HTTPException(404)
    return templates.TemplateResponse(request, "blog_index.html", {"request": request, "posts": [dict(post)], "is_single": True})

# --- ВСЕ ДОПОЛНИТЕЛЬНЫЕ РОУТЫ ИЗ ФУТЕРА ---
@app.get("/voices")
async def voices_view(request: Request): return templates.TemplateResponse(request, "voices.html", {"request": request})

@app.get("/about")
async def about_view(request: Request): return templates.TemplateResponse(request, "about.html", {"request": request})

@app.get("/instructions")
async def instr_view(request: Request): return templates.TemplateResponse(request, "instructions.html", {"request": request})

@app.get("/privacy")
async def priv_view(request: Request): return templates.TemplateResponse(request, "privacy.html", {"request": request})

@app.get("/disclaimer")
async def disc_view(request: Request): return templates.TemplateResponse(request, "disclaimer.html", {"request": request})

@app.get("/faq")
async def faq_view(request: Request): return templates.TemplateResponse(request, "faq.html", {"request": request})

@app.get("/premium")
async def premium_view(request: Request): return templates.TemplateResponse(request, "premium.html", {"request": request})

# АДМИНКА И ГЕНЕРАЦИЯ (РАЗНЫЕ КАРТИНКИ)
@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_gen_view(request: Request): return templates.TemplateResponse(request, "admin_generate.html", {"request": request})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    prompt = f"Напиши статью: {req.message}. Формат: TITLE: [..] EXCERPT: [..] KEYWORD: [1 англ слово для фото] CONTENT: [HTML]"
    res = await mm.generate(prompt)
    try:
        title = re.search(r"TITLE:(.*?)(?=EXCERPT|$)", res, re.S).group(1).strip()
        excerpt = re.search(r"EXCERPT:(.*?)(?=KEYWORD|$)", res, re.S).group(1).strip()
        kw = re.search(r"KEYWORD:(.*?)(?=CONTENT|$)", res, re.S).group(1).strip()
        content = res.split("CONTENT:")[1].strip()
        slug = slugify(title)
        # Генерация разной картинки по ключевому слову от ИИ
        img = f"https://images.unsplash.com/photo-1620712313015-335293771097?auto=format&fit=crop&q=80&w=1024&{kw}&sig={uuid.uuid4().hex[:5]}"
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO posts (title, slug, image, excerpt, content, date, author, category, color) VALUES (?,?,?,?,?,?,?,?,?)', 
                     (title, slug, img, excerpt, content, datetime.now().strftime("%d.%m.%Y"), "Gemini 3.1", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success", "slug": slug}
    except: return JSONResponse(500, {"message": "Ошибка формата"})

# ЗАГРУЗКА ФАЙЛОВ
@app.get("/wait-download", response_class=HTMLResponse)
async def wait_view(request: Request, file: str):
    return templates.TemplateResponse(request, "wait_page.html", {"request": request, "file_url": f"/download?file={file}"})

@app.get("/download")
async def download_file(file: str):
    path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(path): return FileResponse(path, filename="speechclone.mp3")
    return HTMLResponse("File not found", 404)

@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))










