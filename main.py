import os
import uuid
import asyncio
import sqlite3
import secrets
import json
import edge_tts
import google.generativeai as genai
import re
import httpx
import markdown
import random
import requests
import urllib.parse
import urllib.request
import logging
import math
import io
import aiohttp
import socket
import shutil
import soundfile as sf
from fastapi.responses import StreamingResponse, Response
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, UploadFile, File, Form
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from supabase import create_client, Client
from slugify import slugify
from starlette.exceptions import HTTPException as StarletteHTTPException
from gradio_client import Client, handle_file
VOICE_PRESETS = {
    "classic": "Damien Montez",
    "whisper": "Whisper",
    "news": "News",
    "grumpy": "Grumpy",
    "echo": "Echo",
    "custom": "Damien Montez"
}
SUPABASE_URL = "https://zbcpntzpnkhpzlwextbn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpiY3BudHpwbmtocHpsd2V4dGJuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4MjM2NjIsImV4cCI6MjA5MDM5OTY2Mn0.MP7pnt_pTx0Am1Str1yTwR4UYagjyQM5Bk3jC8javdM"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
HF_KOKORO_URL = "https://sercos-my-tts-api.hf.space/generate"
# ТВОЯ НОВАЯ СТУДИЯ (PIPER)
HF_PIPER_URL = "https://sercos-oleg-studio-v2.hf.space/tts"
raw_token = os.getenv("HF_TOKEN1")
if raw_token:
    HF_TOKEN1 = raw_token.strip()
else:
    HF_TOKEN1 = ""
HF_URL = "https://sercos-oleg-xtts-kz-hf-space.hf.space/generate"

# Отладка в консоль Render (увидишь при запуске)
print(f"DEBUG: Token status: {'LOADED' if HF_TOKEN1 else 'EMPTY'}")
HF_TOKEN1 = os.getenv("HF_TOKEN1") 
HF_URL = "https://sercos-oleg-xtts-kz-hf-space.hf.space/generate"
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
        self.target_model = 'gemini-3.1-flash-lite-preview'
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
RESULT_DIR = os.path.join("static", "results")
if not os.path.exists(RESULT_DIR):
    os.makedirs(RESULT_DIR, exist_ok=True)
    print(f"✅ Папка {RESULT_DIR} создана!")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
BLOG_FOLDER = os.path.join(BASE_DIR, "blog")
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(BLOG_FOLDER, exist_ok=True)


