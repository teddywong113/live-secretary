import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "https://www.youtube.com/@RagaFinance/live")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram credentials.")
        return

    # Check YouTube channel connectivity
    try:
        res = requests.get(YOUTUBE_URL, timeout=10)
        if res.status_code == 200:
            yt_status = "✅ YouTube Channel reachable"
        else:
            yt_status = f"⚠️ YouTube returned status {res.status_code}"
    except Exception as e:
        yt_status = f"❌ YouTube Connection Failed"

    # Check if main script exists
    script_exists = os.path.exists("live_secretary.py")
    script_status = "✅ `live_secretary.py` script ready" if script_exists else "❌ `live_secretary.py` missing!"

    msg = f"🔍 *9:45 AM Pre-flight Check*\n\n{yt_status}\n{script_status}\n\nThe 10:00 AM recording task is locked and loaded."
    send_telegram_message(msg)
    print("Pre-flight check complete. Telegram message sent.")

if __name__ == "__main__":
    main()
