import os, json, requests
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=GEMINI_API_KEY)
print("Uploading chunk 0...")
f = client.files.upload(file="chunk_88bN51bbMZM_0.mp3")
import time
while f.state.name == "PROCESSING":
    time.sleep(2)
    f = client.files.get(name=f.name)

print("Generating content...")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[f, """
    You are an expert financial transcriber analyzing a Cantonese financial broadcast.
    Listen to the provided 3-minute audio chunk carefully.
    
    Your task is to summarize the discussion into a detailed Dialogue/Q&A style format (對答 style). 
    - Identify the speakers (e.g., 主持人, 嘉賓, or use their names/nicknames).
    - Summarize their conversation back and forth. You do NOT need to transcribe every single word verbatim, as that will be too long, but you MUST capture ALL the key points.
    - Make sure to capture every specific stock name, ticker, target price, and their exact reasoning and opinions within the dialogue format.
    - Keep it concise enough to fit in a standard message, but detailed enough so no financial advice is lost.
    
    1. Output your response entirely as a Dialogue script (e.g. 主持人: ... 嘉賓: ...).
    2. ALWAYS return status "FOUND_TOPIC" (unless the show is ending). 
    3. The dialogue MUST be written in fluent Traditional Chinese (繁體中文).
    4. If the host is clearly saying goodbye, wrapping up the show, or ending the broadcast, return "END_OF_SHOW".
    """],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "status": {"type": "STRING"},
                "summary": {"type": "STRING"}
            },
            "required": ["status", "summary"]
        }
    )
)
result = json.loads(response.text)
summary = result.get("summary")
print("Summary length:", len(summary))

msg = f"📝 *Secretary Mode (Min 0-3)*\n\n{summary}"
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
res = requests.post(url, json=payload)
print("Telegram API Status:", res.status_code)
print("Telegram API Response:", res.text)
client.files.delete(name=f.name)