# --- ЕДИНЫЙ КОНФИГ ГОЛОСОВ (ИНВЕРТИРОВАННЫЙ ПОД ТВОЮ ЛОГИКУ) ---
VOICES = {
    # --- СТУДИЙНЫЕ (PIPER) ---
    "🎙 🇰🇿 | ISSAI (HQ)": "kk_KZ-issai-high.onnx",
    "🎙 🇰🇿 | РАЯ (Fast)": "kk_KZ-raya-x_low.onnx",
    "🎙 🇰🇿 | ИСЕКЕ (Fast)": "kk_KZ-iseke-x_low.onnx",
    "🎙 🇷🇺 | ДЕНИС": "ru_RU-denis-medium.onnx",
    "🎙 🇷🇺 | ДМИТРИЙ": "ru_RU-dmitri-medium.onnx",
    "🎙 🇷🇺 | ИРИНА": "ru_RU-irina-medium.onnx",
    "🎙 🇷🇺 | РУСЛАН": "ru_RU-ruslan-medium.onnx",
    "🎙 🇷🇺 | ТАТЬЯНА": "ru_RU-tatyana-medium.onnx",
    "🎙 🇷🇺 | ВИКТОРИЯ": "ru_RU-victoria-medium.onnx",
    
    # --- PREMIUM (KOKORO) ---
    "🌟 SKY (PREM)": "af_sky",
    "🌟 BELLA (PREM)": "af_bella",
    "🌟 NICOLE (PREM)": "af_nicole",
    "🌟 ADAM (PREM)": "am_adam",
    "🌟 MICHAEL (PREM)": "am_michael",
    "🌟 EMMA (UK)": "bf_emma",
    "🌟 GEORGE (UK)": "bm_george",

    # --- СТАНДАРТ (EDGE) ---
    "🇷🇺 СВЕТЛАНА": "ru-RU-SvetlanaNeural",
    "🇷🇺 ДМИТРИЙ": "ru-RU-DmitryNeural",
    "🇰🇿 АЙГУЛЬ": "kk-KZ-AigulNeural",
    "🇰🇿 ДӘУЛЕТ": "kk-KZ-DauletNeural",
    "🇺🇦 ПОЛІНА": "uk-UA-PolinaNeural",
    "🇺🇦 ОСТАП": "uk-UA-OstapNeural",
    "🇺🇸 JENNY": "en-US-JennyNeural",
    "🇹🇷 EMEL": "tr-TR-EmelNeural",
    "🇩🇪 KATJA": "de-DE-KatjaNeural",
    "🇫🇷 DENISE": "fr-FR-DeniseNeural",
    "🇪🇸 ELVIRA": "es-ES-ElviraNeural",
    "🇵🇱 ZOFIA": "pl-PL-ZofiaNeural"
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
    # 1. Работа с БД (внутри функции)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,))
    conn.commit()
    conn.close()

    # 2. Проверка подписки
    if message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id):
        kb_sub = InlineKeyboardBuilder()
        kb_sub.button(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")
        kb_sub.button(text="🔄 Проверить подписку", callback_data="sub_check_done")
        return await message.answer(
            "⚠️ Для использования бота необходимо подписаться на наш канал!", 
            reply_markup=kb_sub.adjust(1).as_markup()
        )

    # 3. Если проверка пройдена — создаем клавиатуру голосов
    kb = InlineKeyboardBuilder()

    # Добавляем кнопки голосов (ОТСТУП ВАЖЕН: всё должно быть внутри функции)
    for name in VOICES.keys():
        kb.button(text=name, callback_data=f"v_{name}")

    # Настраиваем сетку
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="🌟 На кофе", callback_data="buy_stars"))

    # Текст сообщения
    welcome_text = (
        "👋 Приветствуем в SpeechClone!\n"
        "Выберите подходящий голос для озвучки:\n"
        "• 🎙 Студия — студийное звучание\n"
        "• 🌟 Premium — максимально живое звучание.\n"
        "• 🇷🇺/🇰🇿 Стандарт — классические голоса.\n\n"
        "Просто отправьте текст после выбора голоса, и я его озвучу."
    )

    # 4. Отправляем ответ
    await message.answer(welcome_text, reply_markup=kb.as_markup())

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
            await asyncio.sleep(0.05)
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
    # 1. Фильтр команд и проверка подписки
    if message.text.startswith("/") or (message.from_user.id != ADMIN_ID and not await check_sub(message.from_user.id)): 
        return

    try:
        # 2. Получаем v_id из базы
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute('SELECT voice FROM users WHERE user_id = ?', (message.from_user.id,)).fetchone()
        v_id = res[0] if res else "ru-RU-DmitryNeural"
        conn.close()
        
        # 3. Настройки файла
        is_piper = v_id.endswith(".onnx")
        is_kokoro = v_id.startswith(("af_", "am_", "bf_", "bm_"))
        ext = ".wav" if (is_piper or is_kokoro) else ".mp3"
        fid = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(AUDIO_DIR, fid)

        # 4. ПОСЛЕДОВАТЕЛЬНАЯ ГЕНЕРАЦИЯ
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(family=socket.AF_INET)) as session:
            # --- KOKORO ---
            if is_kokoro:
                url = "https://sercos-my-tts-api.hf.space/generate"
                token = os.getenv('HF_TOKEN')
                params = {"text": message.text, "voice": v_id, "speed": 1.0}
                async with session.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=90) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                    else: return await message.answer(f"❌ Ошибка Kokoro: {resp.status}")

            # --- PIPER ---
            elif is_piper:
                url = "https://sercos-oleg-studio-v2.hf.space/tts"
                token = os.getenv('TOKEN_PIPER')
                params = {"text": message.text, "voice": v_id, "speed": 0.9}
                async with session.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=120) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f: f.write(await resp.read())
                    else: return await message.answer(f"❌ Ошибка Piper: {resp.status}")

            # --- EDGE ---
            else:
                import edge_tts
                await edge_tts.Communicate(message.text, v_id).save(path)

        # 5. ПРОВЕРКА И ОТПРАВКА
        if os.path.exists(path) and os.path.getsize(path) > 0:
            kb = InlineKeyboardBuilder().button(
                text="📥 СКАЧАТЬ (30 сек)", 
                url=f"{SITE_URL}/wait-download?file={fid}"
            )
            await message.answer("✅ Аудио готово!", reply_markup=kb.as_markup())
        else:
            await message.answer("❌ Ошибка: файл не был создан.")

    except Exception as e:
        print(f"LOG ERROR: {e}")
        await message.answer(f"❌ Системная ошибка: {str(e)}")
