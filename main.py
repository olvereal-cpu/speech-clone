import os
import uuid
import asyncio
import sqlite3
import json
import httpx 
import edge_tts
import google.generativeai as genai
import re
import markdown
import random
import requests
import urllib.parse
import urllib.request
import logging
import math
import soundfile as sf
import mimetypes
from fastapi.responses import StreamingResponse, JSONResponse
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
from urllib.parse import quote

SUPABASE_URL = "https://zbcpntzpnkhpzlwextbn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpiY3BudHpwbmtocHpsd2V4dGJuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4MjM2NjIsImV4cCI6MjA5MDM5OTY2Mn0.MP7pnt_pTx0Am1Str1yTwR4UYagjyQM5Bk3jC8javdM"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# ССЫЛКА НА ТВОЙ API НА HUGGING FACE
HF_KOKORO_URL = "https://sercos-my-tts-api.hf.space/generate"
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


   # --- ЕДИНЫЙ КОНФИГ ГОЛОСОВ (БЕЗ ЛИШНИХ ТЕХНОЛОГИЙ) ---
VOICE_CONFIG = {
    # 🇰🇿 КАЗАХСТАН
    "kk": {"type": "new", "label": "🇰🇿 Казахский (Нейросеть HQ)"},
    "edge_kk_Aigul": {"type": "old", "id": "kk-KZ-AigulNeural", "label": "👧 Айгуль (Стандарт)"},
    "edge_kk_Daulet": {"type": "old", "id": "kk-KZ-DauletNeural", "label": "👦 Даулет (Стандарт)"},
    
    # 🌟 ПРЕМИУМ КЛОНЫ (HQ)
    "ru_oleg": {"type": "new", "label": "👤 Олег (Клон HQ)"},
    "ru_elena": {"type": "new", "label": "👩 Елена (Клон HQ)"},
    "af_sky": {"type": "new", "label": "✨ Sky (Женский HQ)"},
    "af_bella": {"type": "new", "label": "🌸 Bella (Женский HQ)"},
    "am_adam": {"type": "new", "label": "🔥 Adam (Мужской HQ)"},
    "bf_emma": {"type": "new", "label": "🇬🇧 Emma (British HQ)"},
    "bm_george": {"type": "new", "label": "🇬🇧 George (British HQ)"},
    
    # 🇷🇺 РУССКИЙ
    "ru": {"type": "new", "label": "🇷🇺 Русский (Нейросеть HQ)"},
    "edge_ru_Dmitry": {"type": "old", "id": "ru-RU-DmitryNeural", "label": "👨 Дмитрий"},
    "edge_ru_Svetlana": {"type": "old", "id": "ru-RU-SvetlanaNeural", "label": "👩 Светлана"},
    
    # 🌍 МИРОВЫЕ ЯЗЫКИ (NEW ENGINE)
    "en": {"type": "new", "label": "🇺🇸 English"},
    "uk": {"type": "new", "label": "🇺🇦 Українська"},
    "be": {"type": "new", "label": "🇧🇾 Беларуская"},
    "tr": {"type": "new", "label": "🇹🇷 Türkçe"},
    "de": {"type": "new", "label": "🇩🇪 Deutsch"},
    "fr": {"type": "new", "label": "🇫🇷 Français"},
    "pl": {"type": "new", "label": "🇵🇱 Polski"},
    "cs": {"type": "new", "label": "🇨🇿 Čeština"},
    "es": {"type": "new", "label": "🇪🇸 Español"},
    "it": {"type": "new", "label": "🇮🇹 Italiano"},
    "pt": {"type": "new", "label": "🇵🇹 Português"},
    "nl": {"type": "new", "label": "🇳🇱 Nederlands"},
    "sv": {"type": "new", "label": "🇸🇪 Svenska"},
    "da": {"type": "new", "label": "🇩🇰 Dansk"},
    "fi": {"type": "new", "label": "🇫🇮 Suomi"},
    "hu": {"type": "new", "label": "🇭🇺 Magyar"},
    "ro": {"type": "new", "label": "🇷🇴 Română"},
    "zh": {"type": "new", "label": "🇨🇳 中文 (Chinese)"},
    "ja": {"type": "new", "label": "🇯🇵 日本語 (Japanese)"},
    "ko": {"type": "new", "label": "🇰🇷 한국어 (Korean)"},
    "ar": {"type": "new", "label": "🇸🇦 العربية (Arabic)"},
    "hi": {"type": "new", "label": "🇮🇳 हिन्दी (Hindi)"}
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
    # 1. Регистрация в базе
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,))
    conn.commit()
    conn.close()

    # 2. Проверка подписки (если не админ)
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.button(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")
        kb.button(text="🔄 Проверить подписку", callback_data="sub_check_done")
        return await message.answer(
            "⚠️ **Для использования бота необходимо подписаться на наш канал!**", 
            parse_mode="Markdown", 
            reply_markup=kb.adjust(1).as_markup()
        )

    # 3. Если подписан — выводим красивое меню выбора голосов
    kb = InlineKeyboardBuilder()
    # Берем голоса из нашего общего словаря VOICES
    for name, v_id in VOICES.items():
        kb.button(text=name, callback_data=f"v_{v_id}")
    
    # Добавляем кнопку доната в конец
    kb.adjust(2).row(types.InlineKeyboardButton(text="☕ На кофе", callback_data="buy_stars"))
    
    welcome_text = (
        "👋 **Приветствуем в SpeechClone!**\n\n"
        "Выберите подходящий голос для озвучки:\n"
        "• 🌟 **Premium** — максимально живое звучание.\n"
        "• 🇷🇺/🇰🇿 **Стандарт** — классические голоса.\n\n"
        "**Просто отправьте текст** после выбора голоса, и я его озвучу."
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "sub_check_done")
async def sub_check_done(call: types.CallbackQuery):
    if await check_sub(call.from_user.id):
        await call.message.answer("✅ Спасибо за подписку! Теперь выберите голос в меню /start")
    else:
        await call.answer("❌ Вы еще не подписались!", show_alert=True)

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
# Роут для работы с твоим Hugging Face
# 1. Считываем токен из переменных окружения Render
# Он должен называться точно так же, как в Dashboard (HF_TOKEN)
HF_TOKEN = os.getenv("HF_TOKEN")
@app.post("/api/generate") # Это "вход" для твоего сайта
async def generate_proxy(request: Request):
    data = await request.json()
    text = data.get("text")
    voice = data.get("voice", "ru_v10_oleg")
    
    if not text:
        return JSONResponse(status_code=400, content={"detail": "Текст не введен"})

    file_name = f"voice_{uuid.uuid4().hex}.wav"
    file_path = os.path.join("static", file_name)

    async with httpx.AsyncClient() as client:
        try:
            # СТЫКОВКА: Здесь мы обращаемся к Хугану БЕЗ /api и через GET
            hf_url = "https://sercos-my-tts-api.hf.space/generate"
            
            headers = {"Authorization": f"Bearer {os.getenv('HF_TOKEN')}"}
            
            # ВНИМАНИЕ: Тут client.get — это "ключ", который открывает замок на Хугане
            response = await client.get(
                hf_url, 
                params={"text": text, "voice": voice}, 
                headers=headers, 
                timeout=120.0 
            )
            
            if response.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(response.content)
                return {"audio_url": f"/static/{file_name}"}
            else:
                return JSONResponse(status_code=response.status_code, content={"detail": f"Ошибка HF: {response.status_code}"})
                
        except Exception as e:
            return JSONResponse(status_code=500, content={"detail": str(e)})
# Это критично! Если поднять выше - будет "Not Found"

# 1. Подготовка окружения (не удалять!)
if not os.path.exists("static"):
    os.makedirs("static")

mimetypes.add_type('audio/mpeg', '.mp3')
mimetypes.add_type('audio/wav', '.wav')
app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        res = supabase.table("posts").select("*").order("created_at", desc=True).limit(6).execute()
        all_posts = res.data if res.data else []
        
        # ИСПРАВЛЕНО: Явное указание аргументов
        return templates.TemplateResponse(
            request=request, 
            name="index.html", 
            context={"posts": all_posts}
        )
    except Exception as e:
        print(f"Ошибка на главной: {e}")
        return templates.TemplateResponse(
            request=request, 
            name="index.html", 
            context={"posts": []}
        )
@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request, page: int = 1):
    try:
        limit = 6  
        start = (page - 1) * limit
        end = start + limit - 1

        res = supabase.table("posts") \
            .select("*", count="exact") \
            .order("created_at", desc=True) \
            .range(start, end) \
            .execute()
        
        all_posts = res.data if res.data else []
        total_posts = res.count if res.count else 0
        total_pages = math.ceil(total_posts / limit) if total_posts > 0 else 1
        
        # ИСПРАВЛЕНО: Убран "request" из словаря и вынесен в аргументы
        return templates.TemplateResponse(
            request=request,
            name="blog_index.html", 
            context={
                "posts": all_posts, 
                "is_single": False,
                "current_page": page,
                "total_pages": total_pages
            }
        )
    except Exception as e:
        print(f"Ошибка списка блога: {e}")
        return templates.TemplateResponse(
            request=request,
            name="blog_index.html", 
            context={
                "posts": [], 
                "is_single": False,
                "current_page": 1,
                "total_pages": 1
            }
        )

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    try:
        res = supabase.table("posts").select("*").eq("slug", slug).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="Статья не найдена")
            
        post = res.data[0]
        
        # ИСПРАВЛЕНО: Правильный формат вызова для одиночной статьи
        return templates.TemplateResponse(
            request=request,
            name="blog_index.html", 
            context={
                "posts": [post],
                "is_single": True,
                "current_page": 1, # Добавил, чтобы шаблон не ругался на отсутствие переменной
                "total_pages": 1
            }
        )
    except Exception as e:
        print(f"Ошибка чтения статьи {slug}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/sitemap.xml")
