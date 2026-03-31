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
import requests
import urllib.parse
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from supabase import create_client, Client
from slugify import slugify

SUPABASE_URL = "https://zbcpntzpnkhpzlwextbn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpiY3BudHpwbmtocHpsd2V4dGJuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4MjM2NjIsImV4cCI6MjA5MDM5OTY2Mn0.MP7pnt_pTx0Am1Str1yTwR4UYagjyQM5Bk3jC8javdM"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

# --- СОСТОЯНИЯ И КЛАВИАТУРА АДМИНА ---
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

def get_admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="📥 Выгрузка базы (txt)", callback_data="admin_export")
    return kb.adjust(1).as_markup()

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
    # Регистрируем пользователя в базе, если его там нет (для рассылки)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,))
    conn.commit()
    conn.close()

    # Проверка обязательной подписки
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.button(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")
        kb.button(text="🔄 Проверить подписку", callback_data="sub_check_done")
        return await message.answer("⚠️ Для использования бота необходимо подписаться на наш канал!", reply_markup=kb.adjust(1).as_markup())

    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")
    kb.adjust(2).row(types.InlineKeyboardButton(text="🌟 На кофе", callback_data="buy_stars"))
    await message.answer("👋 Выбери голос и пришли текст:", reply_markup=kb.as_markup())

# --- АДМИН-ФУНКЦИИ ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ Панель администратора:", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    await call.message.answer(f"📈 Всего пользователей в базе: {count}")
    await call.answer()

@dp.callback_query(F.data == "admin_export")
async def admin_export(call: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute('SELECT user_id, voice FROM users').fetchall()
    conn.close()
    
    file_path = "users_db.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("ID пользователя | Голос\n" + "-"*30 + "\n")
        for u in users:
            f.write(f"{u[0]} | {u[1]}\n")
    
    await call.message.answer_document(types.FSInputFile(file_path), caption="📂 Выгрузка базы")
    os.remove(file_path)
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📝 Отправьте сообщение для рассылки (текст, фото или видео):")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await call.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def broadcast_process(message: types.Message, state: FSMContext):
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    ok, err = 0, 0
    await message.answer(f"🚀 Рассылка запущена на {len(users)} чел...")
    
    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            ok += 1
            await asyncio.sleep(0.05) # Защита от Flood-лимитов
        except:
            err += 1
            
    await message.answer(f"✅ Рассылка завершена!\n\nДоставлено: {ok}\nНе удалось: {err}")
    await state.clear()

@dp.callback_query(F.data == "sub_check_done")
async def sub_check_done(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await cmd_start(call.message)
    else:
        await call.answer("❌ Вы всё еще не подписаны!", show_alert=True)

# --- ИСХОДНЫЕ ОБРАБОТЧИКИ ---

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
    try:
        res = supabase.table("posts").select("*").order("created_at", desc=True).limit(6).execute()
        all_posts = res.data if res.data else []
        
        # ПЕРВЫМ аргументом идет request, ВТОРЫМ — имя шаблона, ТРЕТЬИМ — словарь данных
        return templates.TemplateResponse(
            request, 
            "index.html", 
            {"posts": all_posts}
        )
    except Exception as e:
        print(f"Ошибка на главной: {e}")
        return templates.TemplateResponse(
            request, 
            "index.html", 
            {"posts": []}
        )

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    try:
        # Берем данные ТОЛЬКО из Supabase
        res = supabase.table("posts").select("*").order("created_at", desc=True).execute()
        all_posts = res.data if res.data else []
        
        return templates.TemplateResponse(
            request, 
            "blog_index.html", 
            {"posts": all_posts, "is_single": False}
        )
    except Exception as e:
        print(f"Ошибка списка блога: {e}")
        return templates.TemplateResponse(
            request, "blog_index.html", {"posts": [], "is_single": False}
        )

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    try:
        # Ищем в Supabase
        res = supabase.table("posts").select("*").eq("slug", slug).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="Статья не найдена")
            
        post = res.data[0]
        
        # Добавляем "Мнение эксперта" (если его нет)
        if "Мнение эксперта" not in post.get("content", ""):
            post["content"] = post.get("content", "") + f"""
            <div style="background: #f0f7ff; border-left: 5px solid #007bff; padding: 15px; margin-top: 30px; border-radius: 8px;">
                <strong>💡 Мнение эксперта:</strong> Технологии клонирования голоса — это наше будущее.
            </div>
            """

        # ВАЖНО: используем blog_index.html, так как post.html у тебя нет!
        return templates.TemplateResponse(
            request, 
            "blog_index.html", 
            {
                "posts": [post], # Шаблон ждет список
                "is_single": True
            }
        )
    except Exception as e:
        print(f"Ошибка чтения статьи {slug}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

# --- ГЕНЕРАЦИЯ СТАТЕЙ (SEO + IMAGE) ---      

async def api_admin_gen(
    req: AdminGenRequest, 
    x_secret_key: str = Header(None)
):
    # ПАРОЛЬ
    MY_SECRET = "Barakuda"

    if x_secret_key != MY_SECRET:
        print(f"🚫 Попытка несанкционированного доступа!")
        raise HTTPException(status_code=403, detail="Доступ запрещен")
        
    try:
        # --- 0. ЛОГИКА АВТОПИЛОТА / РУЧНОГО ВВОДА ---
        target_topic = req.message.strip()
        
        if not target_topic or target_topic.lower() in ["авто", "auto", ".", "начни"]:
            print("🤖 Режим автопилота: придумываю хайповую IT-тему...")
            niches = [
                "Глубокая разработка: Python, FastAPI, микросервисы и чистая архитектура",
                "AI для бизнеса: RAG-системы, автоматизация саппорта и внедрение LLM в рабочие процессы",
                "Инструментарий профи: Секреты Cursor, VS Code, продвинутый промпт-инжиниринг и AI-кодинг",
                "DevOps и Cloud: Развертывание в Docker, облака Render/Vercel и магия Supabase",
                "IT-стратегия: Анализ трендов 2026, личный опыт выживания в индустрии, найм и карьера",
                "Лайфхаки и продуктивность: Как разработчику успевать всё, автоматизировать рутину и не выгорать"
            ]
            
            current_niche = random.choice(niches)
            
            topic_prompt = f"""
            Ты — главный редактор топового IT-издания. Придумай ОДНУ конкретную, экспертную и актуальную тему.
            Направление: {current_niche}.
            Тема должна решать реальную проблему (например: 'Как я ускорил API в 10 раз' или 'Почему ваш ИИ-бот тупит').
            Ответь ТОЛЬКО текстом заголовка без кавычек.
            """
            
            # Генерация через Gemini 3.1
            generated_topic = await mm.generate(topic_prompt)
            target_topic = generated_topic.strip().replace('"', '')
        
        print(f"📝 Генерация статьи по теме: {target_topic}")

        # --- 1. ФОРМИРОВАНИЕ ГИБРИДНОГО ПРОМПТА (ТВОЙ SEO + МОЙ КОНТЕКСТ) ---
        prompt = f"""
        Напиши экспертную, глубокую и человечную статью на тему: {target_topic}.
        
        ТРЕБОВАНИЯ К СТИЛЮ:
        - Никакой "воды" и шаблонных фраз вроде "в современном мире".
        - Используй сторителлинг: начни с реальной проблемы или интригующего факта.
        - Обращайся к читателю на "вы", задавай риторические вопросы.
        - Чередуй короткие и длинные предложения (создавай ритм текста).
        - Добавь немного юмора или уместной иронии.
        
        SEO-ПАРАМЕТРЫ:
        - Заголовок (Title) должен содержать ключевое слово и быть кликабельным (Clickbait-style, но честный).
        - Используй подзаголовки <h2> с ключевыми словами и эмодзи.
        - Добавь в текст LSI-фразы (тематические слова, связанные с {target_topic}).
        - В конце статьи обязательно добавь блок "Часто задаваемые вопросы" (FAQ) в формате <h3>.

        !!! ВАЖНО: ОФОРМЛЕНИЕ МНЕНИЯ ЭКСПЕРТА !!!
        В самом конце статьи добавь блок "Мнение эксперта", оформив его СТРОГО в следующем HTML-виде:
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border-left: 4px solid #8b5cf6; padding: 25px; margin: 40px 0; border-radius: 12px; box-shadow: 0 0 20px rgba(139, 92, 246, 0.15); color: #e2e8f0; font-family: sans-serif;">
          <h4 style="margin-top: 0; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px; font-size: 14px; margin-bottom: 12px; display: flex; align-items: center;">
            <span style="margin-right: 8px;">⚡</span> Мнение эксперта
          </h4>
          <p style="font-style: italic; line-height: 1.6; margin-bottom: 0; color: #cbd5e1;">
            [Здесь текст мнения, СТРОГО релевантный теме "{target_topic}"]
          </p>
        </div>
        
        Верни ответ СТРОГО в формате JSON:
        {{
          "title": "Заголовок статьи",
          "excerpt": "Мета-описание (150-160 символов) для поисковиков, которое заставляет кликнуть.",
          "content": "HTML-текст: вступление, <h2> подзаголовки с эмодзи, списки <ul>, акценты <strong>, FAQ блок и заключение с призывом.",
          "photo_keywords": "3-4 английских слова через запятую для максимально точного поиска фото на тему {target_topic}"
        }}
        """
        
        # 2. ГЕНЕРАЦИЯ КОНТЕНТА
        raw_res = await mm.generate(prompt)
        
        # --- ЗАЩИТА ОТ ОШИБКИ JSON ---
        try:
            # Gemini часто оборачивает JSON в блоки кода ```json ... ```, убираем их
            json_str = re.search(r'\{.*\}', raw_res, re.DOTALL).group(0)
            data = json.loads(json_str)
        except Exception as e:
            print(f"❌ ОШИБКА JSON ПАРСИНГА: {e}")
            data = {
                "title": target_topic, 
                "photo_keywords": "it, technology, digital", 
                "content": f"<p>{raw_res}</p>", # Записываем как есть, если JSON не удался
                "excerpt": "Интересная статья о современных IT-технологиях."
            }
        
        # 3. ПОДГОТОВКА СЛАГА И ФОТО
        final_title = data.get('title', target_topic)
        slug_name = slugify(final_title)
        
        # PEXELS API
        PEXELS_KEY = "rzdmYACqPHYAjdHRDipCFPM40aUMJOPP5Lo8mKvX1VUQCRvdQUC38yYn"
        raw_keywords = data.get('photo_keywords', 'technology')
        search_term = urllib.parse.quote(raw_keywords.replace(",", " "))
        
        img_url = "https://images.unsplash.com/photo-1614741118887-7a4ee193a5fa?q=80&w=1200"

        try:
            async with httpx.AsyncClient() as client:
                px_url = f"https://api.pexels.com/v1/search?query={search_term}&per_page=5&orientation=landscape"
                px_res = await client.get(px_url, headers={"Authorization": PEXELS_KEY}, timeout=10)
                if px_res.status_code == 200:
                    px_data = px_res.json()
                    if px_data.get('photos'):
                        img_url = random.choice(px_data['photos'])['src']['large']
                        print(f"✅ Фото успешно привязано: {img_url}")
        except Exception as img_err:
            print(f"⚠️ Ошибка Pexels: {img_err}")

        # 4. СОХРАНЕНИЕ В SUPABASE
        supabase.table("posts").insert({
            "title": final_title,
            "slug": slug_name,
            "image_url": img_url,
            "excerpt": data.get('excerpt', ''),
            "content": data.get('content', '')
        }).execute()

        return {"status": "success", "title": final_title, "slug": slug_name}

    except Exception as e:
        print(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        return {"status": "error", "message": str(e)}

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

@app.post("/chat")
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































