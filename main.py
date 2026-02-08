from fastapi import FastAPI, Request, HTTPException from fastapi.responses import HTMLResponse, FileResponse from fastapi.staticfiles import StaticFiles from fastapi.templating import Jinja2Templates from pydantic import BaseModel import os import edge_tts import uuid import asyncio

app = FastAPI()

Создаем структуру папок при запуске
for path in ["static", "static/audio", "static/images/blog"]: os.makedirs(path, exist_ok=True)

Очистка старых файлов при старте сервера
def clean_audio(): audio_dir = "static/audio" if os.path.exists(audio_dir): for filename in os.listdir(audio_dir): file_path = os.path.join(audio_dir, filename) try: if os.path.isfile(file_path): os.unlink(file_path) except Exception as e: print(f"Error cleaning: {e}")

clean_audio()

Подключаем статику и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static") templates = Jinja2Templates(directory="templates")

Модель данных для API
class TTSRequest(BaseModel): text: str voice: str

--- МАРШРУТЫ СТРАНИЦ ---
@app.get("/", response_class=HTMLResponse) async def home(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@app.get("/voices", response_class=HTMLResponse) async def voices(request: Request): return templates.TemplateResponse("voices.html", {"request": request})

@app.get("/about", response_class=HTMLResponse) async def about(request: Request): return templates.TemplateResponse("about.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse) async def guide(request: Request): return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse) async def privacy(request: Request): return templates.TemplateResponse("privacy.html", {"request": request})

Блог: Список статей
@app.get("/blog", response_class=HTMLResponse) async def blog_index(request: Request): return templates.TemplateResponse("blog_index.html", {"request": request})

Блог: Сами статьи
@app.get("/blog/{post_name}", response_class=HTMLResponse) async def get_blog_post(request: Request, post_name: str): post_path = f"blog/{post_name}.html" if not os.path.exists(os.path.join("templates", post_path)): return templates.TemplateResponse("404.html", {"request": request}, status_code=404) return templates.TemplateResponse(post_path, {"request": request})

Страница ожидания скачивания
@app.get("/download-page", response_class=HTMLResponse) async def download_page(request: Request, file: str): return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{file}"})

Файл ads.txt для Google AdSense
@app.get("/ads.txt") async def get_ads_txt(): if os.path.exists("ads.txt"): return FileResponse("ads.txt") raise HTTPException(status_code=404, detail="ads.txt not found")

--- API ДЛЯ ГЕНЕРАЦИИ ГОЛОСА ---
@app.post("/api/generate") async def generate(request: TTSRequest): if not request.text or len(request.text) > 2000: raise HTTPException(status_code=400, detail="Text empty or too long")

file_id = f"{uuid.uuid4()}.mp3"
file_path = os.path.join("static/audio", file_id)

try:
    # Используем библиотеку edge-tts для генерации
    communicate = edge_tts.Communicate(request.text, request.voice)
    await communicate.save(file_path)
    return {"audio_url": f"/static/audio/{file_id}"}
except Exception as e:
    print(f"TTS Error: {e}")
    raise HTTPException(status_code=500, detail="TTS Engine Error")
--- ОБРАБОТКА ОШИБКИ 404 ---
@app.exception_handler(404) async def custom_404_handler(request: Request, __): return templates.TemplateResponse("404.html", {"request": request}, status_code=404)



