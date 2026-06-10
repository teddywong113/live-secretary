import os
import sys
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import time
import subprocess
import json
import requests
import yt_dlp
import math
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
VOD_URL = "https://www.youtube.com/watch?v=Kgni_54_c5I"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram max message length is 4096
    max_length = 4000
    for i in range(0, len(text), max_length):
        chunk = text[i:i+max_length]
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": chunk}
        res = requests.post(url, json=payload)
        try:
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Telegram API Error: {res.text}")

def get_video_duration(filename):
    result = subprocess.run(["./ffmpeg", "-i", filename], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = result.stdout.decode()
    for line in out.split('\n'):
        if "Duration" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = time_str.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0

def download_full_vod():
    print("Downloading full VOD audio...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': False,
        'outtmpl': 'full_vod.%(ext)s',
        'ffmpeg_location': './ffmpeg'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([VOD_URL])

def analyze_chunk(filename, start_time):
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"Uploading {filename} to Gemini...")
    uploaded_file = client.files.upload(file=filename)
    
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    prompt = """
    You are an expert financial transcriber analyzing a Cantonese financial broadcast.
    Listen to the provided 15-minute audio chunk carefully.
    
    Your task is to summarize the discussion into a detailed Dialogue/Q&A style format (對答 style). 
    - Identify the speakers (e.g., 主持人, 嘉賓, or use their names/nicknames).
    - Summarize their conversation back and forth. You do NOT need to transcribe every single word verbatim, as that will be too long, but you MUST capture ALL the key points.
    - Make sure to capture every specific stock name, ticker, target price, and their exact reasoning and opinions within the dialogue format.
    - Keep it concise enough to fit in a standard message, but detailed enough so no financial advice is lost.
    
    1. Output your response entirely as a Dialogue script (e.g. 主持人: ... 嘉賓: ...).
    2. ALWAYS return status 'FOUND_TOPIC' (unless the show is ending). 
    3. The dialogue MUST be written in fluent Traditional Chinese (繁體中文).
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
            print("API RESULT:", result)
            import sys; sys.stdout.flush()
            summary = result.get("summary")
            break
        except Exception as e:
            print(f"API error on attempt {attempt+1}: {e}")
            time.sleep(5)
    
    if summary:
        start_min = int(start_time // 60)
        end_min = int((start_time + 900) // 60)
        print("Sending to Telegram...")
        msg = f"📝 *Secretary Mode (Min {start_min}-{end_min})*\n\n{summary}"
        send_telegram_message(msg)
    
    client.files.delete(name=uploaded_file.name)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        VOD_URL = sys.argv[1]
    start_point = 0
    video_id = VOD_URL.split("v=")[-1]
    
    def download_full_vod_unique():
        print(f"Downloading full VOD audio for {video_id}...")
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': False,
            'outtmpl': f'full_vod_{video_id}.%(ext)s',
            'ffmpeg_location': './ffmpeg'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([VOD_URL])
            
    download_full_vod_unique()
    # Find the downloaded file (could be webm or m4a)
    video_file = None
    for f in os.listdir('.'):
        if f.startswith(f'full_vod_{video_id}.'):
            video_file = f
            break
            
    if not video_file:
        print("Failed to download VOD!")
        sys.exit(1)
        
    duration = get_video_duration(video_file)
    print(f"Total duration: {duration} seconds")
    
    while start_point < duration:
        print(f"--- Processing chunk from {start_point}s ---")
        chunk_file = f"chunk_{video_id}_{start_point}.mp3"
        command = [
            "./ffmpeg",
            "-hide_banner", "-loglevel", "error", "-y",
            "-i", video_file,
            "-ss", str(start_point),
            "-t", "900",
            "-vn", "-ac", "1", "-ar", "16000",
            chunk_file
        ]
        subprocess.run(command, check=True)
        
        analyze_chunk(chunk_file, start_point)
        start_point += 900
        time.sleep(3) # Small delay to be safe
        
    print("Finished processing the entire VOD!")
    os.remove(video_file) # Clean up the giant file
