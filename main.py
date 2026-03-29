import os
import uuid
import asyncio
import sqlite3
import json
import edge_tts
import google.generativeai as genai
import markdown
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
import re

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
# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_KEY")

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- ИНИЦИАЛИЗАЦИЯ GEMINI 3.1 FLASH LITE ---
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
            return resp.text if resp else "Ошибка: ИИ не вернул ответ"
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BLOG_FOLDER = os.path.join(BASE_DIR, "blog")
os.makedirs(BLOG_FOLDER, exist_ok=True)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)

# --- ДАННЫЕ БЛОГА ---
BLOG_POSTS = [
    {
        "id": 1001, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue",
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства...</p>"
    },
    {
        "id": 1002, "title": "Секреты идеального подкаста", "slug": "sekrety-sozdaniya-podkasta-ii", 
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", 
        "excerpt": "Автоматизация монтажа с помощью ИИ.", "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple",
        "content": "<p>Создание подкаста всегда было трудоемким процессом...</p>"
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

class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str; key: Optional[str] = None
class KeyCheck(BaseModel): key: str
class AdminGenRequest(BaseModel): 
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

# --- МАРШРУТЫ САЙТА (ИСПРАВЛЕНЫ) ---

def get_posts_from_folder():
    posts = []
    if not os.path.exists(BLOG_FOLDER):
        return posts
    
    # Читаем все .html файлы
    files = [f for f in os.listdir(BLOG_FOLDER) if f.endswith('.html')]
    
    for filename in files:
        try:
            with open(os.path.join(BLOG_FOLDER, filename), 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) >= 3:
                    title = lines[0].strip()
                    image_url = lines[1].strip()
                    content = "".join(lines[2:])
                    # Делаем короткое превью для главной
                    excerpt = content[:200].replace('<h2>', '').replace('<p>', '')[:150] + "..."
                    
                    posts.append({
                        "title": title,
                        "image": image_url,
                        "content": content,
                        "excerpt": excerpt,
                        "slug": filename # передаем имя файла целиком
                    })
        except Exception as e:
            print(f"Ошибка чтения файла {filename}: {e}")
            
    # Сортируем: новые файлы (по дате создания) будут первыми
    posts.sort(key=lambda x: os.path.getmtime(os.path.join(BLOG_FOLDER, x['slug'])), reverse=True)
    return posts

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    all_posts = get_posts_from_folder()
    # Передаем список постов в шаблон index.html
    return templates.TemplateResponse(request=request, name="index.html", context={"posts": all_posts[:15]})

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request):
    all_posts = get_posts_from_folder()
    return templates.TemplateResponse(request=request, name="blog_index.html", context={"posts": all_posts, "is_single": False})



@app.get("/blog/{slug}", response_class=HTMLResponse)
async def read_post(request: Request, slug: str):
    # 1. Формируем путь к файлу
    filename = slug if slug.endswith('.html') else f"{slug}.html"
    file_path = os.path.join(BLOG_FOLDER, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Статья не найдена")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if len(lines) < 2:
            raise HTTPException(status_code=500, detail="Файл поврежден")

        # 2. Чистим данные
        title = lines[0].strip()
        
        # Проверяем вторую строку на наличие ссылки
        potential_img = lines[1].strip()
        if potential_img.startswith("http"):
            image_url = potential_img
            content_raw = "".join(lines[2:])
        else:
            # Если ссылки нет, генерируем её по названию (Способ 1)
            img_id = abs(hash(filename)) % 1000
            image_url = f"https://loremflickr.com/800/600/ai,tech?lock={img_id}"
            content_raw = "".join(lines[1:])

        # 3. ПРЕВРАЩАЕМ МАРКДАУН В HTML
        # Это уберет видимые ## и сделает текст чистым
        formatted_html = markdown.markdown(content_raw)

        post = {
            "title": title,
            "image": image_url,
            "content": formatted_html
        }

        return templates.TemplateResponse(
            "blog_index.html", 
            {"request": request, "posts": [post], "is_single": True}
        )
    except Exception as e:
        print(f"Ошибка: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обработки статьи")

@app.get("/voices", response_class=HTMLResponse)
async def voices_page(request: Request):
    return templates.TemplateResponse(request=request, name="voices.html")

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

# --- API ---

@app.post("/api/admin/generate-post")
async def api_admin_gen(req: AdminGenRequest):
    try:
        # 1. Проверяем/создаем папку блога прямо перед записью
        if not os.path.exists(BLOG_FOLDER):
            os.makedirs(BLOG_FOLDER, exist_ok=True)

        # 2. Промпт с требованием чистого JSON
        prompt = f"""
        Напиши профессиональную SEO-статью на тему: {req.message}.
        Верни ответ СТРОГО в формате JSON:
        {{
          "title": "Заголовок статьи",
          "excerpt": "Краткий анонс",
          "content": "Текст с тегами <h2> и <p>",
          "photo_keyword": "english_keyword"
        }}
        """
        
        raw_res = await mm.generate(prompt)
        
        # 3. Улучшенная очистка JSON от мусора ИИ
        clean_json = raw_res.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
        data = json.loads(clean_json)
        
        # 4. Формируем имя файла через транслит
        title_rus = data.get('title', 'bez-nazvaniya')
        slug_name = slugify(title_rus)
        
        # Если вдруг заголовок пустой или slugify не сработал
        if not slug_name:
            slug_name = f"article-{uuid.uuid4().hex[:6]}"
            
        filename = f"{slug_name}.html"
        file_path = os.path.join(BLOG_FOLDER, filename)

        # 5. Фиксируем картинку
        img_id = abs(hash(filename)) % 1000
        keyword = data.get('photo_keyword', 'technology').lower()
        img_url = f"https://loremflickr.com/800/600/{keyword}?lock={img_id}"

        # 6. Запись в файл (Заголовок | Картинка | Контент)
        # Используем разделитель ||| для надежного чтения в будущем
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"{data['title']}\n")
            f.write(f"{img_url}\n")
            f.write(f"{data['content']}")
            
        print(f"Статья успешно создана: {filename}") # Увидите в логах Render
        return {"status": "success", "slug": filename}

    except json.JSONDecodeError:
        return JSONResponse(status_code=500, content={"status": "error", "message": "ИИ вернул некорректный формат данных. Попробуйте еще раз."})
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {str(e)}") # Важно для логов!
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Ошибка сервера: {str(e)}"})

@app.post("/api/verify-key")
async def verify_key(data: KeyCheck):
    is_valid = data.key.upper() in [k.upper() for k in PREMIUM_KEYS]
    return {"success": is_valid}

@app.get("/wait-download", response_class=HTMLResponse)
async def wait_page(request: Request, file: str, key: str = None):
    return templates.TemplateResponse(
        request=request, 
        name="wait_page.html", 
        context={"file": file}
    )

@app.get("/download")
async def download_file(file: str):
    path = os.path.join(AUDIO_DIR, file)
    if os.path.exists(path):
        return FileResponse(path=path, filename="speechclone.mp3")
    return HTMLResponse("Файл не найден.", status_code=404)

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
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))































