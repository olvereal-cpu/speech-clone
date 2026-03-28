import os
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"

# --- ДАННЫЕ БЛОГА (15 СТАТЕЙ) ---
BLOG_POSTS = [
    {"id": 1, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", "excerpt": "Разбираемся в будущем клонирования...", "content": "Текст статьи...", "date": "10.02.2026", "author": "Алекс Грей", "category": "Технологии", "color": "blue"},
    {"id": 2, "title": "Секреты идеального подкаста", "slug": "sekrety-sozdaniya-podkasta-ii", "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", "excerpt": "Автоматизация монтажа...", "content": "Текст статьи...", "date": "08.02.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple"},
    {"id": 3, "title": "ИИ в аудиокнигах", "slug": "ii-v-obrazovanii-audioknigi", "image": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?q=80&w=800", "excerpt": "Революция в обучении...", "content": "Текст статьи...", "date": "05.02.2026", "author": "С. Адамс", "category": "Образование", "color": "green"},
    {"id": 4, "title": "Как нейронки понимают текст", "slug": "how-it-works", "image": "https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800", "excerpt": "Технический разбор...", "content": "Текст статьи...", "date": "01.02.2026", "author": "Д. Тэч", "category": "Разработка", "color": "indigo"},
    {"id": 5, "title": "Озвучка на 20+ языках", "slug": "multilanguage-update", "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800", "excerpt": "Глобальное обновление...", "content": "Текст статьи...", "date": "28.01.2026", "author": "К. Ли", "category": "Глобал", "color": "green"},
    {"id": 6, "title": "Будущее подкастов", "slug": "podcast-future", "image": "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?q=80&w=800", "excerpt": "Куда движется индустрия...", "content": "Текст статьи...", "date": "25.01.2026", "author": "Р. Грей", "category": "Тренды", "color": "purple"},
    {"id": 7, "title": "YouTube без микрофона", "slug": "youtube-voiceover", "image": "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=800", "excerpt": "Кейсы создания видео...", "content": "Текст статьи...", "date": "22.01.2026", "author": "В. Кей", "category": "YouTube", "color": "red"},
    {"id": 8, "title": "Как выбрать ИИ-голос", "slug": "kak-vybrat-ii-golos", "image": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?q=80&w=800", "excerpt": "Советы по подбору тембра...", "content": "Текст статьи...", "date": "20.01.2026", "author": "М. Рид", "category": "Советы", "color": "blue"},
    {"id": 9, "title": "Голосовые ассистенты", "slug": "buduschee-golosovyh-assistentov", "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=800", "excerpt": "От команд к общению...", "content": "Текст статьи...", "date": "18.01.2026", "author": "А. Хопп", "category": "Будущее", "color": "orange"},
    {"id": 10, "title": "От текста к аудио за 5 минут", "slug": "ot-teksta-k-zvuku", "image": "https://images.unsplash.com/photo-1484662020986-75935d2ebc66?q=80&w=800", "excerpt": "Быстрая генерация...", "content": "Текст статьи...", "date": "15.01.2026", "author": "Т. Свифт", "category": "Гайды", "color": "cyan"},
    {"id": 11, "title": "5 применений ИИ-озвучки", "slug": "top-5-primenenii-ii-ozvuchki", "image": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=800", "excerpt": "Необычные способы...", "content": "Текст статьи...", "date": "12.01.2026", "author": "Б. Смарт", "category": "Разное", "color": "pink"},
    {"id": 12, "title": "Рост аудитории с ИИ", "slug": "ii-ozvuchka-dlya-blogerov", "image": "https://images.unsplash.com/photo-1533750349088-cd871a92f311?q=80&w=800", "excerpt": "Масштабирование бренда...", "content": "Текст статьи...", "date": "10.01.2026", "author": "Э. Миллер", "category": "Блогинг", "color": "yellow"},
    {"id": 13, "title": "Этика и безопасность", "slug": "eticheskie-voprosy-ii-golosov", "image": "https://images.unsplash.com/photo-1507146426996-ef05306b995a?q=80&w=800", "excerpt": "Deepfakes и защита...", "content": "Текст статьи...", "date": "08.01.2026", "author": "Х. Шмидт", "category": "Этика", "color": "slate"},
    {"id": 14, "title": "Локализация контента", "slug": "lokalizatsiya-kontenta-ii", "image": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?q=80&w=800", "excerpt": "Выход на мир с ИИ...", "content": "Текст статьи...", "date": "05.01.2026", "author": "Л. Карсон", "category": "Бизнес", "color": "indigo"},
    {"id": 15, "title": "ИИ на казахском языке", "slug": "ii-kazakh-language", "image": "https://images.unsplash.com/photo-1489749798305-4fea3ae63d43?q=80&w=800", "excerpt": "Жаңа мүмкіндіктер...", "content": "Текст статьи...", "date": "11.02.2026", "author": "А. Серік", "category": "Қазақ тілі", "color": "blue"}
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

# --- ИНИЦИАЛИЗАЦИЯ ИИ (Gemini 2.5 Flash) ---
google.generativeai.configure(api_key=GEMINI_API_KEY)
model_ai = google.generativeai.GenerativeModel('gemini-2.5-flash')

# --- ПУТИ И БД ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static/audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")
os.makedirs(AUDIO_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.commit()
    conn.close()

def add_user(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (uid,))
    conn.commit()
    conn.close()

init_db()

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
    add_user(message.from_user.id)
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2)
    await message.answer("👋 Привет! Выбери голос кнопкой и пришли текст.", reply_markup=kb.as_markup())

@dp.message(Command("stars"))
async def cmd_stars(message: types.Message):
    await message.answer("🌟 **Поддержка проекта**\n\nВы можете поддержать сервис отправив Telegram Stars. Это поможет нам добавлять новые голоса и улучшать качество озвучки!")

@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    file_path = os.path.join(BASE_DIR, "users.txt")
    with open(file_path, "w") as f:
        for u in users: f.write(f"{u[0]}\n")
    await message.answer_document(FSInputFile(file_path), caption=f"📊 Список пользователей (всего: {len(users)})")
    if os.path.exists(file_path): os.remove(file_path)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    await message.answer(f"📊 Всего в базе: {count}")

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_name = call.data.replace("v_", "")
    v_id = VOICES.get(v_name, "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id))
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Голос изменен на: {v_name}")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться", url=CHANNEL_URL))
        return await message.answer("⚠️ Подпишитесь на канал для доступа!", reply_markup=kb.as_markup())

    msg = await message.answer("⏳ Генерирую...")
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (uid,)).fetchone()
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
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"posts": BLOG_POSTS[:8]})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_blog(request: Request, slug: str):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="blog.html", context={"post": post})

# Универсальный роут для остальных страниц (о нас, услуги и т.д.)
@app.get("/{page}", response_class=HTMLResponse)
async def get_page(request: Request, page: str):
    try:
        return templates.TemplateResponse(request=request, name=f"{page}.html", context={})
    except:
        return templates.TemplateResponse(request=request, name="index.html", context={"posts": BLOG_POSTS[:8]})

@app.post("/api/chat")
async def chat(r: ChatRequest):
    try:
        response = await asyncio.to_thread(model_ai.generate_content, r.message)
        return {"reply": response.text}
    except Exception:
        return JSONResponse(status_code=500, content={"reply": "Ошибка ИИ."})

@app.on_event("startup")
async def startup_event():
    # Очистка вебхуков для предотвращения ConflictError
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)

