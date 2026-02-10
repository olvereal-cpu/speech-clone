import os
import re
import uuid
import asyncio
import ssl
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

# --- ФИКС SSL (для стабильной связи с Microsoft на любых серверах) ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

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

# Гарантируем наличие всех папок
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

# --- ЛОГИКА ГЕНЕРАЦИИ (ИСПРАВЛЕНА ОШИБКА BAD ESCAPE) ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    audio_dir = os.path.join(BASE_DIR, "static/audio")
    file_path = os.path.join(audio_dir, file_id)
    
    # Очистка текста от лишних символов
    clean_text = re.sub(r'[^\w\s\+\!\?\.\,\:\;\-]', '', text).strip()
    
    # Исправляем ударения через chr(769), чтобы избежать ошибки "bad escape \u"
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
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise ValueError("Empty file generated")
    except Exception as e:
        print(f"Fallback due to error: {e}")
        communicate = edge_tts.Communicate(clean_text.replace("+", ""), voice)
        await communicate.save(file_path)
        
    return file_id

# --- ТЕЛЕГРАМ БОТ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Пришли текст для озвучки.\n"
        "💡 Используй **+** перед гласной для ударения (например, з+амок)."
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    if callback.from_user.id in user_data:
        user_data.pop(callback.from_user.id)
    await callback.message.answer("🏠 Жду новый текст:")
    await callback.answer()

@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"): return
    user_id = message.from_user.id
    user_data[user_id] = {"text": message.text}
    
    builder = InlineKeyboardBuilder()
    # Восстановленный полный список голосов
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
    
    await message.answer("Выберите голос:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("v_"))
async def select_voice(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["voice"] = callback.data.split("_")[1]
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="Обычный", callback_data="m_natural"),
        types.InlineKeyboardButton(text="Медленно", callback_data="m_slow"),
        types.InlineKeyboardButton(text="Быстро", callback_data="m_fast")
    )
    await callback.message.edit_text("Выберите режим звучания:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("m_"))
async def select_mode(callback: types.CallbackQuery):
    mode = callback.data.split("_")[1]
    user_id = callback.from_user.id
    if user_id not in user_data:
        return await callback.message.answer("⚠️ Сессия истекла. Пришлите текст заново.")
    
    data = user_data[user_id]
    status_msg = await callback.message.edit_text("⌛ Озвучиваю...")
    
    try:
        file_id = await generate_speech_logic(data["text"][:1000], data["voice"], mode)
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        nav = InlineKeyboardBuilder()
        nav.row(types.InlineKeyboardButton(text="🏠 Озвучить ещё", callback_data="main_menu"))

        await callback.message.answer_audio(
            types.FSInputFile(file_path),
            caption="✅ Готово! Озвучено на SpeechClone.online",
            reply_markup=nav.as_markup()
        )
        await status_msg.delete()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# --- МАРШРУТЫ САЙТА (ПОЛНЫЙ СПИСОК) ---

@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text: raise HTTPException(400, "Empty text")
    try:
        file_id = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/get-audio/{file_name}")
async def get_audio(file_name: str):
    file_path = os.path.join(BASE_DIR, "static/audio", file_name)
    if not os.path.exists(file_path): raise HTTPException(404)
    return FileResponse(file_path, media_type='audio/mpeg')

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {
        "request": request, "file_name": file, "download_link": f"/get-audio/{file}"
    })

# Инфо-страницы
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

# Блог
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





















