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
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "https://www.youtube.com/@RagaFinance/live")

start_time = time.time()
MAX_RUNTIME_SECONDS = 60 * 120  # Run for up to 2 hours (covers the segment)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    max_length = 4000
    for i in range(0, len(message), max_length):
        chunk = message[i:i+max_length]
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": chunk}
        res = requests.post(url, json=payload)
        try:
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"Telegram API Error: {res.text}")

def get_live_stream_url(youtube_url):
    print(f"Extracting live stream URL from {youtube_url}...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extractor_args': {'youtube': ['player_client=android']}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_url, download=False)
            return info['url']
        except Exception as e:
            print(f"Error fetching YouTube stream: {e}")
            return None

def record_audio_chunk(stream_url, duration=900, output_file="live_chunk.mp3"):
    print(f"Recording {duration} seconds (15 mins) of audio...")
    command = [
        "./ffmpeg",
        "-hide_banner", "-loglevel", "error", "-y",
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", stream_url,
        "-t", str(duration),
        "-vn", "-ac", "1", "-ar", "16000",
        output_file
    ]
    process = subprocess.Popen(command, stderr=sys.stderr)
    try:
        process.wait(timeout=duration + 30)
    except subprocess.TimeoutExpired:
        print("ffmpeg hung! Killing process.", flush=True)
        process.kill()
        process.wait()
        
    if process.returncode != 0 and not os.path.exists(output_file):
         raise RuntimeError("ffmpeg failed to record audio chunk.")

def analyze_audio_chunk(client, audio_file):
    print(f"Uploading {audio_file} to Gemini...")
    uploaded_file = client.files.upload(file=audio_file)
    
    while uploaded_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    if uploaded_file.state.name == "FAILED":
        print(f"File processing failed.")
        client.files.delete(name=uploaded_file.name)
        return
        
    print("Analyzing audio (Secretary Mode)...")
    prompt = """
    You are a highly professional financial secretary taking exhaustive, accurate meeting minutes for a live trading broadcast.
    Listen to the provided 15-minute audio chunk carefully. The broadcast is in Cantonese/Chinese.
    Pay special attention to the segment "文錦期權譜" (Man Kam Options Strategy).
    
    Your task is to report EVERYTHING discussed in this 15-minute window in chronological order. Do NOT compress, filter, or omit information. 
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

    try:
        result = None
        status = None
        for attempt in range(5):
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
                status = result.get("status")
                break
            except Exception as api_err:
                print(f"Gemini API error (Attempt {attempt+1}/5): {api_err}")
                time.sleep(5)
                
        if not status:
            print("Failed to get response.")
            return

        if status == "END_OF_SHOW":
            send_telegram_message("👋 *Show Ended*: The host is wrapping up. Shutting down the script.")
            os._exit(0)
            
        elif status == "FOUND_TOPIC":
            summary = result.get("summary")
            if summary:
                minutes_elapsed = int((time.time() - start_time) / 60)
                msg = f"📝 *Secretary Mode (Min {minutes_elapsed-15} to {minutes_elapsed})*\n\n{summary}"
                send_telegram_message(msg)
    except Exception as e:
        print(f"Error during LLM analysis: {e}")
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass

def detect_show_start(client, audio_file):
    print(f"Uploading {audio_file} for start detection...")
    uploaded_file = client.files.upload(file=audio_file)
    
    while uploaded_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    if uploaded_file.state.name == "FAILED":
        print(f"File processing failed.")
        client.files.delete(name=uploaded_file.name)
        return False
        
    print("Checking if show has started...")
    prompt = """
    Listen to this short audio chunk from a live broadcast. 
    Does it contain the start of the show? The show always starts with the hosts saying "早晨早晨", and then "早晨文錦sir" or "早晨各位網友".
    If you hear these greetings, or if the main financial discussion has clearly started, return 'STARTED'.
    If it is just pre-show holding music, silence, ads, or waiting, return 'WAITING'.
    """
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "status": {"type": "STRING"}
        },
        "required": ["status"]
    }

    started = False
    try:
        for attempt in range(5):
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
                if result.get("status") == "STARTED":
                    started = True
                break
            except Exception as api_err:
                print(f"Gemini API error (Detection Attempt {attempt+1}/5): {api_err}")
                time.sleep(5)
    except Exception as e:
        print(f"Error during LLM detection: {e}")
    finally:
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass
            
    return started

def main():
    if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, YOUTUBE_URL]):
        print("Error: Missing required environment variables.")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    send_telegram_message(f"🟢 *Bot Started*: Listening for show start (早晨早晨) on {YOUTUBE_URL}...")

    has_started = False

    while True:
        if time.time() - start_time > MAX_RUNTIME_SECONDS:
            send_telegram_message("🛑 *Script Shutdown*: Reached maximum runtime of 2 hours.")
            break
            
        stream_url = get_live_stream_url(YOUTUBE_URL)
        if not stream_url:
            print("Could not retrieve stream URL. Channel might not be live yet. Retrying in 60s...")
            time.sleep(60)
            continue

        # Use 2-minute chunks when listening for the start, 15-minute chunks once started
        chunk_duration = 900 if has_started else 120
        chunk_filename = "live_chunk.mp3"
        try:
            record_audio_chunk(stream_url, duration=chunk_duration, output_file=chunk_filename)
            if os.path.exists(chunk_filename):
                if not has_started:
                    if detect_show_start(client, chunk_filename):
                        has_started = True
                        send_telegram_message("📢 *Show Started*: Detected the starting greetings. Beginning full 15-minute coverage.")
                        # Sleep to avoid hitting Gemini Free Tier 5 RPM quota after the detection call
                        time.sleep(30)
                        # Analyze the chunk where the show started so we don't miss the first 2 minutes
                        analyze_audio_chunk(client, chunk_filename)
                    else:
                        print("Show hasn't started yet. Listening again...")
                else:
                    analyze_audio_chunk(client, chunk_filename)
                os.remove(chunk_filename)
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
