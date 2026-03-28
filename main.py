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
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"

# --- ДАННЫЕ БЛОГА ---
BLOG_POSTS = [
    {
        "id": 1,
        "title": "Как ИИ изменит ваш голос в 2026 году: от клонирования до эмоций",
        "slug": "kak-ii-izmenit-vash-golos",
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800",
        "excerpt": "Разбираемся, почему в этом году ваш цифровой двойник будет звучать убедительнее, чем вы сами.",
        "content": "Текст статьи о будущем клонирования голоса и эмоциональном интеллекте нейросетей...",
        "date": "10.02.2026", "author": "Алекс Грей", "category": "Технологии", "color": "blue"
    },
    {
        "id": 2,
        "title": "Секреты создания идеального подкаста с помощью ИИ",
        "slug": "sekrety-sozdaniya-podkasta-ii",
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800",
        "excerpt": "Как автоматизировать монтаж и озвучку подкастов.",
        "content": "Подробный гайд по использованию ИИ в подкастинге...",
        "date": "08.02.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple"
    },
    {
        "id": 3,
        "title": "ИИ в аудиокнигах: Как обучать тысячи людей одновременно",
        "slug": "ii-v-obrazovanii-audioknigi",
        "image": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?q=80&w=800",
        "excerpt": "Революция в образовательном контенте через автоматическую озвучку.",
        "content": "Использование синтеза речи для создания курсов и книг...",
        "date": "05.02.2026", "author": "С. Адамс", "category": "Образование", "color": "green"
    },
    {
        "id": 4,
        "title": "За кулисами: Как нейронки «понимают» ваш текст",
        "slug": "how-it-works",
        "image": "https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800",
        "excerpt": "Технический разбор работы алгоритмов обработки естественного языка.",
        "content": "Разбор архитектуры трансформеров и акустических моделей...",
        "date": "01.02.2026", "author": "Д. Тэч", "category": "Разработка", "color": "indigo"
    },
    {
        "id": 5,
        "title": "Озвучка на 20+ языках: Глобальный апдейт",
        "slug": "multilanguage-update",
        "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800",
        "excerpt": "Наш сервис теперь говорит на мировых языках с идеальным акцентом.",
        "content": "Список новых языков и улучшенных моделей...",
        "date": "28.01.2026", "author": "К. Ли", "category": "Глобал", "color": "green"
    },
    {
        "id": 6,
        "title": "Будущее подкастов и роль нейросетей",
        "slug": "podcast-future",
        "image": "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?q=80&w=800",
        "excerpt": "Куда движется индустрия аудио-контента в ближайшие 5 лет.",
        "content": "Тренды аудио-рынка и роль ИИ в них...",
        "date": "25.01.2026", "author": "Р. Грей", "category": "Тренды", "color": "purple"
    },
    {
        "id": 7,
        "title": "YouTube-революция без микрофона",
        "slug": "youtube-voiceover",
        "image": "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=800",
        "excerpt": "Как создавать контент для видеохостингов, не имея дорогого оборудования.",
        "content": "Кейсы успешных каналов с ИИ-озвучкой...",
        "date": "22.01.2026", "author": "В. Кей", "category": "YouTube", "color": "red"
    },
    {
        "id": 8,
        "title": "Как выбрать идеальный ИИ-голос",
        "slug": "kak-vybrat-ii-golos",
        "image": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?q=80&w=800",
        "excerpt": "Советы по подбору тембра и скорости для разных типов контента.",
        "content": "Психология восприятия голоса слушателем...",
        "date": "20.01.2026", "author": "М. Рид", "category": "Советы", "color": "blue"
    },
    {
        "id": 9,
        "title": "Будущее голосовых ассистентов",
        "slug": "buduschee-golosovyh-assistentov",
        "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=800",
        "excerpt": "От простых команд к полноценному общению.",
        "content": "Разбор новых LLM моделей для ассистентов...",
        "date": "18.01.2026", "author": "А. Хопп", "category": "Будущее", "color": "orange"
    },
    {
        "id": 10,
        "title": "От текста к живому аудио за 5 минут",
        "slug": "ot-teksta-k-zvuku",
        "image": "https://images.unsplash.com/photo-1484662020986-75935d2ebc66?q=80&w=800",
        "excerpt": "Пошаговый гайд по быстрой генерации контента.",
        "content": "Инструкция по работе с API и веб-интерфейсом...",
        "date": "15.01.2026", "author": "Т. Свифт", "category": "Гайды", "color": "cyan"
    },
    {
        "id": 11,
        "title": "5 необычных применений ИИ-озвучки",
        "slug": "top-5-primenenii-ii-ozvuchki",
        "image": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=800",
        "excerpt": "От озвучки старых писем до помощи людям с нарушениями речи.",
        "content": "Креативные способы использования TTS технологий...",
        "date": "12.01.2026", "author": "Б. Смарт", "category": "Разное", "color": "pink"
    },
    {
        "id": 12,
        "title": "ИИ-озвучка для кратного роста аудитории",
        "slug": "ii-ozvuchka-dlya-blogerov",
        "image": "https://images.unsplash.com/photo-1533750349088-cd871a92f311?q=80&w=800",
        "excerpt": "Как масштабировать личный бренд через аудио-платформы.",
        "content": "Маркетинговая стратегия для blogerov в 2026 году...",
        "date": "10.01.2026", "author": "Э. Миллер", "category": "Блогинг", "color": "yellow"
    },
    {
        "id": 13,
        "title": "Этические вопросы и безопасность голоса",
        "slug": "eticheskie-voprosy-ii-golosov",
        "image": "https://images.unsplash.com/photo-1507146426996-ef05306b995a?q=80&w=800",
        "excerpt": "Deepfakes, авторские права и защита вашего цифрового тембра.",
        "content": "Правовые аспекты использования нейросетевых голосов...",
        "date": "08.01.2026", "author": "Х. Шмидт", "category": "Этика", "color": "slate"
    },
    {
        "id": 14,
        "title": "Локализация контента: Выход на мир с ИИ",
        "slug": "lokalizatsiya-kontenta-ii",
        "image": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?q=80&w=800",
        "excerpt": "Как переводить и озвучивать курсы на десятки языков без переводчиков.",
        "content": "Экономика локализации и примеры внедрения...",
        "date": "05.01.2026", "author": "Л. Карсон", "category": "Бизнес", "color": "indigo"
    },
    {
        "id": 15,
        "title": "Жасанды интеллект қазақ тілінде: Жаңа мүмкіндіктер",
        "slug": "ii-kazakh-language",
        "image": "https://images.unsplash.com/photo-1489749798305-4fea3ae63d43?q=80&w=800",
        "excerpt": "Қазақ тіліндегі контентті дамытуға арналған жаңа құралдар.",
        "content": "Қазақ тіліндегі нейрондық желілердің дамуы...",
        "date": "11.02.2026", "author": "А. Серік", "category": "Қазақ тілі", "color": "blue"
    }
]

VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural",
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural",
    "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural",
    "🇺🇦 Остап (UA)": "uk-UA-OstapNeural",
    "🇹🇷 Ahmet (TR)": "tr-TR-AhmetNeural",
    "🇪🇸 Alvaro (ES)": "es-ES-AlvaroNeural",
    "🇩🇪 Conrad (DE)": "de-DE-ConradNeural",
    "🇵🇱 Marek (PL)": "pl-PL-MarekNeural",
    "🇫🇷 Remy (FR)": "fr-FR-RemyNeural",
    "🇯🇵 Keita (JP)": "ja-JP-KeitaNeural",
    "🇨🇳 Yunxi (CN)": "zh-CN-YunxiNeural"
}

# --- ИНИЦИАЛИЗАЦИЯ ИИ ---
google.generativeai.configure(api_key=GEMINI_API_KEY)
model_ai = google.generativeai.GenerativeModel('gemini-1.5-flash')

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
    for name in VOICES.keys():
        kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2)
    await message.answer("👋 Привет! Выбери язык озвучки кнопкой ниже и пришли текст.", reply_markup=kb.as_markup())

@dp.message(Command("stars"))
async def cmd_stars(message: types.Message):
    await message.answer("🌟 Спасибо за поддержку! Если вам нравится сервис, вы можете отправить Telegram Stars. Это помогает нам развиваться.")

@dp.message(Command("export"))
async def cmd_export(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    file_path = os.path.join(BASE_DIR, "users.txt")
    with open(file_path, "w") as f:
        for u in users:
            f.write(f"{u[0]}\n")
            
    await message.answer_document(FSInputFile(file_path), caption=f"📊 Список пользователей (всего: {len(users)})")
    if os.path.exists(file_path):
        os.remove(file_path)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    await message.answer(f"📊 Всего пользователей: {count}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID or not command.args: return
    conn = sqlite3.connect(DB_PATH)
    users = [row[0] for row in conn.execute('SELECT user_id FROM users').fetchall()]
    conn.close()
    done = 0
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            done += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена: {done}/{len(users)}")

@dp.callback_query(F.data.startswith("v_"))
async def set_voice(call: types.CallbackQuery):
    v_name = call.data.replace("v_", "")
    v_id = VOICES.get(v_name, "ru-RU-DmitryNeural")
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE users SET voice = ? WHERE user_id = ?', (v_id, call.from_user.id))
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
        return await message.answer("⚠️ Озвучка доступна только подписчикам канала!", reply_markup=kb.as_markup())

    add_user(uid)
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
        await message.answer_voice(voice=types.FSInputFile(path))
        await msg.delete()
    except Exception as e:
        await message.answer(f"Ошибка озвучки: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class ChatRequest(BaseModel):
    message: str

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Ограничиваем вывод на главную до первых 8 статей
    display_posts = BLOG_POSTS[:8]
    return templates.TemplateResponse(name="index.html", context={"request": request, "posts": display_posts})

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_blog(request: Request, slug: str):
    post = next((p for p in BLOG_POSTS if p["slug"] == slug), None)
    if not post:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return templates.TemplateResponse(name="blog.html", context={"request": request, "post": post})

@app.post("/api/chat")
async def chat(r: ChatRequest):
    try:
        response = await asyncio.to_thread(model_ai.generate_content, r.message)
        if response and response.text:
            return {"reply": response.text}
        else:
            return {"reply": "ИИ не смог сгенерировать ответ. Попробуйте другой запрос."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"reply": "Ошибка соединения с ИИ."})

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
        return JSONResponse(status_code=500, content={"detail": f"Ошибка: {e}"})

@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try:
        return templates.TemplateResponse(name=f"{page}.html", context={"request": request})
    except:
        return templates.TemplateResponse(name="index.html", context={"request": request, "posts": BLOG_POSTS[:8]})

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))
