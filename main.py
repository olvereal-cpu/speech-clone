import os
import re
import uuid
import asyncio
import ssl
import sqlite3
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
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

# --- БАЗА ДАННЫХ (SQLite) ---
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

# --- НАСТРОЙКА GEMINI AI (С ЗАЩИТОЙ) ---
GOOGLE_API_KEY = os.getenv("GEMINI_KEY")
model_ai = None

if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model_ai = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=(
                "Ты — Спич-Бро, официальный ИИ-помощник сайта SpeechClone.online. "
                "Помогай с озвучкой текста, пиши коротко и с эмодзи. "
                "Ударения: ставь '+' перед гласной. Скачивание: ожидание 30 сек."
            )
        )
    except Exception as e:
        print(f"Ошибка инициализации Gemini: {e}")

# --- ФИКС SSL ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# --- ИНИЦИАЛИЗАЦИЯ FastAPI ---
app = FastAPI(redirect_slashes=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем папки при старте
for path in ["static", "static/audio", "static/images/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

class ChatRequest(BaseModel):
    message: str

# --- ЛОГИКА ГЕНЕРАЦИИ ---
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

# --- ТЕЛЕГРАМ БОТ (AIOGRAM 3.x) ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_data = {}

async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    user_name = message.from_user.first_name or "друг"
    await message.answer(f"👋 Привет, {user_name}! Пришли текст для озвучки.\n💡 Используй **+** для ударения.")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    count = len(get_all_users())
    await message.answer(f"📊 Всего пользователей в базе: {count}")

@dp.message(Command("db"))
async def cmd_db(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if os.path.exists(DB_PATH):
        await message.answer_document(types.FSInputFile(DB_PATH), caption="📦 Бэкап базы данных пользователей.")
    else:
        await message.answer("❌ Файл базы данных не найден.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID: return
    if not command.args:
        return await message.answer("❌ Введи текст: `/broadcast Привет всем`")
    
    users = get_all_users()
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, command.args)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    if message.text.startswith("/"): return
    
    if uid != ADMIN_ID and not await check_sub(uid):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="💎 Подписаться на Speech Clone", url=CHANNEL_URL))
        text_sub = (
            "⚠️ **Доступ ограничен**\n\n"
            "Наш проект **полностью бесплатный**! 🎁\n\n"
            "Единственное условие — подписка на канал. Это помогает нам работать.\n\n"
            "Подпишись, и голоса станут доступны!"
        )
        return await message.answer(text_sub, reply_markup=kb.as_markup(), parse_mode="Markdown")

    add_user(uid)
    user_data[uid] = {"text": message.text}
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Екатерина", callback_data="v_ru-RU-EkaterinaNeural"),
                types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Ava", callback_data="v_en-US-AvaNeural"),
                types.InlineKeyboardButton(text="🇺🇸 Andrew", callback_data="v_en-US-AndrewNeural"))
    builder.row(types.InlineKeyboardButton(text="Поддержать проект ⭐️", callback_data="donate_menu"))
    await message.answer("Выберите голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_data: 
        user_data[user_id] = {"text": "Тестовый текст"}
    user_data[user_id]["voice"] = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Обычный", callback_data="m_natural"),
                types.InlineKeyboardButton(text="Медленно", callback_data="m_slow"),
                types.InlineKeyboardButton(text="Быстро", callback_data="m_fast"))
    await callback.message.edit_text("Выберите режим скорости:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    uid = callback.from_user.id
    if uid not in user_data: return
    
    data = user_data[uid]
    status_msg = await callback.message.edit_text("⌛ Нейросеть генерирует аудио...")
    try:
        file_id = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        await callback.message.answer_audio(
            types.FSInputFile(file_path), 
            caption="✅ Готово! Озвучено в @SpeechCloneBot"
        )
        await status_msg.delete()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

# --- САЙТ И API ---
@app.post("/api/chat")
async def chat_ai(request: ChatRequest):
    if not model_ai:
        return {"reply": "Бро, мой ИИ-мозг сейчас спит (проблема с ключом), но озвучка работает! 🎤"}
    try:
        response = await asyncio.to_thread(model_ai.generate_content, request.message)
        return {"reply": response.text}
    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "Ошибка связи с ИИ. Попробуй позже."}

@app.post("/api/generate")
async def generate(request: TTSRequest):
    try:
        fid = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request): 
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-audio/{f}")
async def get_audio(f: str): 
    return FileResponse(os.path.join(BASE_DIR, "static/audio", f))

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {"request": request, "file_name": file})

@app.get("/blog")
async def blog_index(request: Request): 
    return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{p}")
async def blog_post(request: Request, p: str): 
    try:
        return templates.TemplateResponse(f"blog/{p}.html", {"request": request})
    except:
        return templates.TemplateResponse("index.html", {"request": request})

@app.get("/{p}")
async def other_pages(request: Request, p: str):
    try: 
        return templates.TemplateResponse(f"{p}.html", {"request": request})
    except: 
        return templates.TemplateResponse("index.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    # Запускаем бота один раз
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)





