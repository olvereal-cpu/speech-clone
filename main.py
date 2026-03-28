import os
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
GEMINI_API_KEY = "AIzaSyBUfpWakwPK3ECR83Ou8L81C0yKa_gnIOE"
CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"

# --- ДАННЫЕ БЛОГА (Для вывода на главную) ---
# Добавь сюда свои реальные статьи. Шаблон index.html должен уметь их отображать.
BLOG_POSTS = [
    {
        "id": 1,
        "title": "Как нейросети меняют озвучку",
        "slug": "kak-neyroseti-menyayut-ozvuchku",
        "image": "/static/img/blog1.jpg", # Путь к картинке (создай папку static/img)
        "excerpt": "Разбираемся, как технологии AI делают синтез речи неотличимым от человеческого голоса...",
        "date": "15.10.2023"
    },
    {
        "id": 2,
        "title": "5 лучших голосов Speech Clone",
        "slug": "5-luchshih-golosov-speech-clone",
        "image": "/static/img/blog2.jpg",
        "excerpt": "Обзор самых популярных и реалистичных голосов на нашем сервисе для разных задач...",
        "date": "10.10.2023"
    },
    {
        "id": 3,
        "title": "Озвучка книг с помощью ИИ",
        "slug": "ozvuchka-knig-s-pomoshchyu-ii",
        "image": "/static/img/blog3.jpg",
        "excerpt": "Пошаговое руководство, как быстро и качественно озвучить целую книгу, используя Speech Clone...",
        "date": "05.10.2023"
    }
]

# Все доступные голоса
VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural",
    "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural",
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

# --- ИНИЦИАЛИЗАЦИЯ ИИ (Gemini) ---
google.generativeai.configure(api_key=GEMINI_API_KEY)
# Используем flash модель для скорости
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
    await message.answer("👋 Привет! Выбери язык озвучки кнопку ниже и пришли текст. Не забудь подписаться на канал!", reply_markup=kb.as_markup())

# --- АДМИН-ПАНЕЛЬ ---
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
    
    # Обязательная подписка
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

# --- FASTAPI (САЙТ И API) ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Модели запросов
class ChatRequest(BaseModel):
    message: str

class TTSRequest(BaseModel):
    text: str; voice: str; mode: str

# 1. ГЛАВНАЯ СТРАНИЦА: Теперь с передачей статей блога
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Передаем список статей BLOG_POSTS в шаблон
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"posts": BLOG_POSTS} # <--- СЮДА ПЕРЕДАЕМ СТАТЬИ
    )

# 2. ПОЧИНЕННЫЙ РОУТ ЧАТА: Больше не будет undefined
@app.post("/api/chat")
async def chat(r: ChatRequest):
    try:
        # Генерация ответа через Gemini в отдельном потоке (чтобы не вешать сервер)
        response = await asyncio.to_thread(model_ai.generate_content, r.message)
        
        # ВАЖНО: возвращаем {"reply": ...}, JS на сайте ищет это поле
        if response and response.text:
            return {"reply": response.text}
        else:
            return {"reply": "ИИ не смог сгенерировать ответ. Попробуйте другой запрос."}
            
    except Exception as e:
        print(f"Chat Error: {e}")
        # Если ИИ упал, возвращаем понятную ошибку в том же формате
        return JSONResponse(status_code=500, content={"reply": "Ошибка соединения с ИИ. Попробуйте позже."})

# API для генерации аудио на сайте (Speech Clone)
@app.post("/api/generate")
async def generate(r: TTSRequest):
    try:
        fid = f"{uuid.uuid4()}.mp3"
        path = os.path.join(AUDIO_DIR, fid)
        # Настройка скорости
        rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
        comm = edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%"))
        await comm.save(path)
        # Возвращаем URL файла
        return {"audio_url": f"/static/audio/{fid}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": f"Ошибка генерации: {e}"})

# Перехват всех остальных страниц (если есть)
@app.get("/{page}", response_class=HTMLResponse)
async def catch_all(request: Request, page: str):
    try:
        return templates.TemplateResponse(request=request, name=f"{page}.html")
    except:
        return templates.TemplateResponse(request=request, name="index.html")

# --- ЗАПУСК БОТА В ФОНЕ ---
@app.on_event("startup")
async def startup_event():
    # Запускаем поллинг бота в фоне при старте FastAPI
    asyncio.create_task(dp.start_polling(bot))
