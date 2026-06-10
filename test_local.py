import os
import sys
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import time
import json
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    requests.post(url, json=payload)

def analyze_chunk():
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("Uploading test_clip.mp3 to Gemini...")
    uploaded_file = client.files.upload(file="test_clip.mp3")
    
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    prompt = """
    You are a highly professional financial secretary taking exhaustive, accurate meeting minutes for a live trading broadcast.
    Listen to the provided 3-minute audio chunk carefully. The broadcast is in Cantonese/Chinese.
    
    Your task is to report EVERYTHING discussed in this 3-minute window in chronological order. Do NOT compress, filter, or omit information. 
    - For financial topics: record every single stock name, ticker, target price, entry/exit point, market bias, and the exact reasoning of the host.
    - For off-topic or casual conversations: record exactly what they are chatting about in detail.
    
    1. Output your response as a highly detailed, chronological bulleted list (meeting minutes format).
    2. ALWAYS return status 'FOUND_TOPIC' (unless the show is ending). 
    3. The meeting minutes MUST be written in fluent Traditional Chinese (繁體中文).
    4. If the host is clearly saying goodbye, wrapping up the show, or ending the broadcast, return 'END_OF_SHOW'.
    """
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "status": {"type": "STRING"},
            "summary": {"type": "STRING"}
        },
        "required": ["status"]
    }
    
    print("Generating meeting minutes...")
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            break
        except Exception as e:
            print(f"API error on attempt {attempt+1}: {e}")
            time.sleep(5)
    
    result = json.loads(response.text)
    summary = result.get("summary")
    
    print("Sending to Telegram...")
    msg = f"📝 *Secretary Mode Test (First 3 Mins)*\n\n{summary}"
    send_telegram_message(msg)
    
    client.files.delete(name=uploaded_file.name)

if __name__ == "__main__":
    analyze_chunk()
    print("Done!")
