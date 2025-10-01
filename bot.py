import os
import sys
import asyncio

# Ensure src/ is on sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from bot.main import main as bot_main  # noqa: E402


if __name__ == "__main__":
    asyncio.run(bot_main())
