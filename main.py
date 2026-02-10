import os
import re
import uuid
import asyncio
import edge_tts
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI(redirect_slashes=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = "8337208157:AAEPSueD83LmT96Yr1ThAkX3V7HxvHWdh9U"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_data = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Гарантируем наличие папок
for path in ["static", "static/audio", "static/images/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

def clean_audio():
    audio_dir = os.path.join(BASE_DIR, "static/audio")
    if os.path.exists(audio_dir):
        for filename in os.listdir(audio_dir):
            file_path = os.path.join(audio_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error cleaning: {e}")

clean_audio()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

# --- ЛОГИКА ГЕНЕРАЦИИ (СТАБИЛЬНАЯ) ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    audio_dir = os.path.join(BASE_DIR, "static/audio")
    file_path = os.path.join(audio_dir, file_id)
    
    # Исправляем ударения: "+а" на "а" с невидимым символом ударения (Unicode U+0301)
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        # Меняем местами + и гласную, чтобы символ ударения встал ПОСЛЕ гласной
        return re.sub(r'\+([%s])' % vowels, r'\1\u0301', t)

    processed_text = fix_stress(text)
    
    rates = {"natural": "-10%", "slow": "-20%", "fast": "+15%"}
    pitches = {"natural": "-5Hz", "slow": "+0Hz", "fast": "+2Hz"}
    
    rate = rates.get(mode, "+0%")
    pitch = pitches.get(mode, "+0Hz")

    try:
        # Проверяем наличие папки прямо перед сохранением
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir, exist_ok=True)
            
        communicate = edge_tts.Communicate(processed_text, voice, rate=rate, pitch=pitch)
        await communicate.save(file_path)
    except Exception as e:
        print(f"TTS Error: {e}")
        # Запасной вариант без параметров
        communicate = edge_tts.Communicate(processed_text, voice)
        await communicate.save(file_path)
        
    return file_id

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [[types.KeyboardButton(text="/start")]]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "👋 Привет! Пришли текст (до 1000 знаков).\n\n"
        "💡 Используй **+** перед гласной для ударения (з+амок).",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data.pop(user_id)
    await callback.message.answer("🏠 Пришлите новый текст:")
    await callback.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text == "/start": return
    user_data[message.from_user.id] = {"text": message.text}
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇦 Остап", callback_data="v_uk-UA-OstapNeural"),
                types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Ava", callback_data="v_en-US-AvaNeural"),
                types.InlineKeyboardButton(text="🇺🇸 Guy", callback_data="v_en-US-GuyNeural"))
    
    await message.answer("Выберите голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["voice"] = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="Natural", callback_data="m_natural"),
        types.InlineKeyboardButton(text="Slow", callback_data="m_slow"),
        types.InlineKeyboardButton(text="Fast", callback_data="m_fast")
    )
    await callback.message.edit_text("Выберите режим:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    user_id = callback.from_user.id
    if user_id not in user_data:
        return await callback.message.answer("⚠️ Ошибка сессии. Нажмите /start")
    
    data = user_data[user_id]
    status_msg = await callback.message.edit_text("⌛ Генерирую...")
    
    try:
        file_id = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        nav = InlineKeyboardBuilder()
        nav.row(types.InlineKeyboardButton(text="🏠 Озвучить ещё", callback_data="main_menu"))

        await callback.message.answer_audio(
            types.FSInputFile(file_path),
            caption="✅ Готово! https://speechclone.online",
            reply_markup=nav.as_markup()
        )
        await status_msg.delete()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# --- API ---

@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="Текст пустой")
    try:
        file_id = await generate_speech_logic(request.text, request.voice, request.mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        if os.path.exists(file_path):
            return {"audio_url": f"/static/audio/{file_id}"}
        else:
            raise Exception("Файл не найден на диске")
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка на сервере")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-audio/{file_name}")
async def get_audio(file_name: str):
    file_path = os.path.join(BASE_DIR, "static/audio", file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл удален или не найден")
    return FileResponse(path=file_path, filename=f"audio_{file_name}", media_type='audio/mpeg')

@app.on_event("startup")
async def startup_event():
    if not os.environ.get("GUNICORN_STARTED"):
        os.environ["GUNICORN_STARTED"] = "true"
        asyncio.create_task(dp.start_polling(bot))




















