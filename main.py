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
ADMIN_ID = 430747895
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_API_KEY = "AIzaSyCQ3JD4Fot7wV3oVklOxPU96jH6sNDoIoE"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
# Убрал лишние пробелы в адресе
SITE_URL = "https://speechclone.online" 

# Счетчик LiveInternet
LI_COUNTER = '<a href="https://www.liveinternet.ru/click" target="_blank"><img src="https://counter.yadro.ru/logo?27.1" title="LiveInternet" alt="" border="0" width="88" height="31"/></a>'

# Настройка Gemini 3.1 Flash-Lite
genai.configure(api_key=GEMINI_API_KEY)
model_ai = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

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
        "id": 1, 
        "title": "Как ИИ изменит ваш голос в 2026 году", 
        "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", 
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства с человеческим голосом...</p>", 
        "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue"
    },
    {
        "id": 2, 
        "title": "Секреты идеального подкаста", 
        "slug": "sekrety-sozdaniya-podkasta-ii", 
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", 
        "excerpt": "Автоматизация монтажа...", 
        "content": "<p>Создание подкаста всегда было трудоемким процессом. В 2026 году ИИ берет на себя 80% рутины.</p>", 
        "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple"
    },
    {
        "id": 3, 
        "title": "ИИ в аудиокнигах", 
        "slug": "ii-v-obrazovanii-audioknigi", 
        "image": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?q=80&w=800", 
        "excerpt": "Революция в обучении...", 
        "content": "<p>Озвучка книг стала доступнее благодаря нейросетям.</p>", 
        "date": "05.03.2026", "author": "С. Адамс", "category": "Образование", "color": "green"
    },
    {
        "id": 4, 
        "title": "Как нейронки понимают текст", 
        "slug": "how-it-works", 
        "image": "https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800", 
        "excerpt": "Технический разбор...", 
        "content": "<p>Архитектура трансформеров перевернула мир ИИ.</p>", 
        "date": "01.03.2026", "author": "Д. Тэч", "category": "Разработка", "color": "indigo"
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
    for name in VOICES.keys():
        kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="🌟 Купить Stars", callback_data="buy_stars"))
    await message.answer("👋 Выбери голос и пришли текст для озвучки:", reply_markup=kb.as_markup())

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
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id))
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Голос установлен!")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        return await message.answer(f"⚠️ Подпишись на наш канал, чтобы пользоваться ботом:\n{CHANNEL_URL}")
    
    status_msg = await message.answer("⏳ Создаю аудио, подождите...")
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
        v_id = res[0] if res else "ru-RU-DmitryNeural"
        conn.close()
        
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        comm = edge_tts.Communicate(message.text, v_id)
        await comm.save(path)
        
        # Ссылка на страницу ожидания
        download_link = f"{SITE_URL}/wait-download?file={fid}"
        
        kb = InlineKeyboardBuilder()
        kb.button(text="📥 СКАЧАТЬ ФАЙЛ", url=download_link)
        
        await message.answer(f"✅ Аудио готово! Для скачивания перейдите по ссылке (нужно подождать 30 секунд):", reply_markup=kb.as_markup())
        await status_msg.delete()
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str
class AdminGenRequest(BaseModel): message: str

# --- МАРШРУТЫ САЙТА ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, name="index.html", context={"posts": BLOG_POSTS[:8], "li_counter": LI_COUNTER})

@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str):
    # Эта страница рендерит таймер и рекламу
    file_url = f"/download?file={file}"
    return templates.TemplateResponse(request, name="wait_page.html", context={"file_url": file_url, "li_counter": LI_COUNTER})

@app.get("/download")
async def download_file(file: str):
    file_path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="speechclone.mp3", media_type='audio/mpeg')
    return HTMLResponse("Файл не найден. Попробуйте создать его заново.", status_code=404)

@app.post("/api/admin/generate-post")
async def admin_generate_post(req: AdminGenRequest):
    try:
        prompt = f"Напиши статью для блога на тему: {req.message}. Стиль: экспертный, но доступный. Оформи в HTML (только теги p). Верни JSON: title, content, excerpt, category."
        response = await asyncio.to_thread(model_ai.generate_content, prompt)
        
        new_id = len(BLOG_POSTS) + 1
        new_post = {
            "id": new_id,
            "title": req.message,
            "slug": f"post-{new_id}",
            "image": "https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800",
            "excerpt": "Автоматически сгенерировано нейросетью Gemini 3.1 Flash-Lite.",
            "content": response.text,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "author": "AI Admin",
            "category": "ИИ",
            "color": "blue"
        }
        BLOG_POSTS.insert(0, new_post)
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    try:
        response = await asyncio.to_thread(model_ai.generate_content, req.message)
        return {"reply": response.text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"reply": f"Ошибка ИИ: {str(e)}"})

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        comm = edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%"))
        await comm.save(path)
        # Для веб-версии возвращаем URL страницы ожидания
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    return templates.TemplateResponse(request, name="blog_index.html", context={"posts": BLOG_POSTS, "is_single": False, "li_counter": LI_COUNTER})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404, detail="Статья не найдена")
    return templates.TemplateResponse(request, name="blog_index.html", context={"posts": [post], "is_single": True, "li_counter": LI_COUNTER})

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    template_file = f"{page}.html"
    if os.path.exists(os.path.join(TEMPLATE_DIR, template_file)):
        return templates.TemplateResponse(request, name=template_file, context={"li_counter": LI_COUNTER})
    return templates.TemplateResponse(request, name="index.html", context={"posts": BLOG_POSTS[:8], "li_counter": LI_COUNTER})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))



