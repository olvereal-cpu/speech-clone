# SpeechClone AI - Free Text-to-Speech Service

Простой и эффективный сервис для озвучки текста онлайн. Построен на FastAPI и gTTS.

## Особенности
- Многостраничная структура (SEO-friendly)
- Поддержка более 50 языков
- Без регистрации и лимитов
- Полная адаптивность под мобильные устройства

## Технологии
- **Backend:** Python 3.10+, FastAPI, Gunicorn
- **Frontend:** HTML5, Tailwind CSS, Jinja2
- **TTS Engine:** Google Text-to-Speech (gTTS)

## Как запустить локально
1. Установите зависимости: `pip install -r requirements.txt`
2. Запустите сервер: `uvicorn main:app --reload`
3. Откройте `http://127.0.0.1:8000`