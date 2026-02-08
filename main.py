from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import edge_tts
import os
import uuid
import asyncio

app = FastAPI()

# Создаем структуру папок
for path in ["static", "static/audio", "static/images/blog"]:
    os.makedirs(path, exist_ok=True)

# Очистка старых файлов при запуске
def clean_audio():
    if os.path.exists("static/audio"):
        for filename in os.listdir("static/audio"):
            file_path = os.path.join("static/audio", filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error cleaning: {e}")

clean_audio()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class TTSRequest(BaseModel):
    text: str
    lang: str
    voice: str
# Маршрут для главной страницы блога
@app.get("/blog", response_class=HTMLResponse)
async def read_blog(request: Request):
    return templates.TemplateResponse("blog_index.html", {"request": request})

# Универсальный маршрут для всех статей блога
@app.get("/blog/{article_name}", response_class=HTMLResponse)
async def read_article(request: Request, article_name: str):
    # Проверяем, существует ли файл, чтобы сервер не падал
    file_path = f"blog/{article_name}.html"
    if os.path.exists(f"templates/{file_path}"):
        return templates.TemplateResponse(file_path, {"request": request})
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

# Маршрут для AdSense
@app.get("/ads.txt")
async def get_ads_txt():
    if os.path.exists("ads.txt"):
        return FileResponse("ads.txt")
    return "Файл ads.txt еще не создан", 404
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/download-page", response_class=HTMLResponse)
async def download_page(request: Request, file: str):
    return templates.TemplateResponse("download.html", {"request": request, "file_url": f"/static/audio/{file}"})

@app.get("/blog", response_class=HTMLResponse)
async def blog_index(request: Request):
    return templates.TemplateResponse("blog_index.html", {"request": request})

@app.get("/blog/{post_name}", response_class=HTMLResponse)
async def get_blog_post(request: Request, post_name: str):
    post_path = f"blog/{post_name}.html"
    if not os.path.exists(os.path.join("templates", post_path)):
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse(post_path, {"request": request})

@app.get("/voices", response_class=HTMLResponse)
async def voices(request: Request):
    return templates.TemplateResponse("voices.html", {"request": request})

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    return templates.TemplateResponse("guide.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.post("/api/generate")
async def generate(request: TTSRequest):
    if not request.text or len(request.text) > 2000:
        raise HTTPException(status_code=400, detail="Text too long")
    
    file_id = f"{uuid.uuid4()}.mp3"
    file_path = os.path.join("static/audio", file_id)
    
    try:
        communicate = edge_tts.Communicate(request.text, request.voice)
        await communicate.save(file_path)
        return {"audio_url": f"/static/audio/{file_id}"}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="TTS Engine Error")

