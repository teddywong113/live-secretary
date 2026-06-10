import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

try:
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents='Hello, does this model have quota?'
    )
    print("gemini-1.5-flash is working! Response:", response.text)
except Exception as e:
    print("gemini-1.5-flash error:", e)

try:
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Hello, does this model have quota?'
    )
    print("gemini-2.0-flash is working! Response:", response.text)
except Exception as e:
    print("gemini-2.0-flash error:", e)