async def get_sitemap():
    try:
        # 1. Получаем данные из Supabase
        response = supabase.table("posts").select("slug").execute()
        posts = response.data
        
        # 2. ПРОПИШИ СВОЙ РЕАЛЬНЫЙ ДОМЕН ЗДЕСЬ (БЕЗ СЛЭША В КОНЦЕ)
        base_url = "https://speechclone.online" 

        # 3. Сборка XML
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            f'<url><loc>{base_url}/</loc><priority>1.0</priority></url>'
        ]

        for post in posts:
            slug = post.get('slug')
            if slug:
                # Формируем полную ссылку на статью
                xml_lines.append(f'<url><loc>{base_url}/blog/{slug}</loc><priority>0.8</priority></url>')

        xml_lines.append('</urlset>')
        
        return Response(content="".join(xml_lines), media_type="application/xml")

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        # Если база не отвечает, вернем хотя бы главную страницу, чтобы не было ошибки 500
        return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://speechclone.online/</loc></url></urlset>', media_type="application/xml")
# --- ГЕНЕРАЦИЯ СТАТЕЙ (SEO + IMAGE) ---      
@app.post("/api/admin/generate-post")
async def api_admin_gen(
    req: AdminGenRequest, 
    x_secret_key: str = Header(None)
):
    # 1. АВТОРИЗАЦИЯ
    MY_SECRET = "Barakuda"
    if x_secret_key != MY_SECRET:
        print(f"🚫 Попытка несанкционированного доступа!")
        raise HTTPException(status_code=403, detail="Доступ запрещен")
        
    try:
        # --- 0. ЛОГИКА АВТОПИЛОТА: ГЕНЕРАТОР УНИКАЛЬНЫХ СМЫСЛОВ ---
        target_topic = req.message.strip()

        if not target_topic or target_topic.lower() in ["авто", "auto", ".", "начни"]:
            print("🤖 Автопилот: создаю уникальный социальный инсайд...")
            niches = [
                "Цифровое бессмертие и трансформация личности",
                "Психология одиночества в эпоху алгоритмов",
                "Кибербезопасность семьи и кража личности через ИИ",
                "Воспитание детей и новые навыки для 2030 года",
                "Любовь, Tinder и цифровые суррогаты близости",
                "Биохакинг, чипы и слияние человека с кодом",
                "Экономика выживания: профессии, которые ИИ заберет завтра",
                "Ментальное здоровье и борьба с информационным шумом"
            ]
            selected_niche = random.choice(niches)
            
            topic_prompt = f"""
            Ты — главный редактор Esquire. Придумай провокационный заголовок для статьи.
            НИША: {selected_niche}
            ПРАВИЛА:
            - СТРОГО: от 3 до 6 слов. Без кавычек.
            - Тема должна быть про ЖИЗНЬ и ОБЩЕСТВО, а не про софт.
            - Это должен быть "крючок": страх, любопытство или инсайд.
            - Пример: 'Почему твой голос больше не твой', 'ИИ-няня: кто растит наших детей'.
            """
            generated_topic = await mm.generate(topic_prompt)
            target_topic = generated_topic.strip().replace('"', '').replace('.', '')

        print(f"📝 Тема: {target_topic}")

        # --- 1. ФОРМИРОВАНИЕ ГИБРИДНОГО ПРОМПТА (ПОЛНАЯ ВЕРСИЯ) ---
        prompt = f"""
        Напиши экспертную, глубокую и человечную статью на тему: {target_topic}.

        ТРЕБОВАНИЯ К СТИЛЮ:
        - Никакой "воды" и шаблонных фраз вроде "в современном мире".
        - Используй сторителлинг: начни с реальной проблемы или интригующего факта.
        - Обращайся к читателю на "вы", задавай риторические вопросы.
        - Чередуй короткие и длинные предложения (создавай ритм текста).
        - Добавь немного юмора или уместной иронии.
        
        SEO-ПАРАМЕТРЫ:
        - Используй подзаголовки <h2> с ключевыми словами и эмодзи.
        - В конце статьи обязательно добавь блок "Часто задаваемые вопросы" (FAQ) в формате <h3>.

        ВИЗУАЛЬНАЯ КОНЦЕПЦИЯ (поле photo_keywords):
        - СТРОГО ЗАПРЕЩЕНО использовать: 'computer', 'laptop', 'monitor', 'typing', 'office'.
        - ИСПОЛЬЗУЙ МЕТАФОРЫ: 'cinematic lighting', 'surreal digital art', 'neon bokeh', 'atmospheric night city'.

        !!! ВАЖНО: ОФОРМЛЕНИЕ МНЕНИЯ ЭКСПЕРТА !!!
        В самом конце текста (в поле content) добавь блок "Мнение эксперта", оформив его СТРОГО в этом HTML:
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border-left: 4px solid #8b5cf6; padding: 25px; margin: 40px 0; border-radius: 12px; box-shadow: 0 0 20px rgba(139, 92, 246, 0.15); color: #e2e8f0; font-family: sans-serif;">
          <h4 style="margin-top: 0; color: #a78bfa; text-transform: uppercase; letter-spacing: 1px; font-size: 14px; margin-bottom: 12px; display: flex; align-items: center;">
            <span style="margin-right: 8px;">⚡</span> Мнение эксперта
          </h4>
          <p style="font-style: italic; line-height: 1.6; margin-bottom: 0; color: #cbd5e1;">
            [Твой краткий, дерзкий и экспертный вывод по теме "{target_topic}"]
          </p>
        </div>

        Верни ответ СТРОГО в формате JSON:
        {{
          "title": "{target_topic}",
          "excerpt": "Мета-описание (150-160 символов) для поисковиков.",
          "content": "HTML-текст статьи (включая подзаголовки, списки и блок эксперта в конце)",
          "photo_keywords": "3-5 атмосферных английских слов"
        }}
        """

        # --- 2. ГЕНЕРАЦИЯ И ПАРСИНГ ---
        raw_res = await mm.generate(prompt)
        match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            raise Exception("Ошибка формата JSON")

        # --- 3. РАБОТА С ИЗОБРАЖЕНИЕМ (PEXELS) ---
        PEXELS_KEY = "rzdmYACqPHYAjdHRDipCFPM40aUMJOPP5Lo8mKvX1VUQCRvdQUC38yYn"
        raw_keywords = data.get('photo_keywords', 'abstract future').lower()
        forbidden = ['computer', 'laptop', 'monitor', 'pc', 'office', 'screen', 'keyboard', 'typing']
        
        clean_ai_list = [w for w in raw_keywords.replace(",", " ").split() if w not in forbidden]
        art_styles = ["cinematic photography", "surreal digital art", "bokeh city lights", "atmospheric lighting", "abstract pattern"]
        
        query = f"{' '.join(clean_ai_list[:2])} {random.choice(art_styles)}".strip()
        img_url = "https://images.unsplash.com/photo-1614741118887-7a4ee193a5fa?q=80&w=1200"

        try:
            px_url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=15&orientation=landscape"
            px_res = requests.get(px_url, headers={"Authorization": PEXELS_KEY}, timeout=10)
            if px_res.status_code == 200:
                photos = px_res.json().get('photos', [])
                if photos:
                    img_url = random.choice(photos)['src']['large']
        except Exception as e:
            print(f"🚨 Ошибка Pexels: {e}")

        # --- 4. СОХРАНЕНИЕ В SUPABASE (ИСПРАВЛЕННЫЙ SLUG + ПРОВЕРКА ТЕКСТА) ---
        final_title = data.get("title", target_topic)
        
        # Интегрируем твой транслит прямо сюда
        def internal_slugify(text):
            chars = {
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
                'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
                'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
                'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
            }
            text = text.lower().strip()
            # Сначала транслит букв
            result = "".join(chars.get(c, c) for c in text)
            # Потом замена всего лишнего на дефисы
            result = re.sub(r'[^a-z0-9]+', '-', result)
            return result.strip('-')

        slug_name = internal_slugify(final_title)

        # Если вдруг слаг пустой — страховка
        if not slug_name:
            slug_name = f"post-{random.randint(1000, 9999)}"

        # --- ЗАЩИТА ОТ ПУСТОГО КОНТЕНТА ---
        # Проверяем разные ключи, которые может выдать ИИ
        final_content = data.get('content') or data.get('text') or data.get('article')
        
        # Если в JSON пусто, берем сырой ответ raw_res (fallback)
        if not final_content:
            print("⚠️ Контент в JSON не найден, использую сырой текст")
            final_content = raw_res if 'raw_res' in locals() else "Текст не был сгенерирован"

        # Если excerpt пустой, создаем его из начала контента
        final_excerpt = data.get('excerpt', '')
        if not final_excerpt and final_content:
             # Убираем теги для анонса (если функция clean_html доступна)
             final_excerpt = final_content[:160].replace('<p>', '').replace('</p>', '') + "..."

        # Вставляем данные
        res = supabase.table("posts").insert({
            "title": final_title,
            "slug": slug_name,
            "image_url": img_url,
            "excerpt": final_excerpt,
            "content": final_content  # Теперь здесь точно не будет пусто
        }).execute()

        print(f"🚀 Статья опубликована: {final_title} | SLUG: {slug_name}")

        return {
            "status": "success", 
            "title": final_title, 
            "slug": slug_name,
            "image": img_url,
            "content_status": "filled" if final_content else "empty"
        }

    except Exception as e:
        print(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/posts")
async def get_posts(page: int = 1, limit: int = 6):
    try:
        # Считаем диапазон для Supabase
        start = (page - 1) * limit
        end = start + limit - 1

        # Запрос: берем данные + общее количество (count)
        # Сортируем: самые свежие (desc=True) сверху
        res = supabase.table("posts") \
            .select("*", count="exact") \
            .order("created_at", desc=True) \
            .range(start, end) \
            .execute()

        total_count = res.count or 0
        total_pages = (total_count + limit - 1) // limit

        return {
            "posts": res.data,
            "total_pages": total_pages,
            "current_page": page,
            "total_posts": total_count
        }
    except Exception as e:
        return {"error": str(e)}

# --- ОСТАЛЬНЫЕ РОУТЫ (БЕЗ ИЗМЕНЕНИЙ) ---

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
        
        # Автоматическое определение типа голоса по префиксу
        is_premium = any(p in r.voice for p in ["af_", "am_", "ru_v10_"])

        if is_premium:
            # Запрос к улучшенному движку
            resp = requests.post(HF_KOKORO_URL, json={"text": r.text, "voice": r.voice}, timeout=60)
            if resp.status_code == 200:
                with open(path, "wb") as f: f.write(resp.content)
            else:
                return JSONResponse(status_code=500, content={"detail": "Ошибка движка озвучки"})
        else:
            # Обычный движок
            rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
            await edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%")).save(path)
            
        return {"audio_url": f"/wait-download?file={fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": "Техническая ошибка"})
        
@app.on_event("startup")
async def startup_event():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)')
    conn.commit(); conn.close()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))































