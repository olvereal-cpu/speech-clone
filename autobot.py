import requests
import time

# Теперь пароль берется из секретов GitHub Actions
MY_SECRET = os.getenv("MY_SECRET_KEY", "Barakuda") 
API_URL = "https://speechclone.online/api/admin/generate-post"

def run_autopilot():
    print(f"🚀 [{time.strftime('%H:%M:%S')}] Запуск генерации статьи на speechclone.online...")
    
    payload = {"message": "."} # Сигнал автопилоту
    
    try:
        # Увеличиваем timeout до 120 секунд, так как генерация статьи — процесс долгий
        response = requests.post(API_URL, json=payload, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ УСПЕХ! Статья создана: {result.get('title')}")
        else:
            print(f"❌ ОШИБКА СЕРВЕРА: {response.status_code}")
            print(f"Детали: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ ОШИБКА: Сервер слишком долго думал (Таймаут).")
    except Exception as e:
        print(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {e}")

if __name__ == "__main__":
    run_autopilot()
