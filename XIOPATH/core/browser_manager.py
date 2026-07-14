import os
import sys
from pathlib import Path
from browser_use import Browser
from browser_use.browser.profile import ProxySettings

def is_headless_environment() -> bool:
    """Dynamically determine if the system should run headless."""
    # Virtual/Cloud CI environments
    if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
        return True
    
    # Linux without a display usually means a server
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
        return True
    
    # Default to headed for residential/local machines (Mac, Windows, Linux with GUI)
    return False

def get_browser(
    profile_name: str = None, 
    record_video: bool = True, 
    headless_mode: str = 'auto',
    proxy_server: str = None,
    proxy_username: str = None,
    proxy_password: str = None
) -> Browser:
    """
    Get a dynamically configured browser instance.
    """
    if headless_mode.lower() == 'true':
        headless = True
    elif headless_mode.lower() == 'false':
        headless = False
    else:
        headless = is_headless_environment()
    
    extra_args = []
    
    # Configure Profile Persistence
    user_data_dir = None
    if profile_name:
        profile_path = Path("data/profiles") / profile_name
        profile_path.mkdir(parents=True, exist_ok=True)
        user_data_dir = str(profile_path.absolute())

    # Configure Proxy
    proxy = None
    if proxy_server:
        proxy = ProxySettings(
            server=proxy_server,
            username=proxy_username,
            password=proxy_password
        )

    return Browser(
        headless=headless,
        user_data_dir=user_data_dir,
        proxy=proxy
    )
