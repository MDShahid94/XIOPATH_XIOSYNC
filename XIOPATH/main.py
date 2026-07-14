import asyncio
import os
import argparse
from dotenv import load_dotenv
from rich.console import Console

from core.chat_loop import InteractiveRouter

load_dotenv()
console = Console()

async def main():
    parser = argparse.ArgumentParser(description="Run the V2 Scalable AI Browser Agent")
    parser.add_argument("--profile", type=str, default="default", help="The browser profile to use for persistence")
    parser.add_argument("--session", type=str, default="session_1", help="The memory session ID")
    parser.add_argument("--headless", type=str, choices=['auto', 'true', 'false'], default='auto', help="Force headless mode ('true', 'false', or 'auto')")
    parser.add_argument("--proxy-server", type=str, default=None, help="Proxy server URL (e.g. http://proxy:8080)")
    parser.add_argument("--proxy-username", type=str, default=None, help="Proxy username")
    parser.add_argument("--proxy-password", type=str, default=None, help="Proxy password")
    args = parser.parse_args()

    router = InteractiveRouter(
        session_id=args.session,
        headless_mode=args.headless,
        profile=args.profile,
        proxy_server=args.proxy_server,
        proxy_username=args.proxy_username,
        proxy_password=args.proxy_password,
    )
    await router.chat_loop()

if __name__ == "__main__":
    asyncio.run(main())

