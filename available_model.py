import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    print("Error: GOOGLE_API_KEY nahi mili. Kripya apni .env file check karein.")
else:
    print("Checking available Gemini models...\n")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        models = response.json().get("models", [])
        print("✅ Models available for text generation (generateContent):\n")
        
        for m in models:
            name = m.get("name")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                print(f"- {name}")
    else:
        print(f"❌ Error API fetch failed: {response.status_code}")
        print(response.text)

# ✅ Models available for text generation (generateContent):

# - models/gemini-2.5-flash
# - models/gemini-2.5-pro
# - models/gemini-2.5-flash-preview-tts
# - models/gemini-2.5-pro-preview-tts
# - models/gemma-4-26b-a4b-it
# - models/gemma-4-31b-it
# - models/gemini-flash-latest
# - models/gemini-flash-lite-latest
# - models/gemini-pro-latest
# - models/gemini-2.5-flash-lite
# - models/gemini-2.5-flash-image
# - models/gemini-3-flash-preview
# - models/gemini-3.1-pro-preview
# - models/gemini-3.1-pro-preview-customtools
# - models/gemini-3.1-flash-lite-preview
# - models/gemini-3.1-flash-lite
# - models/gemini-3-pro-image-preview
# - models/gemini-3-pro-image
# - models/nano-banana-pro-preview
# - models/gemini-3.1-flash-image-preview
# - models/gemini-3.1-flash-image
# - models/gemini-3.1-flash-lite-image
# - models/gemini-3.5-flash
# - models/gemini-3.5-flash-lite
# - models/gemini-omni-flash-preview
# - models/gemini-omni-1.1-flash
# - models/gemini-3.5-transcribe
# - models/gemini-3.6-flash
# - models/gemini-3.7-flash
# - models/gemini-3.8-flash
# - models/lyria-3-clip-preview
# - models/lyria-3-pro-preview
# - models/lyria-3.5
# - models/gemini-3.1-flash-tts-preview
# - models/gemini-3.8-flash-tts
# - models/gemini-3.8-flash-lite-tts
# - models/gemini-robotics-er-2-preview
# - models/gemini-2.5-computer-use-preview-10-2025
# - models/antigravity-preview-05-2026
# - models/antigravity-preview-09-2026
# - models/antigravity-preview-latest
# - models/deep-research-max-preview-04-2026
# - models/deep-research-preview-04-2026
# - models/deep-research-pro-preview-12-2025