# --- НАСТРОЙКИ TTS ---


# --- FASTAPI ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# --- МОДЕЛИ ДАННЫХ ---
class ChatRequest(BaseModel): message: str
class TTSRequest(BaseModel): text: str; voice: str; mode: str; key: Optional[str] = None
class KeyCheck(BaseModel): key: str
class AdminGenRequest(BaseModel): 
    message: str
    category: Optional[str] = "Технологии"
    color: Optional[str] = "blue"

# --- МАРШРУТЫ САЙТА ---
@app.exception_handler(404)
async def custom_http_exception_handler(request: Request, exc: Exception):
    # ПЕРВЫМ аргументом должен идти request БЕЗ имени 'name='
    return templates.TemplateResponse(
        "404.html", 
        {"request": request}, 
        status_code=404
    )
@app.post("/api/generate")
async def generate_audio_universal(request: Request):
    try:
        data = await request.json()
        text = data.get("text")
        voice = data.get("voice", "ru-RU-DmitryNeural")
        mode = data.get("mode", "natural") # Добавили mode для Edge
        
        if not text: 
            return {"success": False, "error": "Нет текста"}

        # Определяем расширение и путь
        is_p = voice.endswith(".onnx")
        is_k = voice.startswith(("af_", "am_", "bf_", "bm_"))
        ext = "wav" if (is_p or is_k) else "mp3"
        fid = f"{uuid.uuid4().hex}.{ext}"
        file_path = os.path.join(AUDIO_DIR, fid)

        async with aiohttp.ClientSession() as session:
            if is_p or is_k:
                # Выбираем URL и Токен
                url = "https://sercos-oleg-studio-v2.hf.space/tts" if is_p else "https://sercos-my-tts-api.hf.space/generate"
                token = os.getenv('TOKEN_PIPER' if is_p else 'HF_TOKEN')
                
                async with session.get(url, params={"text": text, "voice": voice}, headers={"Authorization": f"Bearer {token}"}, timeout=120) as resp:
                    if resp.status == 200:
                        with open(file_path, "wb") as f: 
                            f.write(await resp.read())
                    else: 
                        return {"success": False, "error": f"HF Error: {resp.status}"}
            else:
                import edge_tts
                # Добавили скорость (mode), раз она есть в JS
                rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
                await edge_tts.Communicate(text, voice, rate=rates.get(mode, "+0%")).save(file_path)

        # ПРОВЕРКА И ОТВЕТ (Теперь со всеми полями для JS)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return {
                "success": True, 
                "audio_url": f"/static/audio/{fid}",   # Для плеера
                "fid": fid                             # Для кнопки скачивания
            }
        else:
            return {"success": False, "error": "Файл не создан"}

    except Exception as e:
        print(f"SITE ERROR: {e}")
        return {"success": False, "error": str(e)}

app.mount("/static", StaticFiles(directory="static"), name="static")
os.makedirs("static/results", exist_ok=True)
os.makedirs("static/ref", exist_ok=True)






# --- КОНФИГУРАЦИЯ ---
HF_URL = "https://sercos-oleg-xtts-kz-hf-space.hf.space/generate"
# Твой основной токен (добавляем .strip() на всякий случай)
HF_TOKEN = "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".strip()

# ПРОВЕРКА ТОКЕНА
try:
    # Здесь тоже добавляем .strip(), чтобы убрать лишние пробелы и переносы (\n)
    if 'HF_TOKEN1' in locals() and HF_TOKEN1:
        auth_token = HF_TOKEN1.strip()
    elif 'raw_token' in locals() and raw_token:
        auth_token = raw_token.strip()
    else:
        auth_token = HF_TOKEN
except NameError:
    auth_token = HF_TOKEN

print(f"DEBUG: Token loaded (length: {len(auth_token)})") # Проверка длины в логах

