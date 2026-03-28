import os
import uuid
import asyncio
import sqlite3
import edge_tts
import google.generativeai as genai
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile, LabeledPrice, PreCheckoutQuery

# --- КОНФИГУРАЦИЯ ---
ADMIN_ID = int(os.getenv("ADMIN_ID", "430747895"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Берем ключ именно из GEMINI_KEY, как указано на Render
GEMINI_API_KEY = os.getenv("GEMINI_KEY") 

CHANNEL_ID = "@speechclone"
CHANNEL_URL = "https://t.me/speechclone"
SITE_URL = "https://speechclone.online"
PREMIUM_KEYS = ["VIP-777", "PRO-2026", "START-99", "TEST-KEY"]

# --- ИНИЦИАЛИЗАЦИЯ GEMINI (ПРЯМАЯ УСТАНОВКА 3.1 FLASH LITE) ---
class ModelManager:
    def __init__(self, api_key):
        self.api_key = api_key
        self.target_model = 'gemini-3.1-flash-lite'
        self.safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        genai.configure(api_key=self.api_key)
        self.active_model = genai.GenerativeModel(
            model_name=self.target_model, 
            safety_settings=self.safety_settings
        )

    async def generate(self, prompt):
        try:
            resp = await asyncio.to_thread(self.active_model.generate_content, prompt)
            return resp.text
        except Exception as e:
            return f"Ошибка ИИ: {str(e)}"

mm = ModelManager(GEMINI_API_KEY)

# --- ПУТИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
AUDIO_DIR = os.path.join(STATIC_DIR, "audio")
DB_PATH = os.path.join(BASE_DIR, "users.db")

os.makedirs(AUDIO_DIR, exist_ok=True)

# --- ДАННЫЕ БЛОГА (ПОЛНЫЕ СТАТЬИ) ---
BLOG_POSTS = [
    {
        "id": 1001, "title": "Как ИИ изменит ваш голос в 2026 году", "slug": "kak-ii-izmenit-vash-golos", 
        "image": "https://images.unsplash.com/photo-1589254065878-42c9da997008?q=80&w=800", 
        "excerpt": "Разбираемся в будущем клонирования...", "date": "10.03.2026", "author": "Алекс", "category": "Технологии", "color": "blue",
        "content": "<p>В 2026 году технологии синтеза речи достигли невероятного сходства с человеческим голосом. Раньше ИИ звучал роботоподобно, но теперь нейросети учитывают даже микро-интонации, задержки дыхания и эмоциональный фон. <b>Клонирование голоса</b> стало доступным каждому пользователю смартфона.</p><p>Основной прорыв произошел в области <i>Zero-shot TTS</i>, где системе достаточно всего 3 секунд записи вашего голоса, чтобы воспроизвести любую фразу с вашим тембром на 50 языках мира.</p>"
    },
    {
        "id": 1002, "title": "Секреты идеального подкаста", "slug": "sekrety-sozdaniya-podkasta-ii", 
        "image": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=800", 
        "excerpt": "Автоматизация монтажа с помощью ИИ.", "date": "08.03.2026", "author": "М. Вудс", "category": "Подкастинг", "color": "purple",
        "content": "<p>Создание подкаста всегда было трудоемким процессом. Нужно арендовать студию, бороться с шумами и часами монтировать дорожки. В 2026 году всё изменилось.</p><p>Используя <b>SpeechClone</b>, авторы могут записывать сценарий текстом, а ИИ озвучивает его идеальным студийным голосом. Больше не нужно переписывать дубли, если вы ошиблись в слове — просто исправьте текст в редакторе.</p>"
    },
    {
        "id": 1003, "title": "Клонирование голоса: Этика и закон", "slug": "ethics-of-voice-cloning", 
        "image": "https://images.unsplash.com/photo-1507413245164-6160d8298b31?q=80&w=800", 
        "excerpt": "Где грань между инновацией и кражей личности?", "date": "05.03.2026", "author": "Юрист ИИ", "category": "Право", "color": "red",
        "content": "<p>С ростом популярности дипфейков юридические системы стран мира начали активно внедрять законы о <b>цифровой личности</b>. Теперь ваш голос — это ваша собственность, защищенная законом так же, как и отпечатки пальцев. Использование чужого голоса без лицензии преследуется по закону.</p>"
    },
    {
        "id": 1004, "title": "Топ 10 голосов для рекламы", "slug": "top-10-voices-ad", 
        "image": "https://images.unsplash.com/photo-1478737270239-2fccd2c7fd94?q=80&w=800", 
        "excerpt": "Какие тембры продают лучше всего?", "date": "01.03.2026", "author": "Маркетолог", "category": "Маркетинг", "color": "green",
        "content": "<p>Исследования показывают, что выбор правильного голоса увеличивает конверсию рекламы на 40%. В 2026 году нейромаркетинг выделил фаворитов: <b>бархатистые низкие мужские голоса</b> вызывают доверие в финансовом секторе.</p>"
    },
    {
        "id": 1005, "title": "Озвучка книг: Новая эра", "slug": "audiobook-new-era", 
        "image": "https://images.unsplash.com/photo-1495446815901-a7297e633e8d?q=80&w=800", 
        "excerpt": "Как за неделю озвучить целую серию романов.", "date": "25.02.2026", "author": "Книжник", "category": "Литература", "color": "yellow",
        "content": "<p>Раньше на озвучку одной книги уходил месяц работы диктора. Сегодня автор может загрузить текст в <b>SpeechClone</b>, выбрать несколько голосов для разных персонажей и получить готовую аудиокнигу за пару часов.</p>"
    },
    {
        "id": 1006, "title": "ИИ в видеоиграх: Живые диалоги", "slug": "ai-in-gaming", 
        "image": "https://images.unsplash.com/photo-1542751371-adc38448a05e?q=80&w=800", 
        "excerpt": "NPC, которые действительно говорят с вами.", "date": "20.02.2026", "author": "Геймер", "category": "Игры", "color": "indigo",
        "content": "<p>Представьте игру, где каждый персонаж — это не просто набор записанных фраз, а живой собеседник. В 2026 году крупные студии перешли на динамическую генерацию речи с помощью ИИ.</p>"
    },
    {
        "id": 1007, "title": "Как работает Edge TTS?", "slug": "how-edge-tts-works", 
        "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?q=80&w=800", 
        "excerpt": "Технический разбор движка от Microsoft.", "date": "15.02.2026", "author": "Разработчик", "category": "Технологии", "color": "gray",
        "content": "<p>Edge TTS — это один из самых стабильных движков на рынке. Он использует нейронные сети для предсказания спектрограмм звука на основе текстовых токенов через WebSocket.</p>"
    },
    {
        "id": 1008, "title": "Психология восприятия голоса", "slug": "psychology-of-voice", 
        "image": "https://images.unsplash.com/photo-1526256262350-7da7584cf5eb?q=80&w=800", 
        "excerpt": "Почему мы доверяем одним голосам и боимся других.", "date": "10.02.2026", "author": "Доктор Пси", "category": "Наука", "color": "pink",
        "content": "<p>Голос несет в себе больше информации, чем слова. Мы подсознательно считываем уверенность, доброту или агрессию по частотным характеристикам звука.</p>"
    },
    {
        "id": 1009, "title": "ИИ-переводчики с сохранением голоса", "slug": "voice-translation", 
        "image": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800", 
        "excerpt": "Говорите на китайском своим собственным голосом.", "date": "05.02.2026", "author": "Лингвист", "category": "Технологии", "color": "orange",
        "content": "<p>Языковой барьер окончательно разрушен. Современные системы синхронного перевода не только заменяют слова, но и <b>клонируют ваш тембр</b> на лету.</p>"
    },
    {
        "id": 1010, "title": "Заработок на озвучке в 2026", "slug": "money-on-voice", 
        "image": "https://images.unsplash.com/photo-1554224155-169641357599?q=80&w=800", 
        "excerpt": "Как фрилансеры используют ИИ для дохода.", "date": "01.02.2026", "author": "Бизнес-аналитик", "category": "Бизнес", "color": "emerald",
        "content": "<p>Рынок дикторских услуг трансформировался. Успешные фрилансеры теперь не просто читают текст, а создают цифровые слепки голоса и продают лицензии.</p>"
    },
    {
        "id": 1011, "title": "Музыка и ИИ: Вокал без певца", "slug": "ai-vocals-music", 
        "image": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?q=80&w=800", 
        "excerpt": "Как создаются хиты с виртуальными вокалистами.", "date": "28.01.2026", "author": "Продюсер", "category": "Музыка", "color": "rose",
        "content": "<p>В чартах 2026 года всё чаще появляются песни, вокал в которых полностью сгенерирован. Продюсеры могут «нанять» виртуальную версию легендарных певцов.</p>"
    },
    {
        "id": 1012, "title": "Будущее радио: ИИ-ведущие", "slug": "future-radio-ai", 
        "image": "https://images.unsplash.com/photo-1485579149621-3123dd979885?q=80&w=800", 
        "excerpt": "Радиостанции, работающие полностью на нейросетях.", "date": "20.01.2026", "author": "Радиофан", "category": "Медиа", "color": "cyan",
        "content": "<p>Традиционное радио уступает место персонализированным станциям. ИИ-ведущий знает ваши музыкальные вкусы и читает новости специально для вас.</p>"
    },
    {
        "id": 1013, "title": "Кибербезопасность: Дипфейки", "slug": "cybersec-deepfakes", 
        "image": "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=800", 
        "excerpt": "Как защитить себя от голосового мошенничества.", "date": "15.01.2026", "author": "Хакер", "category": "Безопасность", "color": "slate",
        "content": "<p>К сожалению, технологии клонирования голоса используют и преступники. Телефонное мошенничество вышло на новый уровень. Используйте кодовые слова для семьи.</p>"
    },
    {
        "id": 1014, "title": "ИИ для людей с потерей речи", "slug": "ai-for-disability", 
        "image": "https://images.unsplash.com/photo-1516542077369-6de03c158542?q=80&w=800", 
        "excerpt": "Возвращение голоса тем, кто его потерял.", "date": "10.01.2026", "author": "Врач", "category": "Медицина", "color": "teal",
        "content": "<p>Это самое благородное применение ИИ. Пациенты с заболеваниями связок теперь могут общаться с миром своим настоящим голосом через нейросети.</p>"
    },
    {
        "id": 1015, "title": "Эволюция интерфейсов: Голос вместо рук", "slug": "voice-interfaces", 
        "image": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?q=80&w=800", 
        "excerpt": "Почему в 2026 году мы перестанем печатать.", "date": "05.01.2026", "author": "Футуролог", "category": "Будущее", "color": "violet",
        "content": "<p>Клавиатуры становятся пережитком прошлого. Благодаря идеальному распознаванию и синтезу речи, взаимодействие с техникой стало естественным диалогом.</p>"
    }
]

VOICES = {
    "🇷🇺 Дмитрий": "ru-RU-DmitryNeural", "🇷🇺 Светлана": "ru-RU-SvetlanaNeural",
    "🇰🇿 Даулет": "kk-KZ-DauletNeural", "🇰🇿 Айгуль": "kk-KZ-AigulNeural",
    "🇺🇸 Guy (EN)": "en-US-GuyNeural", "🇺🇦 Остап (UA)": "uk-UA-OstapNeural",
    "🇹🇷 Ahmet (TR)": "tr-TR-AhmetNeural", "🇪🇸 Alvaro (ES)": "es-ES-AlvaroNeural",
    "🇩🇪 Conrad (DE)": "de-DE-ConradNeural", "🇵🇱 Marek (PL)": "pl-PL-MarekNeural",
    "🇫🇷 Remy (FR)": "fr-FR-RemyNeural", "🇯🇵 Keita (JP)": "ja-JP-KeitaNeural",
    "🇨🇳 Yunxi (CN)": "zh-CN-YunxiNeural"
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, voice TEXT DEFAULT "ru-RU-DmitryNeural")')
    conn.execute('''CREATE TABLE IF NOT EXISTS posts 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, slug TEXT, image TEXT, 
                     excerpt TEXT, content TEXT, date TEXT, author TEXT, category TEXT, color TEXT)''')
    conn.commit()
    conn.close()

init_db()

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
    kb = InlineKeyboardBuilder()
    for name in VOICES.keys(): kb.button(text=name, callback_data=f"v_{name}")


