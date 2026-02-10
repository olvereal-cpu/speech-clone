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
# ДОБАВЛЯЕМ ИМПОРТЫ БОТА
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Создаем структуру папок
for path in ["static", "static/audio", "static/images/blog"]:
    os.makedirs(os.path.join(BASE_DIR, path), exist_ok=True)

# Очистка старых файлов при запуске
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

# ОБНОВЛЕННАЯ МОДЕЛЬ (добавлен mode)
class TTSRequest(BaseModel):
    text: str
    voice: str
    mode: str = "natural"

# --- ОБЩАЯ ФУНКЦИЯ ГЕНЕРАЦИИ (ДЛЯ САЙТА И БОТА) ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join(BASE_DIR, "static/audio", file_id)
    
    # Настройки пресетов
    rates = {"natural": "-10%", "slow": "-25%", "fast": "+10%"}
    pitches = {"natural": "-5Hz", "slow": "0Hz", "fast": "+2Hz"}
    
    rate = rates.get(mode, "+0%")
    pitch = pitches.get(mode, "+0Hz")

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(file_path)
    return file_id

# --- ЛОГИКА ТЕЛЕГРАМ БОТА ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Пришли мне текст, и я озвучу его качественным голосом (Dmitry Neural).")

@dp.message()
async def handle_text(message: types.Message):
    if not message.text: return
    status_msg = await message.answer("⌛ Генерирую аудио, подождите...")
    try:
        # Бот по умолчанию использует режим natural и голос Дмитрий
        file_id = await generate_speech_logic(message.text[:1000], "ru-RU-DmitryNeural", "natural")
        file_path = os.path.join(BASE_DIR, "static/audio", file_id)
        
        await message.answer_audio(types.FSInputFile(file_path))
        await status_msg.delete()
    except Exception as e:
        await message.answer("Произошла ошибка при генерации.")

# --- МАРШРУТЫ САЙТА ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/voices", response_class=HTMLResponse)
async def voices(request: Request):
    return templates.TemplateResponse("voices.html", {"request": request})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer(request: Request):
    return templates.TemplateResponse("disclaimer.html", {"request": request})

@app.get("/blog", response_class=HTMLResponse)
async def blog_index(request: Request):
    return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def get_blog_post(request: Request, post_name: str):
    template_name = f"blog/{post_name}.html"
    if not os.path.exists(os.path.join(BASE_DIR, "templates", template_name)):
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return templates.TemplateResponse(template_name, {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{file}"})

@app.get("/ads.txt")
async def get_ads_txt():
    file_path = os.path.join(BASE_DIR, "ads.txt")
    if os.path.exists(file_path): return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="ads.txt not found")

# ОБНОВЛЕННЫЙ API МАРШРУТ
@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text or len(request.text) > 2000:
        raise HTTPException(status_code=400, detail="Text empty or too long")
    
    try:
        file_id = await generate_speech_logic(request.text, request.voice, request.mode)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        print(f"TTS Error: {e}")
        raise HTTPException(status_code=500, detail="TTS Engine Error")

@app.exception_handler(404)
async def custom_404_handler(request: Request, __):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

# ЗАПУСК БОТА ВМЕСТЕ С СЕРВЕРОМ
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(dp.start_polling(bot))