# --- 1. VOICE DESIGNER (Генерация по промпту) ---
@app.post("/api/prompt-voice")
async def api_prompt_voice(prompt_type: str = Form(...), text: str = Form(...)):
    headers = {"Authorization": f"Bearer {auth_token}"}
    data = {
        'gen_text': text, 
        'voice_type': prompt_type, 
        'remove_silence': 'true'
    }
    
    try:
        print(f"DEBUG Prompt: Отправка на {HF_URL} (Тип: {prompt_type})")
        res = requests.post(HF_URL, data=data, headers=headers, timeout=120)
        
        if res.status_code == 200:
            filename = f"voice_{uuid.uuid4().hex}.wav"
            path = os.path.join("static/results", filename)
            os.makedirs("static/results", exist_ok=True)
            with open(path, "wb") as out: 
                out.write(res.content)
            return {"status": "success", "audio_url": f"/static/results/{filename}"}
        
        print(f"DEBUG Error: Код {res.status_code}, Ответ: {res.text}")
        return {"status": "error", "message": f"HF Error: {res.status_code}"}
        
    except Exception as e: 
        print(f"DEBUG Exception: {str(e)}")
        return {"status": "error", "message": str(e)}

# --- 2. DUBBING & CLONING (Дубляж и Николай) ---
@app.post("/api/dub")
async def api_dubbing(
    file: UploadFile = File(...), 
    text: str = Form(""), 
    target_lang: str = Form("ru")
):
    temp_input = f"temp_{uuid.uuid4().hex}_{file.filename}"
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    try:
        # Читаем файл (Николай или видео)
        content = await file.read()
        with open(temp_input, "wb") as f: 
            f.write(content)

        with open(temp_input, "rb") as f:
            # Отправляем файл на Хуган для клонирования голоса
            files = {'ref_audio': (file.filename, f, file.content_type)}
            data = {
                'gen_text': text, 
                'target_lang': target_lang,
                'remove_silence': 'true'
            }
            print(f"DEBUG Dub: Отправка файла {file.filename} на {HF_URL}")
            res = requests.post(HF_URL, data=data, files=files, headers=headers, timeout=180)

        if res.status_code == 200:
            filename = f"output_{uuid.uuid4().hex}.wav"
            path = os.path.join("static/results", filename)
            os.makedirs("static/results", exist_ok=True)
            with open(path, "wb") as out: 
                out.write(res.content)
            return {"status": "success", "audio_url": f"/static/results/{filename}"}
            
        print(f"DEBUG Error Dub: Код {res.status_code}, Ответ: {res.text}")
        return {"status": "error", "message": f"HF Error: {res.status_code}"}
        
    except Exception as e: 
        print(f"DEBUG Exception in Dub: {str(e)}")
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_input): 
            os.remove(temp_input)
@app.get("/voices", response_class=HTMLResponse)
async def voices_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="voices.html",
        context={} # Добавляем пустой контекст для стабильности
    )

@app.get("/dubbing", response_class=HTMLResponse)
async def get_dubbing_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="dubbing.html", 
        context={}
    )

@app.get("/prompt-voice", response_class=HTMLResponse)
async def get_creation_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="prompt-voice.html", 
        context={}
    ) 
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        # Пробуем достать посты из базы
        res = supabase.table("posts").select("*").order("created_at", desc=True).limit(6).execute()
        all_posts = res.data if res and hasattr(res, 'data') and res.data else []
        
        return templates.TemplateResponse(
            request=request,  # Обязательно первым или именованным
            name="index.html", 
            context={"posts": all_posts}
        )
    except Exception as e:
        # Если база лежит или ошибка в коде - всё равно показываем сайт, но без постов
        print(f"Критическая ошибка на главной: {e}")
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
        
        return templates.TemplateResponse(
            request=request,
            name="blog_index.html", 
            context={
                "posts": [post],
                "is_single": True,
                "current_page": 1,
                "total_pages": 1
            }
        )
    except Exception as e:
        print(f"Ошибка чтения статьи {slug}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

@app.get("/sitemap.xml")
async def get_sitemap():
    try:
        response = supabase.table("posts").select("slug").execute()
        posts = response.data
        
        base_url = "https://speechclone.online" 

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            f'<url><loc>{base_url}/</loc><priority>1.0</priority></url>'
        ]

        for post in posts:
            slug = post.get('slug')
            if slug:
                xml_lines.append(f'<url><loc>{base_url}/blog/{slug}</loc><priority>0.8</priority></url>')

        xml_lines.append('</urlset>')
        
        return Response(content="".join(xml_lines), media_type="application/xml")

    except Exception as e:
        print(f"🚨 Ошибка: {e}")
        return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://speechclone.online/</loc></url></urlset>', media_type="application/xml")




