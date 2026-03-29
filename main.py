import os
import uuid
import asyncio
import sqlite3
import re
import edge_tts
import google.generativeai as genai
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- SEO ФУНКЦИЯ (ЧПУ) ---
def slugify(text):
    chars = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"}
    text = text.lower()
    for k, v in chars.items(): text = text.replace(k, v)
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')

# --- ИНИЦИАЛИЗАЦИЯ GEMINI 3.1 ---
class ModelManager:
    def __init__(self, api_key):
        self.api_key = api_key
        self.target_model = 'gemini-3.1-flash-lite-preview'
        genai.configure(api_key=self.api_key)
        self.active_model = genai.GenerativeModel(
            model_name=self.target_model,
            safety_settings=[{"category": c, "threshold": "BLOCK_NONE"} for c in ["HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH", "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT"]]
        )

    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.active_model.generate_content, prompt)
            return resp.text if resp else "Ошибка: ИИ не вернул ответ"
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ПУТИ И БД ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit(); conn.close()

init_db()

# --- ДАННЫЕ ГОЛОСОВ ---
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", 
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural", 
    "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇦 Поліна": "uk-UA-PolinaNeural", 
    "🇺🇸 Guy (EN)": "en-US-GuyNeural",
    "🇹🇷 Emel": "tr-TR-EmelNeural"
}

# --- ДАННЫЕ БЛОГА (СТАТИКА) ---
BLOG_POSTS = [
    {
        "id": 9999, "title": "Будущее ИИ в 2026 году", "slug": "budushee-ii-2026", 
        "image": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800", 
        "excerpt": "Как новые модели Gemini изменят нашу жизнь...", "date": "15.03.2026", "author": "Admin", "category": "Технологии", "color": "blue",
        "content": "<p>Технологии не стоят на месте. В 2026 году мы видим расцвет генеративных систем...</p>"
    }
]

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str; key: str = None
class KeyCheck(BaseModel): key: str
class AdminGenRequest(BaseModel): 
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

# --- МАРШРУТЫ САЙТА ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 8').fetchall(); conn.close()
    return templates.TemplateResponse(request, "index.html", {"posts": [dict(p) for p in db_posts]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall(); conn.close()
    all_posts = [dict(p) for p in db_posts] + BLOG_POSTS
    return templates.TemplateResponse(request, "blog_index.html", {"posts": all_posts, "is_single": False})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        prompt = f"""Напиши глубокую SEO-статью на тему: {req.message}. 
        Язык: Русский. Обязательно используй HTML: <p>, <h2>, <ul>, <li>, <b>.
        Статья должна быть длинной, содержательной и полезной.
        Формат ответа СТРОГО по маркерам:
        TITLE: [Заголовок]
        EXCERPT: [SEO-описание до 160 знаков]
        CONTENT: [Полная статья с HTML разметкой]"""
        
        raw = await mm.generate(prompt)
        
        title_match = re.search(r"TITLE:(.*?)(?=EXCERPT|$)", raw, re.S)
        excerpt_match = re.search(r"EXCERPT:(.*?)(?=CONTENT|$)", raw, re.S)
        
        title = title_match.group(1).strip() if title_match else req.message
        excerpt = excerpt_match.group(1).strip() if excerpt_match else "Новое в мире ИИ."
        content = raw.split("CONTENT:")[1].strip() if "CONTENT:" in raw else raw
        content = content.replace("```html", "").replace("```", "").strip()

        new_slug = slugify(title)
        # Массив живых картинок
        img_url = "https://images.unsplash.com/photo-1620712943543-bcc4628c6757?w=800"

        conn = sqlite3.connect(DB_PATH)
        conn.execute('''INSERT INTO posts 
            (title, slug, image, excerpt, content, date, author, category, color) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
            (title, new_slug, img_url, excerpt, content, datetime.now().strftime("%d.%m.%Y"), 
             "SpeechClone AI", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success", "slug": new_slug}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_post = conn.execute('SELECT * FROM posts WHERE slug = ?', (slug,)).fetchone(); conn.close()
    post = dict(db_post) if db_post else next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "blog_index.html", {"posts": [post], "is_single": True})

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status not in ["left", "kicked"]
    except: return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="🌟 Купить Stars", callback_data="buy_stars"))
    await message.answer("👋 Привет! Выбери голос и пришли текст для озвучки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def send_invoice(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Поддержка проекта", description="50 Stars для доступа", payload="stars", currency="XTR", prices=[LabeledPrice(label="Stars", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id)); conn.commit(); conn.close()
    await call.message.answer("✅ Голос успешно выбран!"); await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/") or (message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id)):
        if message.from_user.id != ADMIN_ID:
            return await message.answer(f"❌ Подпишись на канал: {CHANNEL_URL}")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH); res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone(); v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(message.text, v_id).save(path)
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ АУДИО", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer("✅ Ваша озвучка готова:", reply_markup=kb.as_markup())
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

# --- ВСПОМОГАТЕЛЬНЫЕ ЭНДПОИНТЫ ---
@app.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request): return templates.TemplateResponse(request, "premium.html")

@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_gen_page(request: Request): return templates.TemplateResponse(request, "admin_generate.html")

@app.post("/api/verify-key")
async def verify_key(data: KeyCheck):
    if data.key.upper() in [k.upper() for k in PREMIUM_KEYS]: return {"success": True}
    return {"success": False}

@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str, key: str = None):
    if key and key.upper() in [k.upper() for k in PREMIUM_KEYS]:
        if os.path.exists(os.path.join(AUDIO_DIR, file)):
            return FileResponse(path=os.path.join(AUDIO_DIR, file), filename="speechclone.mp3")
    return templates.TemplateResponse(request, "wait_page.html", {"file_url": f"/download?file={file}"})

@app.get("/download")
async def download_file(file: str):
    path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(path): return FileResponse(path=path, filename="speechclone.mp3")
    return HTMLResponse("Файл не найден.", status_code=404)

@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    reply = await mm.generate(req.message)
    return {"reply": reply}

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(r.text, r.voice).save(path)
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e: return JSONResponse(status_code=500, content={"detail": str(e)})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))


