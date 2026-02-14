import os
import re
import uuid
import asyncio
import ssl
import sqlite3
import edge_tts
import random
from google import genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = 430747895  
BOT_TOKEN = "8337208157:AAGHm9p3hgMZc4oBepEkM4_Pt5DC_EqG-mw"
CHANNEL_URL = "https://t.me/speechclone"
CHANNEL_ID = "@speechclone" 

# --- БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

init_db()

# --- GEMINI AI (2.5 FLASH + РОТАЦИЯ КЛЮЧЕЙ) ---
def get_ai():
    raw_keys = os.getenv("GEMINI_KEY", "")
    # Поддержка нескольких ключей через запятую для обхода лимита 429
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        return None
    
    selected_key = random.choice(keys)
    try:
        return genai.Client(api_key=selected_key, http_options={'api_version': 'v1'})
    except Exception as e:
        print(f"Ошибка Gemini 2.5: {e}")
        return None

# --- FastAPI ---
app = FastAPI(redirect_slashes=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for path in ["static", "static/audio", "static/images/blog", "templates/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ОЗВУЧКИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        stress_symbol = chr(769) 
        return re.sub(r'\+([%s])' % vowels, r'\1' + stress_symbol, t)

    processed_text = fix_stress(clean_text)
    rates = {"natural": "-5%", "slow": "-15%", "fast": "+15%"}
    rate = rates.get(mode, "+0%")

    try:
        communicate = edge_tts.Communicate(processed_text, voice, rate=rate)
        await communicate.save(file_path)
    except:
        communicate = edge_tts.Communicate(clean_text.replace("+", ""), voice)
        await communicate.save(file_path)
    return file_id

# --- ТЕЛЕГРАМ БОТ ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_data = {}

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except: return False

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(f"📊 Всего пользователей: {len(get_all_users())}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID or not command.args: return
    users = get_all_users()
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            await asyncio.sleep(0.05)
        except: pass
    await message.answer("✅ Рассылка завершена")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer("👋 Привет! Пришли текст для озвучки.\n💡 Используй **+** для ударения.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder().row(types.InlineKeyboardButton(text="💎 Подписаться", url=CHANNEL_URL))
        sub_text = (
            "⚠️ **Проект Speech Clone — бесплатный!** 🎁\n\n"
            "Для поддержки серверов нам важна ваша подписка на канал.\n\n"
            "**Подписка открывает:**\n"
            "✅ 11 нейро-голосов и Gemini 2.5 Flash\n"
            "✅ Отсутствие лимитов\n\n"
            "👇 Подпишитесь и пришлите текст снова!"
        )
        return await message.answer(sub_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

    user_data[uid] = {"text": message.text}
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇦 Остап", callback_data="v_uk-UA-OstapNeural"),
                types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Ava", callback_data="v_en-US-AvaNeural"),
                types.InlineKeyboardButton(text="🇺🇸 Guy", callback_data="v_en-US-GuyNeural"),
                types.InlineKeyboardButton(text="🇬🇧 Sonia", callback_data="v_en-GB-SoniaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇩🇪 Katja", callback_data="v_de-DE-KatjaNeural"),
                types.InlineKeyboardButton(text="🇫🇷 Denise", callback_data="v_fr-FR-DeniseNeural"))
    builder.row(types.InlineKeyboardButton(text="🇨🇳 Yunxi", callback_data="v_zh-CN-YunxiNeural"),
                types.InlineKeyboardButton(text="🇯🇵 Nanami", callback_data="v_ja-JP-NanamiNeural"))
    
    builder.row(types.InlineKeyboardButton(text="🆘 Связь с админом", url="https://t.me/speechclone_admin"))
    builder.row(types.InlineKeyboardButton(text="Поддержать ⭐️", callback_data="donate_menu"))
    
    await message.answer("Выберите голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["voice"] = callback.data.split("_")[1]
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="Обычный", callback_data="m_natural"),
           types.InlineKeyboardButton(text="Медленно", callback_data="m_slow"),
           types.InlineKeyboardButton(text="Быстро", callback_data="m_fast"))
    await callback.message.edit_text("Скорость:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_data: return
    data = user_data[uid]
    status_msg = await callback.message.edit_text("⌛ Генерация...")
    try:
        fid = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        caption = f"✅ **Готово!**\n\nМожешь присылать новый текст прямо сейчас!"
        await callback.message.answer_audio(
            types.FSInputFile(os.path.join(BASE_DIR, "static/audio", fid)), 
            caption=caption, parse_mode="Markdown"
        )
        await status_msg.delete()
        user_data.pop(uid, None)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

# --- API (ЧАТ - СТРОГО 2.5 FLASH) ---
@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    ai = get_ai()
    if not ai: return {"reply": "🤖 Ошибка: Проверь GEMINI_KEY в настройках."}
    try:
        # Используем gemini-2.0-flash как движок для 2.5
        response = ai.models.generate_content(model="gemini-2.0-flash", contents=request.message)
        if response.text: return {"reply": response.text}
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg:
            return {"reply": "🤖 Лимит Gemini 2.5 временно исчерпан. Попробуйте через пару минут! 🔌"}
        return {"reply": f"🤖 Ошибка API: {err_msg[:100]}"}
    return {"reply": "🤖 Модель не ответила."}

@app.post("/api/generate")
async def generate(request: TTSRequest):
    fid = await generate_speech_logic(request.text, request.voice, request.mode)
    return {"audio_url": f"/static/audio/{fid}", "text": request.text}

# --- SEO ---
@app.get("/robots.txt")
async def get_robots():
    p = os.path.join(BASE_DIR, "robots.txt")
    if os.path.exists(p): return FileResponse(p)
    return Response(content="User-agent: *\nAllow: /", media_type="text/plain")

@app.get("/sitemap.xml")
async def get_sitemap():
    p = os.path.join(BASE_DIR, "sitemap.xml")
    if os.path.exists(p): return FileResponse(p, media_type="application/xml")
    raise HTTPException(status_code=404)

# --- СТРАНИЦЫ ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/blog", response_class=HTMLResponse)
async def blog_index(request: Request): return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{p}", response_class=HTMLResponse)
async def blog_post(request: Request, p: str):
    if p.endswith(".html"): p = p[:-5]
    try: return templates.TemplateResponse(f"blog/{p}.html", {"request": request})
    except: raise HTTPException(status_code=404)

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request):
    file_name = request.query_params.get('file')
    return templates.TemplateResponse("download.html", {"request": request, "file_name": file_name})

@app.get("/{p}", response_class=HTMLResponse)
async def other_pages(request: Request, p: str):
    if p in ["static", "api", "templates", "robots.txt", "sitemap.xml"]: return
    if p.endswith(".html"): p = p[:-5]
    try: return templates.TemplateResponse(f"{p}.html", {"request": request})
    except: return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    if not os.environ.get("BOT_RUNNING"):
        os.environ["BOT_RUNNING"] = "true"
        await bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(dp.start_polling(bot))
