@app.post("/api/admin/generate-post")
async def api_admin_gen(
    req: AdminGenRequest, 
    x_secret_key: str = Header(None)
):
    # Безопасное сравнение ключа
    MY_SECRET = "Barakuda"
    if not x_secret_key or not secrets.compare_digest(x_secret_key, MY_SECRET):
        print(f"🚫 Попытка несанкционированного доступа!")
        raise HTTPException(status_code=403, detail="Доступ запрещен")
        
    try:
        target_topic = req.message.strip()

        # --- 1. КОНСТРУКТОР ЖИВЫХ ТЕМ ---
        subjects = [
            "Цифровое бессмертие", "Психология алгоритмов", "Кибербезопасность семьи",
            "Воспитание в 2030 году", "Любовь в Tinder", "Биохакинг и чипы",
            "Экономика выживания", "Ментальный шум", "Рынок фриланса", "ИИ-одиночество"
        ]
        roles = [
            "независимый техно-блогер со скептичным взглядом", "дерзкий футуролог", 
            "уставший философ", "инсайдер из Кремниевой долины", "социолог-радикал"
        ]
        
        sel_role = random.choice(roles)
        
        if not target_topic or target_topic.lower() in ["авто", "auto", ".", "начни"]:
            topic_prompt = f"Ты — {sel_role}. Придумай провокационный заголовок для статьи из 3-6 слов. Тема про жизнь и общество. Без кавычек."
            generated_topic = await mm.generate(topic_prompt)
            target_topic = generated_topic.strip().replace('"', '').replace('.', '')

        print(f"📝 Тема: {target_topic} | Роль: {sel_role}")

        # --- 2. ГЕНЕРАЦИЯ «ЧЕЛОВЕЧЕСКОЙ» СТАТЬИ ---
        prompt = f"""
        Ты — {sel_role}. Напиши глубокую, ироничную и живую статью на тему: "{target_topic}".
        ОБЪЕМ: строго от 1200 до 1500 слов. Это КРИТИЧЕСКИ важно для SEO.

        СТИЛЬ (ДЛЯ ОБХОДА ДЕТЕКТОРОВ):
        - Пиши от первого лица ("Я", "мне кажется"). 
        - Используй живые метафоры, иронию, скепсис к корпорациям.
        - НИКАКОЙ ВОДЫ: забудь про "в современном мире", "важно отметить", "в заключение".
        - РИТМ: чередуй короткие хлесткие фразы с длинными размышлениями.
        
        СТРУКТУРА HTML:
        - Заголовки <h2> и <h3> должны быть дерзкими тезисами.
        - Обязательно добавь <table> (сравнение мифов и реальности).
        - Вместо блока FAQ сделай раздел <h2>"Что нужно знать прямо сейчас"</h2> с 5-6 пунктами.
        - В самом конце добавь блок <p><i>P.S. [твой личный дерзкий вывод]</i></p>.

        МНЕНИЕ ЭКСПЕРТА (вставь в поле content перед P.S.):
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border-left: 4px solid #8b5cf6; padding: 25px; margin: 40px 0; border-radius: 12px; color: #e2e8f0;">
          <h4 style="margin-top: 0; color: #a78bfa; text-transform: uppercase; font-size: 14px; margin-bottom: 12px;">⚡ Мнение эксперта</h4>
          <p style="font-style: italic; line-height: 1.6; margin-bottom: 0;">[Вывод от лица {sel_role}]</p>
        </div>

        Верни ответ СТРОГО в формате JSON:
        {{
          "title": "{target_topic}",
          "excerpt": "Мета-описание (150-160 символов)",
          "content": "HTML-текст статьи (минимум 1200 слов)",
          "photo_keywords": "3-5 английских слов для атмосферного фото"
        }}
        """

        raw_res = await mm.generate(prompt)
        
        # Очистка JSON от возможных префиксов Markdown
        json_str = re.search(r'\{.*\}', raw_res, re.DOTALL).group(0)
        data = json.loads(json_str)

        # --- 3. ФОТО (PEXELS) ---
        PEXELS_KEY = "твой_ключ" # ЗАМЕНИ НА СВОЙ КЛЮЧ
        query = data.get('photo_keywords', 'dark technology atmospheric')
        img_url = "https://images.unsplash.com/photo-1614741118887-7a4ee193a5fa?w=1200"

        try:
            px_url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=1&orientation=landscape"
            px_res = requests.get(px_url, headers={"Authorization": PEXELS_KEY}, timeout=10)
            if px_res.status_code == 200:
                photos = px_res.json().get('photos', [])
                if photos: img_url = photos[0]['src']['large']
        except: pass

        # --- 4. СЛАГ И ПУБЛИКАЦИЯ ---
        def slugify(text):
            tr = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ы":"y","э":"e","ю":"yu","я":"ya"}
            # Убираем лишние символы и конвертируем кириллицу
            res_slug = "".join(tr.get(c, c) for c in text.lower())
            return re.sub(r'[^a-z0-9]+', '-', res_slug).strip('-')

        final_title = data.get("title", target_topic)
        final_slug = slugify(final_title) 

        # Вставка в базу данных Supabase
        supabase.table("posts").insert({
            "title": final_title,
            "slug": final_slug,
            "image_url": img_url,
            "excerpt": data.get('excerpt', ''),
            "content": data.get('content')
        }).execute()

        print(f"🚀 Статья опубликована: {final_title}")

        return {"status": "success", "title": final_title, "slug": final_slug}

    except Exception as e:
        # Этот блок ОБЯЗАТЕЛЕН для закрытия try
        print(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- ПОЛУЧЕНИЕ СПИСКА ПОСТОВ ---
@app.get("/api/posts")
async def get_posts(page: int = 1, limit: int = 6):
    try:
        start = (page - 1) * limit
        end = start + limit - 1

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
        print(f"🚨 Ошибка API: {e}")
        return {"error": str(e)}
@app.get("/404", response_class=HTMLResponse)
async def error_404_page(request: Request):
    return templates.TemplateResponse(request=request, name="404.html")

@app.get("/premium", response_class=HTMLResponse)
async def premium_page(request: Request):
    return templates.TemplateResponse(request=request, name="premium.html")

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="about.html")

