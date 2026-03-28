import os
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
LI_COUNTER = '<a href="https://www.liveinternet.ru/click" target="_blank"><img src="https://counter.yadro.ru/logo?27.1" title="LiveInternet" alt="" border="0" width="88" height="31"/></a>'

# Настройка Gemini - ОБНОВЛЕНО до 2.0
genai.configure(api_key=GEMINI_API_KEY)
model_ai = genai.GenerativeModel('gemini-2.0-flash')

# Данные блога
BLOG_POSTS = [
    {"id": 1, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", "excerpt": "Разбираемся в будущем клонирования...", "content": "Полный текст статьи о будущем ИИ-голосов...", "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue"},
    {"id": 2, "title": "Секреты идеального подкаста", "slug": "sekrety-sozdaniya-podkasta-ii", "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", "excerpt": "Автоматизация монтажа...", "content": "Как использовать ИИ для обработки звука в подкастах...", "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple"},
    {"id": 3, "title": "ИИ в аудиокнигах", "slug": "ii-v-obrazovanii-audioknigi", "image": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?q=80&w=800", "excerpt": "Революция в обучении...", "content": "Озвучка книг стала доступнее благодаря нейросетям...", "date": "05.03.2026", "author": "С. Адамс", "category": "Образование", "color": "green"},
    {"id": 4, "title": "Как нейронки понимают текст", "slug": "how-it-works", "image": "https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800", "excerpt": "Технический разбор...", "content": "Разбираем архитектуру трансформеров на пальцах...", "date": "01.03.2026", "author": "Д. Тэч", "category": "Разработка", "color": "indigo"},
    {"id": 5, "title": "Озвучка на 20+ языках", "slug": "multilanguage-update", "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800", "excerpt": "Глобальное обновление...", "content": "Теперь наш сервис поддерживает редкие диалекты...", "date": "28.02.2026", "author": "К. Ли", "category": "Глобал", "color": "green"},
    {"id": 6, "title": "Будущее подкастов", "slug": "podcast-future", "image": "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?q=80&w=800", "excerpt": "Куда движется индустрия...", "content": "Интерактивные подкасты станут нормой в ближайшие годы...", "date": "25.02.2026", "author": "Р. Грей", "category": "Тренды", "color": "purple"},
    {"id": 7, "title": "YouTube без микрофона", "slug": "youtube-voiceover", "image": "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=800", "excerpt": "Кейсы создания видео...", "content": "Как делать качественный контент, имея только текст...", "date": "22.02.2026", "author": "В. Кей", "category": "YouTube", "color": "red"},
    {"id": 8, "title": "Как выбрать ИИ-голос", "slug": "kak-vybrat-ii-golos", "image": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?q=80&w=800", "excerpt": "Советы по подбору...", "content": "Критерии выбора идеального тембра для вашего проекта...", "date": "20.02.2026", "author": "М. Рид", "category": "Советы", "color": "blue"}
]

VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural", "🇺🇸 Guy (EN)": "en-US-GuyNeural"
}

# --- ПУТИ И БД ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

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
    await message.answer("👋 Привет! Выбери голос:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_id = VOICES.get(call.data.replace("v_", ""), "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id))
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Голос изменен!")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться", url=CHANNEL_URL))
        return await message.answer("⚠️ Сначала подпишись!", reply_markup=kb.as_markup())
    
    msg = await message.answer("⏳ Генерирую...")
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
        v_id = res[0] if res else "ru-RU-DmitryNeural"
        conn.close()
        
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        comm = edge_tts.Communicate(message.text, v_id)
        await comm.save(path)
        await message.answer_voice(voice=FSInputFile(path))
        await msg.delete()
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Отдаем только первые 8 постов на главную
    return templates.TemplateResponse("index.html", {
        "request": request, "posts": BLOG_POSTS[:8], "li_counter": LI_COUNTER
    })

# ИСПРАВЛЕНО: Маршрут блога должен быть ВЫШЕ catch_all
@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    return templates.TemplateResponse("blog_index.html", {
        "request": request, "posts": BLOG_POSTS, "is_single": False, "li_counter": LI_COUNTER
    })

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404)
    return templates.TemplateResponse("blog_index.html", {
        "request": request, "posts": [post], "is_single": True, "li_counter": LI_COUNTER
    })

# ИСПРАВЛЕНО: Чат-бот API
@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    try:
        # Принудительно вызываем генерацию через потоки, чтобы не блокировать event loop
        response = await asyncio.to_thread(model_ai.generate_content, req.message)
        # Gemini 2.0 возвращает объект, текст берем через .text
        return {"reply": response.text}
    except Exception as e:
        print(f"Gemini Error: {e}")
        return JSONResponse(status_code=500, content={"reply": "Бро, я приуныл. Попробуй позже."})

@app.post("/api/generate")
async def generate(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        comm = edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%"))
        await comm.save(path)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

# ИСПРАВЛЕНО: Роут для скачивания (чтобы не качало HTML)
@app.get("/download")
async def download_file(file: str):
    file_path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="speechclone.mp3", media_type='audio/mpeg')
    return HTMLResponse("Файл потерялся", status_code=404)

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try: 
        return templates.TemplateResponse(f"{page}.html", {"request": request, "li_counter": LI_COUNTER})
    except: 
        return templates.TemplateResponse("index.html", {"request": request, "posts": BLOG_POSTS[:8], "li_counter": LI_COUNTER})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))



