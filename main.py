from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import edge_tts
import uuid
import asyncio
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

app = FastAPI(redirect_slashes=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- НАСТРОЙКИ БОТА ---
BOT_TOKEN = "8337208157:AAEPSueD83LmT96Yr1ThAkX3V7HxvHWdh9U"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Временное хранилище настроек пользователей
user_data = {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Создание необходимых папок
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

# Очистка при запуске
clean_audio()

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

# --- ЛОГИКА ГЕНЕРАЦИИ (С ФИКСОМ УДАРЕНИЙ) ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    
    # Исправляем ударения: меняем "+а" на "а" с невидимым символом ударения
    def fix_stress(t):
        vowels = "аеёиоуыэюяАЕЁИОУЫЭЮЯaeiouyAEIOUY"
        return re.sub(r'\+([%s])' % vowels, r'\1\u0301', t)

    processed_text = fix_stress(text)
    
    rates = {"natural": "-10%", "slow": "-20%", "fast": "+15%"}
    pitches = {"natural": "-5Hz", "slow": "+0Hz", "fast": "+2Hz"}
    
    rate = rates.get(mode, "+0%")
    pitch = pitches.get(mode, "+0Hz")

    try:
        communicate = edge_tts.Communicate(processed_text, voice, rate=rate, pitch=pitch)
        await communicate.save(file_path)
    except Exception as e:
        print(f"TTS Error, trying fallback: {e}")
        # Если с параметрами не вышло, пробуем простую генерацию
        communicate = edge_tts.Communicate(processed_text, voice)
        await communicate.save(file_path)
        
    return file_id

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [[types.KeyboardButton(text="/start")]]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "👋 Привет! Пришли мне текст для озвучки (до 1000 знаков).\n\n"
        "💡 Используй **+** перед гласной для ударения (например: з+амок).",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        user_data.pop(user_id)
    await callback.message.answer("🏠 Пришлите новый текст для озвучки:")
    await callback.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text == "/start": return
    user_id = message.from_user.id
    user_data[user_id] = {"text": message.text}
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🇷🇺 Дмитрий", callback_data="v_ru-RU-DmitryNeural"),
                types.InlineKeyboardButton(text="🇷🇺 Светлана", callback_data="v_ru-RU-SvetlanaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇦 Остап", callback_data="v_uk-UA-OstapNeural"),
                types.InlineKeyboardButton(text="🇰🇿 Даулет", callback_data="v_kk-KZ-DauletNeural"))
    builder.row(types.InlineKeyboardButton(text="🇺🇸 Ava", callback_data="v_en-US-AvaNeural"),
                types.InlineKeyboardButton(text="🇺🇸 Guy", callback_data="v_en-US-GuyNeural"))
    builder.row(types.InlineKeyboardButton(text="🇬🇧 Sonia", callback_data="v_en-GB-SoniaNeural"))
    builder.row(types.InlineKeyboardButton(text="🇩🇪 Немецкий", callback_data="v_de-DE-KatjaNeural"),
                types.InlineKeyboardButton(text="🇫🇷 Французский", callback_data="v_fr-FR-DeniseNeural"))
    builder.row(types.InlineKeyboardButton(text="🇨🇳 Китайский", callback_data="v_zh-CN-YunxiNeural"),
                types.InlineKeyboardButton(text="🇯🇵 Японский", callback_data="v_ja-JP-NanamiNeural"))
    
    await message.answer("Выберите голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    voice = callback.data.split("_")[1]
    user_data[callback.from_user.id]["voice"] = voice
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
        return await callback.message.answer("⚠️ Сессия истекла. Нажмите /start")
    
    data = user_data[user_id]
    status_msg = await callback.message.edit_text("⌛ Генерирую...")
    
    try:
        file_id = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        nav_builder = InlineKeyboardBuilder()
        nav_builder.row(types.InlineKeyboardButton(text="🏠 Озвучить ещё", callback_data="main_menu"))

        await callback.message.answer_audio(
            types.FSInputFile(file_path),
            caption="✅ Готово! https://speechclone.online",
            reply_markup=nav_builder.as_markup()
        )
        await status_msg.delete()
    except Exception as e:
        await callback.message.answer("❌ Ошибка.")

# --- МАРШРУТЫ САЙТА ---

@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text or len(request.text) > 2000:
        raise HTTPException(status_code=400, detail="Текст слишком длинный")
    try:
        file_id = await generate_speech_logic(request.text, request.voice, request.mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        # Проверка: если файл на диске есть, отдаем успех, даже если были мелкие ошибки API
        if os.path.exists(file_path):
            return {"audio_url": f"/static/audio/{file_id}"}
        else:
            raise Exception("File not created")
    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка генерации")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-audio/{file_name}")
async def get_audio(file_name: str):
    file_path = os.path.join(BASE_DIR, "static/audio", file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path=file_path, filename=f"audio_{file_name}", media_type='audio/mpeg')

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {
        "request": request, "file_name": file, "download_link": f"/get-audio/{file}"
    })

# Заглушки для остальных страниц
@app.get("/voices")
async def voices(request: Request): return templates.TemplateResponse("voices.html", {"request": request})
@app.get("/about")
async def about(request: Request): return templates.TemplateResponse("about.html", {"request": request})
@app.get("/guide")
async def guide(request: Request): return templates.TemplateResponse("guide.html", {"request": request})
@app.get("/privacy")
async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})
@app.get("/disclaimer")
async def disclaimer(request: Request): return templates.TemplateResponse("disclaimer.html", {"request": request})
@app.get("/blog")
async def blog_index(request: Request): return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{post_name}")
async def get_blog_post(request: Request, post_name: str):
    template_name = f"blog/{post_name}.html"
    if not os.path.exists(os.path.join(BASE_DIR, "templates", template_name)):
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return templates.TemplateResponse(template_name, {"request": request})

@app.get("/ads.txt")
async def get_ads_txt():
    path = os.path.join(BASE_DIR, "ads.txt")
    return FileResponse(path) if os.path.exists(path) else HTTPException(404)

@app.on_event("startup")
async def startup_event():
    if not os.environ.get("GUNICORN_STARTED"):
        os.environ["GUNICORN_STARTED"] = "true"
        asyncio.create_task(dp.start_polling(bot))


