@app.get("/guide", response_class=HTMLResponse)
async def guide_page(request: Request):
    return templates.TemplateResponse(request=request, name="guide.html")

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html")

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    return templates.TemplateResponse(request=request, name="disclaimer.html")

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
    # Задаем расширение файла на лету, чтобы скачанные wav не сохранялись как mp3
    ext = os.path.splitext(file)[1]
    return FileResponse(path=path, filename=f"speechclone{ext}") if os.path.exists(path) else HTMLResponse("404")

@app.post("/chat")
async def chat_api(req: ChatRequest):
    reply = await mm.generate(req.message)
    return {"reply": reply}

@app.post("/api/generate")
async def api_generate_web(r: TTSRequest):
    try:
        # 1. Авто-определение расширения (wav для новых, mp3 для Edge)
        is_p = r.voice.endswith(".onnx")
        is_k = r.voice.startswith(("af_", "am_", "bf_", "bm_"))
        ext = "wav" if (is_p or is_k) else "mp3"
        
        fid = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(AUDIO_DIR, fid)

        # 2. ГЕНЕРАЦИЯ
        if is_k:
            if 'kokoro' in globals() and kokoro:
                import soundfile as sf
                # Генерируем Kokoro
                samples, sample_rate = kokoro.create(r.text, voice=r.voice, speed=1.0, lang="en-us")
                sf.write(path, samples, sample_rate, format='wav')
            else:
                return {"success": False, "error": "Kokoro не инициализирован"}
                
        elif is_p:
            # Piper через HF Space
            token = os.getenv('TOKEN_PIPER')
            hf_url = "https://sercos-oleg-studio-v2.hf.space/tts"
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {token}"}
                params = {"text": r.text, "voice": r.voice, "speed": 0.9}
                async with session.get(hf_url, params=params, headers=headers, timeout=60) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                    else:
                        return {"success": False, "error": f"Piper API Error: {resp.status}"}
        
        else:
            # Стандартный Edge TTS
            rates = {"natural": "+0%", "slow": "-20%", "fast": "+20%"}
            await edge_tts.Communicate(r.text, r.voice, rate=rates.get(r.mode, "+0%")).save(path)

        # 3. ПРОВЕРКА ФАЙЛА И ОТВЕТ
        if os.path.exists(path) and os.path.getsize(path) > 0:
            # Возвращаем структуру, которую ждет твой JS
            return {
                "success": True, 
                "audio_url": f"/static/audio/{fid}", 
                "fid": fid
            }
        else:
            return {"success": False, "error": "Файл не был создан"}

    except Exception as e:
        # Если ошибка здесь, JS покажет её в alert
        print(f"Ошибка сервера: {str(e)}")
        return {"success": False, "error": str(e)}
@app.on_event("startup")
async def startup_event():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)')
    conn.commit(); conn.close()
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
