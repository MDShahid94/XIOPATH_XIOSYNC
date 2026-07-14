import asyncio
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from core.agent_loop import AgentLoop
from core.gemini_engine import GeminiEngine
from core.api_manager import ApiManager

console = Console()
_api_manager = ApiManager()

class InteractiveRouter:
    def __init__(self, session_id: str = "default_client", headless_mode: str = "auto",
                 profile: str = None, proxy_server: str = None,
                 proxy_username: str = None, proxy_password: str = None):
        self.session_id = session_id
        self.llm = GeminiEngine()
        
        # Build proxy config if provided
        proxy_config = None
        if proxy_server:
            proxy_config = {"server": proxy_server}
            if proxy_username:
                proxy_config["username"] = proxy_username
            if proxy_password:
                proxy_config["password"] = proxy_password
        
        self.agent = AgentLoop(
            session_id=session_id,
            llm=self.llm,
            headless_mode=headless_mode,
            profile=profile,
            proxy_config=proxy_config,
        )

    async def chat_loop(self):
        console.print(Panel.fit("[bold green]🤖 V2 RAE Agent Initialized[/bold green]\n"
                                "Tiered Memory System active. Type your intents below.\n"
                                "Type 'exit' to quit.\n"
                                "Type '/api' to check API Key statuses.", 
                                border_style="green"))

        # Start the persistent browser session
        await self.agent.start()

        try:
            while True:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
                
                if user_input.lower() in ['exit', 'quit']:
                    console.print("[yellow]Shutting down...[/yellow]")
                    break
                    
                if user_input.startswith("/api"):
                    parts = user_input.split()
                    if len(parts) > 1 and parts[1] == "add" and len(parts) > 2:
                        _api_manager.add_key(parts[2])
                        console.print(f"[green]Added new API key ending in {parts[2][-4:]}[/green]")
                    else:
                        status = _api_manager.get_status_report()
                        console.print(Panel(status, title="API Key Status", border_style="cyan"))
                    continue

                # Normal task execution on the persistent browser
                await self.agent.chat_step(user_input)

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted! Shutting down...[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Critical Router Error:[/bold red] {e}")
        finally:
            await self.agent.stop()

if __name__ == "__main__":
    router = InteractiveRouter(headless_mode="false")
    asyncio.run(router.chat_loop())
