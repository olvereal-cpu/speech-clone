import os
import uuid
import asyncio
import sqlite3
import json
import edge_tts
import google.generativeai as genai
import re
import markdown
import random
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


def slugify(text: str) -> str:
    """Конвертирует русский текст в транслит для ЧПУ-ссылок"""
    chars = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
   }
    text = text.lower().strip()
    result = "".join(chars.get(c, c) for c in text)
    result = re.sub(r'[^a-z0-9]+', '-', result)
    return result.strip('-')

def clean_html(raw_html: str) -> str:
    """Удаляет теги для анонса"""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY")

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- ИНИЦИАЛИЗАЦИЯ GEMINI ---
class ModelManager:
    def __init__(self, api_key):
        self.api_key = api_key
        self.target_model = 'gemini-3.1-flash-lite-preview' # Использование стабильной версии
        genai.configure(api_key=self.api_key)
        self.active_model = genai.GenerativeModel(model_name=self.target_model)

    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.active_model.generate_content, prompt)
            return resp.text if resp else "Ошибка: ИИ не вернул ответ"
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
BLOG_FOLDER = os.path.join(BASE_DIR, "blog") # Папка для ваших 15 статей
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(BLOG_FOLDER, exist_ok=True)

# --- ВСТРОЕННЫЕ ПОСТЫ ---
BLOG_POSTS = [
    {
        "id": 1001, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue",
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства...</p>"
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

# --- БД ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БЛОГА ---
def get_all_blog_posts():
    posts = []
    # 1. Читаем файлы из папки blog
    if os.path.exists(BLOG_FOLDER):
        files = [f for f in os.listdir(BLOG_FOLDER) if f.endswith(".html")]
        for f in files:
            try:
                with open(os.path.join(BLOG_FOLDER, f), 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                if len(lines) >= 3:
                    title = lines[0].strip()
                    image = lines[1].strip()
                    # Собираем ВЕСЬ остальной текст (не только одну строку)
                    content_html = "".join(lines[2:]).strip()
                    
                    posts.append({
                        "title": title,
                        "image": image,
                        "content": content_html,
                        "excerpt": clean_html(content_html)[:160] + "...",
                        "slug": f.replace(".html", ""),
                        "date": "20.03.2026", "author": "Admin", "category": "AI", "color": "purple"
                    })
            except Exception as e:
                print(f"Ошибка чтения {f}: {e}")
    
    # 2. Из базы данных
    try:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        db_posts = [dict(p) for p in conn.execute('SELECT * FROM posts ORDER BY id DESC').fetchall()]
        conn.close()
    except: db_posts = []
    
    # Склеиваем: Файлы + БД + Встроенные
    return posts + db_posts + BLOG_POSTS

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
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 Купить Stars", callback_data="buy_stars"))
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
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR REPLACE INTO users (user_id, voice) VALUES (?, ?)', (call.from_user.id, v_id))
    conn.commit()
    conn.close()
    await call.message.answer("✅ Голос установлен!")
    await call.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/") or (message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id)): return
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
        v_id = res[0] if res else "ru-RU-DmitryNeural"
        conn.close()
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        await edge_tts.Communicate(message.text, v_id).save(path)
        kb = InlineKeyboardBuilder().button(text="📥 СКАЧАТЬ", url=f"{SITE_URL}/wait-download?file={fid}")
        await message.answer("✅ Готово!", reply_markup=kb.as_markup())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# --- МОДЕЛИ ДАННЫХ (ИСПРАВЛЕНО: KeyCheck теперь тут) ---
class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str; key: Optional[str] = None
class KeyCheck(BaseModel): key: str
class AdminGenRequest(BaseModel): 
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

# --- МАРШРУТЫ САЙТА ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    all_posts = get_all_blog_posts()
    # Берем первые 6 для главной
    return templates.TemplateResponse(
    request=request, 
    name="index.html", 
    context={"posts": all_posts[:6]}
)

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    all_posts = get_all_blog_posts()
    return templates.TemplateResponse(
    request=request, 
    name="blog_index.html", 
    context={"posts": all_posts, "is_single": False}
)

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    all_posts = get_all_blog_posts()
    post = next((p for p in all_posts if p["slug"] == slug), None)
    if not post: raise HTTPException(status_code=404)
    
    content = post["content"]
    
    # Очеловечивание: Добавляем блок автора в конец, если его нет
    if "Автор статьи" not in content:
        content += f"""
        <div style="background: #f0f7ff; border-left: 5px solid #007bff; padding: 15px; margin-top: 30px; border-radius: 8px;">
            <strong>💡 Мнение эксперта:</strong> Технологии клонирования голоса развиваются быстрее, чем мы думали. Главное — использовать их во благо. А что думаете вы? Напишите нам в <a href="{CHANNEL_ID}">Telegram</a>!
        </div>
        """
    post["content"] = content

    return templates.TemplateResponse(
        request=request, 
        name="blog_index.html", 
        context={"posts": [post], "is_single": True}
    )

# --- ГЕНЕРАЦИЯ СТАТЕЙ (SEO + IMAGE) ---
@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        # Промпт с жестким уклоном в SEO и человеческий стиль
        prompt = f"""
        Напиши экспертную, глубокую и человечную статью на тему: {req.message}.
        
        ТРЕБОВАНИЯ К СТИЛЮ:
        - Никакой "воды" и шаблонных фраз вроде "в современном мире".
        - Используй сторителлинг: начни с реальной проблемы или интригующего факта.
        - Обращайся к читателю на "вы", задавай риторические вопросы.
        - Чередуй короткие и длинные предложения (создавай ритм текста).
        - Добавь немного юмора или уместной иронии.
        
        SEO-ПАРАМЕТРЫ:
        - Заголовок (Title) должен содержать ключевое слово и быть кликабельным (Clickbait-style, но честный).
        - Используй подзаголовки <h2> с ключевыми словами.
        - Добавь в текст LSI-фразы (тематические слова, связанные с {req.message}).
        - В конце статьи обязательно добавь блок "Часто задаваемые вопросы" (FAQ) в формате <h3>.

        Верни ответ СТРОГО в формате JSON:
        {{
          "title": "Заголовок статьи",
          "excerpt": "Мета-описание (150-160 символов) для поисковиков, которое заставляет кликнуть.",
          "content": "HTML-текст: вступление, <h2> подзаголовки с эмодзи, списки <ul>, акценты <strong>, FAQ блок и заключение с призывом.",
          "photo_keywords": "3-4 английских слова через запятую для максимально точного поиска фото"
        }}
        """
        raw_res = await mm.generate(prompt)
        # Очистка JSON от Markdown-разметки
        clean_json = re.sub(r'```json|```', '', raw_res).strip()
        data = json.loads(clean_json)
        
        # Генерация уникального слаг-имени
        slug_name = slugify(data['title'])
        
        # --- Запасные варианты тем (упростил до 2 слов для стабильности) ---
        fallback_themes = [
            'technology,ai',
            'cyberpunk,digital',
            'office,people',
            'microphone,studio',
            'brain,minimalist',
            'success,mountain',
            'soundwave,abstract'
        ]
        
        # Выбираем случайную тему, если ИИ подвел
        default_keywords = random.choice(fallback_themes)
        
        # Получаем ключи от ИИ
        raw_keywords = data.get('photo_keywords', default_keywords)
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: 
        # 1. Разбиваем по запятой. 2. Убираем лишние пробелы. 3. Берем только первые 2-3 слова.
        keyword_list = [k.strip() for k in raw_keywords.split(',') if k.strip()]
        keywords_url = ",".join(keyword_list[:3]) # LoremFlickr любит не более 3 тегов
        
        # Используем random.randint для lock, чтобы всегда получать число > 0
        img_id = random.randint(1, 9999)
        
        # Финальная ссылка (теперь она максимально чистая)
        img_url = f"https://loremflickr.com/800/600/{keywords_url}?lock={img_id}"
        
        # Сохранение (теперь сохраняем и excerpt для SEO-превью)
        file_path = os.path.join(BLOG_FOLDER, f"{slug_name}.html")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{data['title']}\n")
            f.write(f"{img_url}\n")
            f.write(f"{data.get('excerpt', '')}\n")
            f.write(f"{data['content']}")
         return {"status": "success", "url": f"/blog/{slug_name}"}
        except Exception as e:
        print(f"Ошибка генерации: {e}")
        return JSONResponse(status_code=500, content={"error": "Ошибка при создании статьи. Попробуйте другой запрос."})

# --- ОСТАЛЬНЫЕ РОУТЫ (БЕЗ ИЗМЕНЕНИЙ) ---
@app.get("/voices", response_class=HTMLResponse)
async def voices_page(request: Request): return templates.TemplateResponse(request=request, name="voices.html")

@app.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request):
    return templates.TemplateResponse(request=request, name="premium.html")

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="about.html")

@app.get("/guide", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="guide.html")

@app.get("/privacy", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html")

@app.get("/disclaimer", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="disclaimer.html")

@app.get("/guide", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="guide.html")

@app.get("/admin/generate", response_class=HTMLResponse)
async def admin_gen_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin_generate.html")

@app.post("/api/verify-key")
async def verify_key(data: KeyCheck):
    is_valid = data.key.upper() in [k.upper() for k in PREMIUM_KEYS]
    return {"success": is_valid}
    
@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str):
    return templates.TemplateResponse(request=request, name="wait_page.html", context={"file": file})

@app.get("/download")
async def download_file(file: str):
    path = os.path.join(AUDIO_DIR, file)
    return FileResponse(path=path, filename="speechclone.mp3") if os.path.exists(path) else HTMLResponse("404")

@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    reply = await mm.generate(req.message)
    return {"reply": reply}

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        await edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%")).save(path)
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
        
@app.on_event("startup")
async def startup_event():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)')
    conn.commit(); conn.close()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))































