import os
import re
import uuid
import asyncio
import ssl
import edge_tts
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject # ДОБАВИЛИ CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- ФИКС SSL ---
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

# --- ЛОГИКА ГЕНЕРАЦИИ ---
async def generate_speech_logic(text: str, voice: str, mode: str):
    file_id = f"{uuid.uuid4()}.mp3"
    audio_dir = os.path.join(BASE_DIR, "static/audio")
    file_path = os.path.join(audio_dir, file_id)
    
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
    except Exception as e:
        print(f"Fallback due to error: {e}")
        communicate = edge_tts.Communicate(clean_text.replace("+", ""), voice)
        await communicate.save(file_path)
        
    return file_id

# --- ТЕЛЕГРАМ БОТ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    # ПРОВЕРКА НА ДИПЛИНК ДОНАТА (из кнопки на сайте)
    if command.args == "donate":
        try:
            # Отправляем инвойс. Для Stars (XTR) provider_token ВСЕГДА пустая строка.
            return await message.answer_invoice(
                title="Поддержать SpeechClone AI",
                description="Добровольный донат 50 Stars на развитие Open Source проекта.",
                payload="donate_stars_50",
                currency="XTR",
                prices=[types.LabeledPrice(label="Донат 50 ⭐️", amount=50)],
                provider_token="",
                start_parameter="donate_redirect", # Обязательный параметр для диплинков
                protect_content=True
            )
        except Exception as e:
            # Если не сработало, бот напишет ошибку в консоль и отправит текст пользователю
            print(f"ОШИБКА ИНВОЙСА: {e}")
            return await message.answer("💎 Для поддержки проекта отправьте Stars через меню или воспользуйтесь картой на сайте.")

    await message.answer(
        "👋 Привет! Пришли текст для озвучки.\n"
        "💡 Используй **+** перед гласной для ударения (например, з+амок)."
    )

# Подтверждение готовности принять платеж (обязательно!)
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.Pre_checkout_query):
    await pre_checkout_query.answer(ok=True)

# Уведомление об успешной оплате
@dp.message(F.successful_payment)
async def success_payment_handler(message: types.Message):
    await message.answer(
        "💎 **Оплата получена!**\n\n"
        "Огромное спасибо за поддержку. Вы помогаете проекту оставаться бесплатным и развиваться! ❤️"
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

# --- МАРШРУТЫ САЙТА ---

@app.get("/robots.txt")
async def robots_txt():
    content = """User-agent: *
Allow: /
Allow: /blog/
Allow: /static/
Disallow: /admin/
Sitemap: https://speechclone.online/sitemap.xml
Host: https://speechclone.online"""
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml")
async def sitemap_xml():
    path = os.path.join(BASE_DIR, "sitemap.xml")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/xml")
    
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://speechclone.online/</loc><priority>1.0</priority></url>
  <url><loc>https://speechclone.online/blog</loc><priority>0.8</priority></url>
</urlset>"""
    return Response(content=xml_content, media_type="application/xml")

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

@app.get("/contribute")
async def contribute(request: Request): 
    return templates.TemplateResponse("index.html", {"request": request, "scroll_to": "support"})

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






