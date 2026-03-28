import os
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from datetime import datetime
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
# Исправляем здесь: читаем ту переменную, которая у тебя в системе
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 

if not BOT_TOKEN or not GEMINI_API_KEY:
    print(f"⚠️ ВНИМАНИЕ: Данные не получены! BOT_TOKEN: {'OK' if BOT_TOKEN else 'MISSING'}, GEMINI_KEY: {'OK' if GEMINI_API_KEY else 'MISSING'}")

# Инициализируем Google AI с ключом из GEMINI_KEY
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# Настройка Gemini с отключением фильтров контента
genai.configure(api_key=GEMINI_API_KEY)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
model_ai = genai.GenerativeModel('models/gemini-1.5-flash', safety_settings=safety_settings) 

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)

# --- ДАННЫЕ БЛОГА ---
BLOG_POSTS = [
    {
        "id": 1001, 
        "title": "Как ИИ изменит ваш голос в 2026 году", 
        "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", 
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства...</p>", 
        "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue"
    },
    {
        "id": 1002, 
        "title": "Секреты идеального подкаста", 
        "slug": "sekrety-sozdaniya-podkasta-ii", 
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", 
        "excerpt": "Автоматизация монтажа...", 
        "content": "<p>Создание подкаста всегда было трудоемким процессом...</p>", 
        "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple"
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
    conn.commit()
    conn.close()

init_db()

# --- БОТ ---
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
    await message.answer("👋 Выбери голос и пришли текст:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def send_invoice(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Поддержка", description="50 Stars", payload="stars", currency="XTR", prices=[LabeledPrice(label="Stars", amount=50)])
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH); conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id)); conn.commit(); conn.close()
    await call.message.answer("✅ Голос установлен!"); await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/") or (message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id)): return
    try:
        conn = sqlite3.connect(DB_PATH); res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone(); v_id = res[0] if res else "ru-RU-DmitryNeural"; conn.close()
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(message.text, v_id).save(path)
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer("✅ Готово!", reply_markup=kb.as_markup())
    except Exception as e: await message.answer(f"❌ Ошибка: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str; key: str = None
class KeyCheck(BaseModel): key: str
class AdminGenRequest(BaseModel): message: str; category: str; color: str

# --- МАРШРУТЫ САЙТА ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 20').fetchall(); conn.close()
    all_posts = [dict(p) for p in db_posts] + BLOG_POSTS
    return templates.TemplateResponse(request, "index.html", {"posts": all_posts[:12]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall(); conn.close()
    all_posts = [dict(p) for p in db_posts] + BLOG_POSTS
    return templates.TemplateResponse(request, "blog_index.html", {"posts": all_posts, "is_single": False})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        prompt = f"Напиши статью на тему: {req.message}. Формат HTML (только p, b, i). Не используй ```html, просто текст."
        response = await asyncio.to_thread(model_ai.generate_content, prompt)
        
        if not response or not response.text:
            raise Exception("ИИ вернул пустой ответ")

        content = response.text.replace("```html", "").replace("```", "").strip()

        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute('''INSERT INTO posts 
                        (title, slug, image, excerpt, content, date, author, category, color) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (req.message, f"post-{uuid.uuid4().hex[:6]}", 
                      "[https://images.unsplash.com/photo-1614064641935-4476e83bb023](https://images.unsplash.com/photo-1614064641935-4476e83bb023)", 
                      "Сгенерировано нейросетью", content, 
                      datetime.now().strftime("%d.%m.%Y"), "Gemini AI", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_post = conn.execute('SELECT * FROM posts WHERE slug = ?', (slug,)).fetchone(); conn.close()
    post = dict(db_post) if db_post else next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "blog_index.html", {"posts": [post], "is_single": True})

@app.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request):
    return templates.TemplateResponse(request, "premium.html")

@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_gen_page(request: Request):
    return templates.TemplateResponse(request, "admin_generate.html")

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
    try:
        response = await asyncio.to_thread(model_ai.generate_content, req.message)
        if response and response.candidates:
            return {"reply": response.text}
        return {"reply": "Не удалось получить ответ от ИИ."}
    except Exception as e: return {"reply": f"Ошибка: {e}"}

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"; path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        await edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%")).save(path)
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e: return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    template_file = f"{page}.html"
    if os.path.exists(os.path.join(TEMPLATE_DIR, template_file)):
        return templates.TemplateResponse(request, template_file)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC LIMIT 12').fetchall(); conn.close()
    all_posts = [dict(p) for p in db_posts] + BLOG_POSTS
    return templates.TemplateResponse(request, "index.html", {"posts": all_posts[:12]})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))


