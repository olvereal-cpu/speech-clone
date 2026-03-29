import os
import uuid
import asyncio
import sqlite3
import edge_tts
import urllib.parse
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
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- ИНИЦИАЛИЗАЦИЯ GEMINI 3.1 FLASH-LITE ---
class ModelManager:
    def __init__(self, api_key):
        self.api_key = api_key
        # Возвращаем 3.1 Flash-Lite
        self.target_model = 'gemini-3.1-flash-lite-preview'
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        genai.configure(api_key=self.api_key)
        self.active_model = genai.GenerativeModel(
            model_name=self.target_model, 
            safety_settings=self.safety_settings
        )

    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.active_model.generate_content, prompt)
            return resp.text if resp else "Ошибка: ИИ не вернул ответ"
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ГЕНЕРАТОР КАРТИНОК (UNSPLASH + GEMINI KEYWORDS) ---
class NanoBananaImageEngine:
    async def get_image(self, topic: str) -> str:
        try:
            # Используем ИИ для генерации точных тегов под тему статьи
            prompt = f"Generate 3 simple English keywords for high-quality photography search related to: {topic}. Output ONLY keywords separated by commas."
            keywords = await mm.generate(prompt)
            clean_k = keywords.replace(" ", "").strip()
            return f"https://source.unsplash.com/featured/800x600?{urllib.parse.quote(clean_k)}"
        except:
            # Запасная картинка, если что-то пошло не так
            return "https://images.unsplash.com/photo-1614064641935-4476e83bb023"

image_engine = NanoBananaImageEngine()

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- ПОЛНЫЙ СПИСОК ГОЛОСОВ ---
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", 
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Айгуль": "kk-KZ-AigulNeural", 
    "🇰🇿 Даулет": "kk-KZ-DauletNeural",
    "🇺🇸 Jenny": "en-US-JennyNeural", 
    "🇺🇸 Guy": "en-US-GuyNeural", 
    "🇺🇸 Aria": "en-US-AriaNeural",
    "🇺🇦 Поліна": "uk-UA-PolinaNeural", 
    "🇺🇦 Остап": "uk-UA-OstapNeural",
    "🇹🇷 Турецкий": "tr-TR-EmelNeural", 
    "🇩🇪 Немецкий": "de-DE-KatjaNeural",
    "🇫🇷 Французский": "fr-FR-DeniseNeural", 
    "🇪🇸 Испанский": "es-ES-ElviraNeural", 
    "🇵🇱 Польский": "pl-PL-ZofiaNeural"
}

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    
    # Миграция для старых БД
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(posts)")
    cols = [c[1] for c in cursor.fetchall()]
    if 'category' not in cols: conn.execute("ALTER TABLE posts ADD COLUMN category TEXT DEFAULT 'Технологии'")
    if 'color' not in cols: conn.execute("ALTER TABLE posts ADD COLUMN color TEXT DEFAULT 'blue'")
    
    conn.commit()
    conn.close()

init_db()

# --- ЛОГИКА ТЕЛЕГРАМ-БОТА ---
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
    await message.answer("👋 **Добро пожаловать в SpeechClone!**\nВыберите голос и пришлите текст для озвучки:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def send_invoice(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Поддержка", description="Покупка 50 Stars", payload="stars", currency="XTR", prices=[LabeledPrice(label="Stars", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id))
    conn.commit(); conn.close()
    await call.message.answer("✅ Голос успешно выбран!")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/") or (message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id)):
        return await message.answer(f"❌ Для работы нужно подписаться на канал: {CHANNEL_ID}")
    
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
    v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
    
    fid = f"{uuid.uuid4()}.mp3"
    path = os.path.join(AUDIO_DIR, fid)
    
    try:
        await edge_tts.Communicate(message.text, v_id).save(path)
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ АУДИО", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer("✅ Ваше аудио готово!", reply_markup=kb.as_markup())
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {e}")

# --- FASTAPI ПРИЛОЖЕНИЕ ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class AdminGenRequest(BaseModel): 
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

class TTSRequest(BaseModel): 
    text: str; voice: str; mode: str; key: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 20').fetchall(); conn.close()
    return templates.TemplateResponse(request, "index.html", {"posts": [dict(p) for p in db_posts]})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        # Улучшенный промпт для качественного текста (AdSense Friendly)
        prompt = (
            f"Напиши профессиональную статью на тему: '{req.message}'. "
            "Пиши как эксперт-человек. Избегай типичных вступительных фраз ИИ. "
            "Формат ответа строго по маркерам:\n"
            "TITLE: [заголовок]\n"
            "EXCERPT: [краткий анонс для превью, около 15 слов]\n"
            "CONTENT: [основной текст статьи в HTML разметке с тегами <p>, <b>, <ul>, <li>]"
        )
        
        raw_res = await mm.generate(prompt)
        img_url = await image_engine.get_image(req.message)
        
        # Разбор ответа ИИ
        res_title = raw_res.split("TITLE:")[1].split("EXCERPT:")[0].strip()
        res_excerpt = raw_res.split("EXCERPT:")[1].split("CONTENT:")[0].strip()
        res_content = raw_res.split("CONTENT:")[1].strip().replace("```html", "").replace("```", "")
        
        new_slug = f"post-{uuid.uuid4().hex[:8]}"
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''INSERT INTO posts (title, slug, image, excerpt, content, date, author, category, color) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (res_title, new_slug, img_url, res_excerpt, res_content, 
                      datetime.now().strftime("%d.%m.%Y"), "Алексей Редактор", req.category, req.color))
        conn.commit(); conn.close()
        
        return {"status": "success", "slug": new_slug}
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    post = conn.execute('SELECT * FROM posts WHERE slug = ?', (slug,)).fetchone(); conn.close()
    if not post: raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "blog_index.html", {"posts": [dict(post)], "is_single": True})

@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str):
    return templates.TemplateResponse(request, "wait_page.html", {"file_url": f"/download?file={file}"})

@app.get("/download")
async def download_file(file: str):
    path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(path): return FileResponse(path=path, filename="speechclone.mp3")
    return HTMLResponse("Файл не найден.", status_code=404)

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        await edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%")).save(path)
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e: 
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))


