"""ENTRY POINT — starts the FastAPI WhatsApp webhook server.

Run from the project root:
    python run_server.py
Or in production, via uvicorn directly (see Dockerfile):
    uvicorn whatsapp_server.webhook:app --host 0.0.0.0 --port 8000
"""

import uvicorn
from dotenv import load_dotenv
load_dotenv()  

if __name__ == "__main__":
    uvicorn.run("whatsapp_server.webhook:app", host="0.0.0.0", port=8000, reload=False)