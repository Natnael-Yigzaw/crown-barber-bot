"""
Run bot in development mode with test .env
Usage: python run_dev.py
"""
import os
import sys

# Override .env file before importing bot
os.environ["DOTENV_FILE"] = ".env.dev"

# Patch dotenv to load .env.dev instead of .env
from dotenv import load_dotenv
load_dotenv(".env.dev")

# Now import and run bot
if __name__ == "__main__":
    from bot.main import main
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Dev bot stopped")