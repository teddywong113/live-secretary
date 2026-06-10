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

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
YOUTUBE_URL = os.getenv("YOUTUBE_URL")

start_time = time.time()
MAX_RUNTIME_SECONDS = 60 * 60  # 60 minutes maximum run time



def send_telegram_message(message):
    """Send a push notification via Telegram Bot."""
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
    """Use yt-dlp to extract the raw audio stream URL from a YouTube live stream."""
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

def record_audio_chunk(stream_url, duration=180, output_file="chunk.mp3"):
    """Record a chunk of audio from the stream using ffmpeg."""
    print(f"Recording {duration} seconds of audio...")
    command = [
        "./ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y", # Overwrite output file
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", stream_url,
        "-t", str(duration),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        output_file
    ]
    process = subprocess.Popen(command, stderr=sys.stderr)
    process.wait()
    if process.returncode != 0 and not os.path.exists(output_file):
         raise RuntimeError("ffmpeg failed to record audio chunk.")

def analyze_audio_chunk(client, audio_file):
    """Uploads the audio chunk to Gemini and analyzes it."""
    print(f"Uploading {audio_file} to Gemini...")
    uploaded_file = client.files.upload(file=audio_file)
    
    # Wait for the file to be active (though audio is usually fast)
    while uploaded_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(2)
        uploaded_file = client.files.get(name=uploaded_file.name)
        
    if uploaded_file.state.name == "FAILED":
        print(f"File processing failed: {uploaded_file.name}")
        client.files.delete(name=uploaded_file.name)
        return
        
    print("Analyzing audio with Gemini 2.5 Flash...")
    prompt = """
    You are an expert financial transcriber analyzing a Cantonese financial broadcast.
    Listen to the provided 3-minute audio chunk carefully.
    
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
            "status": {
                "type": "STRING",
                "description": "Must be one of: 'FOUND_TOPIC', 'END_OF_SHOW', or 'CONTINUE'."
            },
            "summary": {
                "type": "STRING",
                "description": "If status is FOUND_TOPIC, provide a detailed markdown-formatted summary of what was discussed, including specific numbers, targets, and bias. Otherwise, leave empty."
            }
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
                break # Success, exit retry loop
            except Exception as api_err:
                print(f"Gemini API error (Attempt {attempt+1}/3): {api_err}")
                time.sleep(5)
                
        if not status:
            print("Failed to get a valid response from Gemini after 3 attempts.")
            return

        if status == "END_OF_SHOW":
            print("End of show detected!")
            send_telegram_message("👋 *Show Ended*: The host is wrapping up. Shutting down the script.")
            os._exit(0)
            
        elif status == "FOUND_TOPIC":
            summary = result.get("summary")
            if summary:
                print(f"\n🎉 Topic Found!")
                msg = f"📊 *Live Summary Update*\n\n{summary}"
                send_telegram_message(msg)
    except Exception as e:
        print(f"Error during LLM analysis: {e}")
    finally:
        # Clean up the file from Google's servers
        try:
            client.files.delete(name=uploaded_file.name)
            print(f"Cleaned up file {uploaded_file.name} from Gemini API.")
        except:
            pass


def main():
    if len(sys.argv) > 1:
        youtube_url = sys.argv[1]
    else:
        youtube_url = YOUTUBE_URL

    if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, youtube_url]):
        print("Error: Missing required environment variables. Please check your .env file.")
        sys.exit(1)

    # Initialize Gemini client
    client = genai.Client(api_key=GEMINI_API_KEY)

    send_telegram_message(f"🟢 *Bot Started*: Recording and analyzing live stream using Native Audio... ({youtube_url})")

    stream_url = get_live_stream_url(youtube_url)
    if not stream_url:
        print("Could not retrieve stream URL. Exiting.")
        sys.exit(1)

    while True:
        # Check hard timeout
        if time.time() - start_time > MAX_RUNTIME_SECONDS:
            print("Maximum runtime of 60 minutes reached. Shutting down.")
            send_telegram_message("🛑 *Script Shutdown*: Reached 60 minute maximum runtime.")
            break



        chunk_filename = "chunk.mp3"
        try:
            # 1. Record 3 minutes of audio
            record_audio_chunk(stream_url, duration=180, output_file=chunk_filename)
            
            # 2. Analyze audio with Gemini
            if os.path.exists(chunk_filename):
                analyze_audio_chunk(client, chunk_filename)
                # Clean up local file
                os.remove(chunk_filename)
            
        except KeyboardInterrupt:
            print("Interrupted by user.")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(10) # Wait a bit before retrying if there's an error

    print("Finished.")

if __name__ == "__main__":
    main()
