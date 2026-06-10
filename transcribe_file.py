import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

url = "https://api.deepgram.com/v1/listen?model=nova-2&language=zh&smart_format=true"
headers = {
    "Authorization": f"Token {DEEPGRAM_API_KEY}",
    "Content-Type": "audio/m4a"
}

print("Uploading to Deepgram...")
with open("audio.m4a", "rb") as audio:
    response = requests.post(url, headers=headers, data=audio)

if response.status_code == 200:
    result = response.json()
    transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)
    print("Transcript saved to transcript.txt")
else:
    print(f"Error: {response.status_code} - {response.text}")
