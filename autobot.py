import os
import requests
import time

# Берем ключ из переменных окружения GitHub (Secrets)
# Если ключа нет в Secrets, используем "Barakuda" по умолчанию
MY_SECRET = os.getenv("MY_SECRET_KEY", "Barakuda") 
API_URL = "https://speechclone.online/api/admin/generate-post"

def run_autopilot():
    print(f"🚀 [{time.strftime('%H:%M:%S')}] Запуск генерации на speechclone.online...")
    
    payload = {"message": "."} # Сигнал автопилоту
    
    # ОБЯЗАТЕЛЬНО добавляем заголовки, иначе сервер выдаст 403
    headers = {
        "Content-Type": "application/json",
        "x-secret-key": MY_SECRET
    }
    
    try:
        # Увеличиваем timeout, ИИ работает медленно
        response = requests.post(
            API_URL, 
            json=payload, 
            headers=headers, # Передаем ключ!
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ УСПЕХ! Статья создана: {result.get('title') or result.get('slug')}")
        elif response.status_code == 403:
            print(f"🚫 ОШИБКА ДОСТУПА: Сервер отклонил ключ (Forbidden).")
        else:
            print(f"❌ ОШИБКА СЕРВЕРА: {response.status_code}")
            print(f"Детали: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ ОШИБКА: Тайм-аут (120с вышли).")
    except Exception as e:
        print(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {e}")

if __name__ == "__main__":
    run_autopilot()
