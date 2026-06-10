import os
import sys
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import time
import subprocess
import json
import requests
import yt_dlp
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
VOD_URL = "https://www.youtube.com/watch?v=eI-wANGO5E4"
START_TIME_SEC = 2430  # 40:30
END_TIME_SEC = 4854    # 1:20:54

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_length = 4000
    for i in range(0, len(text), max_length):
        chunk = text[i:i+max_length]
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": chunk}
        res = requests.post(url, json=payload)
        try:
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Telegram API Error: {res.text}")

def download_full_vod_unique(video_id):
    print(f"Downloading full VOD audio for {video_id}...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'outtmpl': f'full_vod_{video_id}.%(ext)s',
        'ffmpeg_location': './ffmpeg'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([VOD_URL])

def analyze_chunk(filename, start_time, duration):
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"Uploading {filename} to Gemini...")
    uploaded_file = client.files.upload(file=filename)
    
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    prompt = """
    You are an expert financial transcriber analyzing a Cantonese financial broadcast.
    Listen to the provided audio chunk carefully.
    
    Your task is to summarize the discussion into a detailed Dialogue/Q&A style format (對答 style). 
    - Identify the speakers.
    - Summarize their conversation back and forth. You do NOT need to transcribe every single word verbatim, but MUST capture ALL the key points.
    - Make sure to capture every specific stock name, ticker, target price, and their exact reasoning and opinions within the dialogue format.
    - Keep it concise enough to fit in a standard message, but detailed enough so no financial advice is lost.
    
    1. Output your response entirely as a Dialogue script.
    2. ALWAYS return status 'FOUND_TOPIC'. 
    3. The dialogue MUST be written in fluent Traditional Chinese (繁體中文).
    """
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "status": {"type": "STRING"},
            "summary": {"type": "STRING"}
        },
        "required": ["status"]
    }
    
    summary = None
    for attempt in range(10):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
            result = json.loads(response.text)
            summary = result.get("summary")
            break
        except Exception as e:
            print(f"API error: {e}")
            time.sleep(5)
            
    if summary:
        start_min = int(start_time // 60)
        start_sec = int(start_time % 60)
        end_time = start_time + duration
        end_min = int(end_time // 60)
        end_sec = int(end_time % 60)
        
        print("Sending to Telegram...")
        msg = f"📝 *Custom VOD Section ({start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d})*\n\n{summary}"
        send_telegram_message(msg)
    
    client.files.delete(name=uploaded_file.name)
    print(f"Deleted {uploaded_file.name} from Gemini API.")

if __name__ == "__main__":
    send_telegram_message(f"⚙️ *Starting custom transcript processing for section 40:30 to 01:20:54...*")
    video_id = VOD_URL.split("v=")[-1]
    # download_full_vod_unique(video_id)
    
    video_file = None
    for f in os.listdir('.'):
        if f.startswith(f'full_vod_{video_id}.'):
            video_file = f
            break
            
    if not video_file:
        print("Failed to download VOD!")
        sys.exit(1)
        
    start_point = START_TIME_SEC
    while start_point < END_TIME_SEC:
        print(f"--- Processing chunk from {start_point}s ---")
        chunk_file = f"chunk_{video_id}_{start_point}.mp3"
        duration = min(900, END_TIME_SEC - start_point)
        command = [
            "./ffmpeg",
            "-hide_banner", "-loglevel", "error", "-y",
            "-i", video_file,
            "-ss", str(start_point),
            "-t", str(duration),
            "-vn", "-ac", "1", "-ar", "16000",
            chunk_file
        ]
        subprocess.run(command, check=True)
        
        analyze_chunk(chunk_file, start_point, duration)
        start_point += 900
        time.sleep(3)
        
    print("Finished processing the custom section!")
    os.remove(video_file)
