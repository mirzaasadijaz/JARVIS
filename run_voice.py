"""ENTRY POINT — starts the mic-listening loop, with a system tray status
indicator (listening/thinking/speaking).

Run from the project root:
    python run_voice.py

Runs natively on your machine, NOT in Docker — see the note in
docker-compose.yml about why desktop automation and mic/speaker access
don't containerize cleanly.
"""

from dotenv import load_dotenv
load_dotenv()  

from core.status import run_with_status
from voice.loop import run

if __name__ == "__main__":
    run_with_status(run)