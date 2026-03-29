import os
import uuid
import asyncio
import sqlite3
import re
import edge_tts
import markdown
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

# --- 2. GEMINI MANAGER ---
class ModelManager:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash') # Стабильная версия
        
    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.model.generate_content, prompt)
            return resp.text if resp else ""
        except Exception as e:
            print(f"Gemini Error: {e}")
            return ""

mm = ModelManager(GEMINI_API_KEY)

# --- 3. ДАННЫЕ И БД ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
BLOG_DIR = os.path.join(BASE_DIR, "blog")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)

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
    text = re.sub(r'[*_#]', '', text)
    res = re.sub(r'[^a-z0-9а-я]+', '-', text.lower()).strip('-')
    return res if len(res) > 2 else f"post-{uuid.uuid4().hex[:5]}"

def get_posts_from_folder():
    folder_posts = []
    if not os.path.exists(BLOG_DIR): return []
    
    files = [f for f in os.listdir(BLOG_DIR) if f.endswith((".html", ".txt", ".md"))]
    for fn in sorted(files, reverse=True):
        try:
            path = os.path.join(BLOG_DIR, fn)
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            slug = fn.rsplit(".", 1)[0]
            title = slug.replace("-", " ").replace("_", " ").replace("*", "").capitalize()
            content_html = markdown.markdown(raw) if not fn.endswith(".html") else raw
            excerpt = re.sub(r'<[^>]+>', '', content_html).replace("*", "").replace("#", "").strip()[:150] + "..."
            
            folder_posts.append({
                "title": title, "slug": slug, 
                "image": "https://images.unsplash.com/photo-1677442136019-21780ecad995?q=80&w=800",
                "excerpt": excerpt, "content": content_html, "date": "Архив", 
                "author": "Система", "category": "Блог", "color": "blue"
            })
        except: continue
    return folder_posts

def get_merged_posts():
    all_posts = []
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        db_data = conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall()
        all_posts = [dict(p) for p in db_data]; conn.close()
    except: pass
    all_posts += get_posts_from_folder()
    return all_posts

init_db()

# --- 4. ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 Купить Stars (50 XTR)", callback_data="buy_stars"))
    await message.answer("🤖 Выбери голос и отправь текст:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "buy_stars")
async def process_buy(call: types.CallbackQuery):
    await bot.send_invoice(call.message.chat.id, title="Донат", description="Поддержка", payload="xtr", currency="XTR", prices=[LabeledPrice(label="XTR", amount=50)])
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
    await message.answer_audio(audio=FSInputFile(path), reply_markup=InlineKeyboardBuilder().button(text="📥 Скачать", url=f"{SITE_URL}/wait-download?file={fid}").as_markup())

# --- 5. FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class ChatReq(BaseModel): message: str
class GenReq(BaseModel): message: str; category: str = "ИИ"; color: str = "blue"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    posts = get_merged_posts()
    return templates.TemplateResponse("index.html", {"request": request, "posts": posts[:12]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_all(request: Request):
    posts = get_merged_posts()
    return templates.TemplateResponse("blog_index.html", {"request": request, "posts": posts, "is_single": False})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_one(request: Request, slug: str):
    posts = get_merged_posts()
    p = next((x for x in posts if x['slug'] == slug), None)
    if not p: raise HTTPException(404)
    return templates.TemplateResponse("blog_index.html", {"request": request, "posts": [p], "is_single": True})

@app.post("/api/chat")
async def api_chat(req: ChatReq):
    if not req.message.strip(): return {"reply": "Чем могу помочь?"}
    ans = await mm.generate(f"Ты ИИ-ассистент SpeechClone. Ответь кратко на русском: {req.message}")
    return {"reply": ans or "ИИ временно недоступен."}

@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin_generate.html", {"request": request})

@app.post("/api/admin/generate-post")
async def api_gen(req: GenReq):
    prompt = f"Напиши SEO статью про {req.message}. Формат TITLE: текст без звезд KEYWORD: одно_слово CONTENT: текст"
    raw = await mm.generate(prompt)
    if not raw: return JSONResponse(status_code=500, content={"error": "No AI response"})
    try:
        title = re.search(r"TITLE:(.*?)(?=KEYWORD|CONTENT|$)", raw, re.S).group(1).replace("*", "").replace("#", "").strip()
        kw = re.search(r"KEYWORD:(.*?)(?=CONTENT|$)", raw, re.S).group(1).replace("*", "").strip()
        content_raw = raw.split("CONTENT:")[1].strip()
        content_html = markdown.markdown(content_raw)
        excerpt = re.sub(r'<[^>]+>', '', content_html).replace("*", "").replace("#", "").strip()[:150] + "..."
        slug = slugify(title)
        img = f"https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&q=80&w=800"
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO posts (title, slug, image, excerpt, content, date, author, category, color) VALUES (?,?,?,?,?,?,?,?,?)', 
                     (title, slug, img, excerpt, content_html, datetime.now().strftime("%d.%m.%Y"), "Gemini AI", req.category, req.color))
        conn.commit(); conn.close()
        return {"status": "success", "slug": slug}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/wait-download", response_class=HTMLResponse)
async def wait(request: Request, file: str):
    return templates.TemplateResponse("wait_page.html", {"request": request, "file_url": f"/download?file={file}"})

@app.get("/download")
async def dl(file: str):
    p = os.path.join(AUDIO_DIR, file)
    return FileResponse(p, filename="speechclone.mp3") if os.path.exists(p) else HTMLResponse("404", 404)

# ИСПРАВЛЕННЫЙ РОУТ СТАТИЧЕСКИХ СТРАНИЦ
@app.get("/{path}", response_class=HTMLResponse)
async def static_pages(request: Request, path: str):
    # Исключаем системные файлы (например favicon.ico), чтобы не было 500 ошибки
    if "." in path: raise HTTPException(404)
    
    valid = ["voices", "about", "guide", "privacy", "disclaimer", "faq", "premium", "contact", "instructions"]
    if path in valid:
        return templates.TemplateResponse(f"{path}.html", {"request": request})
    raise HTTPException(404)

@app.on_event("startup")
async def startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))



















