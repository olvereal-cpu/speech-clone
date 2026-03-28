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
# Берем ключ именно из GEMINI_KEY, как указано на Render
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- ИНИЦИАЛИЗАЦИЯ GEMINI (ПРЯМАЯ УСТАНОВКА 3.1 FLASH LITE) ---
class ModelManager:
    def __init__(self, api_key):
        self.api_key = api_key
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
            return resp.text
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)

# --- ДАННЫЕ БЛОГА (ПОЛНЫЕ СТАТЬИ) ---
BLOG_POSTS = [
    {
        "id": 1001, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue",
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства с человеческим голосом. Раньше ИИ звучал роботоподобно, но теперь нейросети учитывают даже микро-интонации, задержки дыхания и эмоциональный фон. <b>Клонирование голоса</b> стало доступным каждому пользователю смартфона.</p><p>Основной прорыв произошел в области <i>Zero-shot TTS</i>, где системе достаточно всего 3 секунд записи вашего голоса, чтобы воспроизвести любую фразу с вашим тембром на 50 языках мира.</p>"
    },
    {
        "id": 1002, "title": "Секреты идеального подкаста", "slug": "sekrety-sozdaniya-podkasta-ii", 
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", 
        "excerpt": "Автоматизация монтажа с помощью ИИ.", "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple",
        "content": "<p>Создание подкаста всегда было трудоемким процессом. Нужно арендовать студию, бороться с шумами и часами монтировать дорожки. В 2026 году всё изменилось.</p><p>Используя <b>SpeechClone</b>, авторы могут записывать сценарий текстом, а ИИ озвучивает его идеальным студийным голосом. Больше не нужно переписывать дубли, если вы ошиблись в слове — просто исправьте текст в редакторе.</p>"
    },
    {
        "id": 1003, "title": "Клонирование голоса: Этика и закон", "slug": "ethics-of-voice-cloning", 
        "image": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?q=80&w=800", 
        "excerpt": "Где грань между инновацией и кражей личности?", "date": "05.03.2026", "author": "Юрист ИИ", "category": "Право", "color": "red",
        "content": "<p>С ростом популярности дипфейков юридические системы стран мира начали активно внедрять законы о <b>цифровой личности</b>. Теперь ваш голос — это ваша собственность, защищенная законом так же, как и отпечатки пальцев. Использование чужого голоса без лицензии преследуется по закону.</p>"
    },
    {
        "id": 1004, "title": "Топ 10 голосов для рекламы", "slug": "top-10-voices-ad", 
        "image": "https://images.unsplash.com/photo-1478737270239-2fccd2c7fd94?q=80&w=800", 
        "excerpt": "Какие тембры продают лучше всего?", "date": "01.03.2026", "author": "Маркетолог", "category": "Маркетинг", "color": "green",
        "content": "<p>Исследования показывают, что выбор правильного голоса увеличивает конверсию рекламы на 40%. В 2026 году нейромаркетинг выделил фаворитов: <b>бархатистые низкие мужские голоса</b> вызывают доверие в финансовом секторе.</p>"
    },
    {
        "id": 1005, "title": "Озвучка книг: Новая эра", "slug": "audiobook-new-era", 
        "image": "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?q=80&w=800", 
        "excerpt": "Как за неделю озвучить целую серию романов.", "date": "25.02.2026", "author": "Книжник", "category": "Литература", "color": "yellow",
        "content": "<p>Раньше на озвучку одной книги уходил месяц работы диктора. Сегодня автор может загрузить текст в <b>SpeechClone</b>, выбрать несколько голосов для разных персонажей и получить готовую аудиокнигу за пару часов.</p>"
    },
    {
        "id": 1006, "title": "ИИ в видеоиграх: Живые диалоги", "slug": "ai-in-gaming", 
        "image": "https://images.unsplash.com/photo-1542751371-adc38448a05e?q=80&w=800", 
        "excerpt": "NPC, которые действительно говорят с вами.", "date": "20.02.2026", "author": "Геймер", "category": "Игры", "color": "indigo",
        "content": "<p>Представьте игру, где каждый персонаж — это не просто набор записанных фраз, а живой собеседник. В 2026 году крупные студии перешли на динамическую генерацию речи с помощью ИИ.</p>"
    },
    {
        "id": 1007, "title": "Как работает Edge TTS?", "slug": "how-edge-tts-works", 
        "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=800", 
        "excerpt": "Технический разбор движка от Microsoft.", "date": "15.02.2026", "author": "Разработчик", "category": "Технологии", "color": "gray",
        "content": "<p>Edge TTS — это один из самых стабильных движков на рынке. Он использует нейронные сети для предсказания спектрограмм звука на основе текстовых токенов через WebSocket.</p>"
    },
    {
        "id": 1008, "title": "Психология восприятия голоса", "slug": "psychology-of-voice", 
        "image": "https://images.unsplash.com/photo-1526256262350-7da7584cf5eb?q=80&w=800", 
        "excerpt": "Почему мы доверяем одним голосам и боимся других.", "date": "10.02.2026", "author": "Доктор Пси", "category": "Наука", "color": "pink",
        "content": "<p>Голос несет в себе больше информации, чем слова. Мы подсознательно считываем уверенность, доброту или агрессию по частотным характеристикам звука.</p>"
    },
    {
        "id": 1009, "title": "ИИ-переводчики с сохранением голоса", "slug": "voice-translation", 
        "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800", 
        "excerpt": "Говорите на китайском своим собственным голосом.", "date": "05.02.2026", "author": "Лингвист", "category": "Технологии", "color": "orange",
        "content": "<p>Языковой барьер окончательно разрушен. Современные системы синхронного перевода не только заменяют слова, но и <b>клонируют ваш тембр</b> на лету.</p>"
    },
    {
        "id": 1010, "title": "Заработок на озвучке в 2026", "slug": "money-on-voice", 
        "image": "https://images.unsplash.com/photo-1554224155-169641357599?q=80&w=800", 
        "excerpt": "Как фрилансеры используют ИИ для дохода.", "date": "01.02.2026", "author": "Бизнес-аналитик", "category": "Бизнес", "color": "emerald",
        "content": "<p>Рынок дикторских услуг трансформировался. Успешные фрилансеры теперь не просто читают текст, а создают цифровые слепки голоса и продают лицензии.</p>"
    },
    {
        "id": 1011, "title": "Музыка и ИИ: Вокал без певца", "slug": "ai-vocals-music", 
        "image": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?q=80&w=800", 
        "excerpt": "Как создаются хиты с виртуальными вокалистами.", "date": "28.01.2026", "author": "Продюсер", "category": "Музыка", "color": "rose",
        "content": "<p>В чартах 2026 года всё чаще появляются песни, вокал в которых полностью сгенерирован. Продюсеры могут «нанять» виртуальную версию легендарных певцов.</p>"
    },
    {
        "id": 1012, "title": "Будущее радио: ИИ-ведущие", "slug": "future-radio-ai", 
        "image": "https://images.unsplash.com/photo-1485579149621-3123dd979885?q=80&w=800", 
        "excerpt": "Радиостанции, работающие полностью на нейросетях.", "date": "20.01.2026", "author": "Радиофан", "category": "Медиа", "color": "cyan",
        "content": "<p>Традиционное радио уступает место персонализированным станциям. ИИ-ведущий знает ваши музыкальные вкусы и читает новости специально для вас.</p>"
    },
    {
        "id": 1013, "title": "Кибербезопасность: Дипфейки", "slug": "cybersec-deepfakes", 
        "image": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=800", 
        "excerpt": "Как защитить себя от голосового мошенничества.", "date": "15.01.2026", "author": "Хакер", "category": "Безопасность", "color": "slate",
        "content": "<p>К сожалению, технологии клонирования голоса используют и преступники. Телефонное мошенничество вышло на новый уровень. Используйте кодовые слова для семьи.</p>"
    },
    {
        "id": 1014, "title": "ИИ для людей с потерей речи", "slug": "ai-for-disability", 
        "image": "https://images.unsplash.com/photo-1516542077369-6de03c158542?q=80&w=800", 
        "excerpt": "Возвращение голоса тем, кто его потерял.", "date": "10.01.2026", "author": "Врач", "category": "Медицина", "color": "teal",
        "content": "<p>Это самое благородное применение ИИ. Пациенты с заболеваниями связок теперь могут общаться с миром своим настоящим голосом через нейросети.</p>"
    },
    {
        "id": 1015, "title": "Эволюция интерфейсов: Голос вместо рук", "slug": "voice-interfaces", 
        "image": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?q=80&w=800", 
        "excerpt": "Почему в 2026 году мы перестанем печатать.", "date": "05.01.2026", "author": "Футуролог", "category": "Будущее", "color": "violet",
        "content": "<p>Клавиатуры становятся пережитком прошлого. Благодаря идеальному распознаванию и синтезу речи, взаимодействие с техникой стало естественным диалогом.</p>"
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
    return templates.TemplateResponse(request, "index.html", {"posts": all_posts[:15]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    db_posts = conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall(); conn.close()
    all_posts = [dict(p) for p in db_posts] + BLOG_POSTS
    return templates.TemplateResponse(request, "blog_index.html", {"posts": all_posts, "is_single": False})

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        # 1. Улучшенный промпт (просим ИИ не использовать разметку Markdown)
        prompt = (
            f"Напиши информативную статью на тему: {req.message}. "
            "Используй только HTML теги <p>, <b>, <i>. "
            "ВАЖНО: Не пиши слово 'html', не используй обратные кавычки ```. "
            "Просто текст статьи."
        )
        
        # 2. Получаем ответ
        raw_text = await mm.generate(prompt)
        
        # 3. Жесткая очистка контента от мусора
        clean_content = raw_text.replace("```html", "").replace("```", "").strip()
        
        # 4. Генерируем данные для вставки
        post_title = req.message
        post_slug = f"post-{uuid.uuid4().hex[:8]}"
        post_date = datetime.now().strftime("%d.%m.%Y")
        # Ставим дефолтную картинку, если в запросе нет своей
        post_image = "[https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800](https://images.unsplash.com/photo-1614064641935-4476e83bb023?q=80&w=800)"
        
        # 5. Запись в БД с использованием контекстного менеджера (безопасно)
        with sqlite3.connect(DB_PATH, timeout=20) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO posts 
                (title, slug, image, excerpt, content, date, author, category, color) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_title, 
                post_slug, 
                post_image, 
                "Статья создана нейросетью Gemini 3.1 Flash-Lite.", 
                clean_content, 
                post_date, 
                "AI Editor", 
                req.category, 
                req.color
            ))
            conn.commit()
            
        print(f"--- Статья успешно создана: {post_title} ---")
        return {"status": "success", "slug": post_slug}
        
    except Exception as e:
        # Печатаем ошибку в логи Render, чтобы ты мог ее прочитать
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА ГЕНЕРАЦИИ: {str(e)}")
        return JSONResponse(
            status_code=500, 
            content={"status": "error", "message": f"Ошибка на стороне сервера: {str(e)}"}
        )

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
        reply = await mm.generate(req.message)
        return {"reply": reply}
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
    return templates.TemplateResponse(request, "index.html", {"posts": all_posts[:15]})

@app.on_event("startup")
async def startup_event():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))

