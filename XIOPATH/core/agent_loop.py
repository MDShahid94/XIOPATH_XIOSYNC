import asyncio
import shlex
import subprocess
import os
import logging
from typing import Dict, Any, List, Optional
from rich.console import Console
import json
from urllib.parse import urlparse as url_parse

logger = logging.getLogger(__name__)

from core.browser_controller import PlaywrightController
from core.dom_inspector import DOMInspector
from core.gemini_engine import GeminiEngine
from core.memory_manager import MemoryManager  # Legacy fallback
from core.llm_preprocessor import PreFlightValidator
from core.plugin_registry import PluginRegistry

console = Console()

class ActorLoop:
    """
    Retrieval-Augmented Execution (RAE) Actor Loop.
    Supports Continuous Chat, Tiered Long-Term Action Memory, and Semantic Workflow Graphs.
    """
    def __init__(self, session_id: str, llm: GeminiEngine, enable_screenshots: bool = False, record_video: bool = True,
                 headless_mode: str = "auto", profile: str = None, proxy_config: dict = None):
        self.session_id = session_id
        
        # Configure browser options — forwarded from CLI (Phase 24: E-01/E-02)
        self.browser = PlaywrightController(
            headless=headless_mode, proxy_config=proxy_config, profile_name=profile
        )
        self.enable_screenshots = enable_screenshots
        self.record_video = record_video
        self.llm = llm
        # v5.0: Use KnowledgeManager via MemoryBridge, fall back to legacy MemoryManager
        try:
            from pathlib import Path
            from core.database import DatabaseManager
            from core.type_registry import TypeRegistry
            from core.knowledge_manager import KnowledgeManager
            from core.memory_bridge import MemoryBridge
            _db = DatabaseManager(Path('data/xiopath.db'))
            _tr = TypeRegistry(_db)
            _km = KnowledgeManager(_db, type_registry=_tr)
            self.memory = MemoryBridge(session_id=session_id, knowledge_manager=_km, db=_db)
            logger.info('v5.0 KnowledgeManager wired via MemoryBridge')
        except Exception as e:
            logger.warning(f'v5.0 bridge unavailable ({e}), falling back to legacy MemoryManager')
            self.memory = MemoryManager(session_id=session_id)
        self.preflight_validator = PreFlightValidator(llm)
        
        self.current_footprint = []
        self.last_failure_context = None
        self.previous_intent = None # Track the last intent for graph linking
        self.context_dict = None # Will be generated dynamically in start()
        self.max_fallback_tier = 2 # Configurable fallback depth
        
        # Phase 2: Pre-flight state management
        self.pending_workflow_graph = None
        self.execution_context = {}
        self.workflow_vars = {} # Phase 5: Global variables for data extraction and input
        self.required_params = []
        self.active_graph_parent_intent = None # Phase 6: Tracks the last successful graph node for self-healing stitching
        
        from core.secret_manager import SecretManager
        self.secret_manager = SecretManager()
        # Phase 7 → Enterprise Circuit Breaker (3-state: CLOSED/OPEN/HALF_OPEN)
        from core.resilience import registry as _resilience_registry
        self._breaker = _resilience_registry.get("browser_default")
        
        self.plugin_manager = PluginRegistry() # Phase 11 → E.1: Full Plugin Registry with lifecycle
        self.plugin_manager.load_all()         # Discover, load, and enable all plugins
        self._parallel_semaphore = asyncio.Semaphore(4)  # W.5: Max 4 concurrent parallel branches
        
        self.system_instruction = """
        You are a highly advanced AI browser agent.
        Your goal is to accomplish user intents on the web.
        
        Respond ONLY with a strictly formatted JSON object matching this schema:
        {
            "thought": "Your internal reasoning for this step",
            "action": "click|type|navigate|scroll_down|extract_data|done",
            "action_params": {
                "node_id": 12, // Required for click, type, or extract_data. Must be an integer corresponding to an interactive element.
                "text": "string", // Required for type or navigate.
            }
        }
        CRITICAL: If you are typing or clicking, you MUST provide a valid integer `node_id` from the Interactive Elements Map.
        CRITICAL: If the user's goal has been fully accomplished based on the current DOM, you MUST output the action 'done'.
        """
        
        self.validation_instruction = """
        You are a validation agent. The user wants to execute a cached action from Secondary Memory.
        Evaluate if the cached action is STILL VALID on the current DOM.
        
        Respond ONLY with a JSON object:
        {
            "is_valid": true/false,
            "reason": "Why it is or isn't valid",
            "updated_node_id": 12 // If the node_id changed but you found the same element, provide the new node_id. Or null if invalid.
        }
        """

    async def start(self):
        await self.browser.start(enable_traces=True, enable_video=self.record_video, video_mode='action')
        
        # Phase 3: Dynamic Fingerprinting
        self.context_dict = await self.browser.get_fingerprint()
        console.print(f"[bold cyan]🔍 Browser Fingerprint:[/bold cyan] {self.context_dict}")
        
    async def stop(self):
        await self.browser.stop(save_trace=True)

    async def _execute_playwright_action(self, action: str, params: Dict, node_map: Dict, place_value: Dict = None, face_value: Dict = None) -> bool:
        """Executes the action on the browser using the Grounding Matrix. Returns True if successful."""
        if self.enable_screenshots:
            import os, time
            timestamp = int(time.time() * 1000)
            os.makedirs("data/screenshots", exist_ok=True)
            await self.browser.page.screenshot(path=f"data/screenshots/before_{timestamp}.png")
            
        try:
            success = False
            face_value = face_value or {}
            
            async def _interact(locators: List[str], action: str, text: str = None):
                """Try each locator in order. Returns (success: bool, winning_locator: str|None)."""
                for loc in locators:
                    if not loc: continue
                    try:
                        # Clean up test_id locator if it's just the value
                        if loc.startswith("data-test"):
                            loc = f"[{loc}]"
                            
                        if action == 'click':
                            await self.browser.page.locator(loc).first.click(timeout=2000)
                        elif action == 'type':
                            await self.browser.page.locator(loc).first.fill(text, timeout=2000)
                            await self.browser.page.locator(loc).first.press('Enter')
                        elif action == 'extract_data':
                            return await self.browser.page.locator(loc).first.text_content(timeout=2000), loc
                        await self.browser.page.wait_for_load_state('networkidle')
                        return True, loc
                    except Exception as e:
                        continue
                return False, None

            if action == 'run_script':
                # Execute external script — HARDENED (Phase 23: S-06)
                script_cmd = params.get('text', '')
                console.print(f"[bold yellow]⚙️ Running External Script:[/bold yellow] {script_cmd}")

                args = shlex.split(script_cmd)
                if not args:
                    console.print(f"[red]Script Rejected:[/red] Empty command")
                    return False

                from pathlib import Path as _Path
                # Load runtime-configurable settings
                try:
                    from api.routers.admin import SecurityConfig
                    allowed_exts = set(SecurityConfig.allowed_plugin_extensions)
                    script_timeout = SecurityConfig.plugin_timeout_seconds
                except ImportError:
                    allowed_exts = {'.py', '.sh'}
                    script_timeout = 30

                # Resolve with strict=True to block broken symlinks / traversals
                try:
                    plugins_dir = _Path('plugins').resolve(strict=True)
                except (OSError, FileNotFoundError):
                    console.print(f"[red]Script Rejected:[/red] plugins/ directory not found")
                    return False
                try:
                    script_path = _Path(args[0]).resolve(strict=True)
                except (OSError, FileNotFoundError):
                    console.print(f"[red]Script Rejected:[/red] Script file not found or unresolvable")
                    return False

                # Verify path is within plugins/ (blocks symlink escapes)
                if not str(script_path).startswith(str(plugins_dir)):
                    console.print(f"[red]Script Rejected:[/red] Only scripts in plugins/ directory are allowed")
                    return False

                # Verify file extension
                if script_path.suffix.lower() not in allowed_exts:
                    console.print(f"[red]Script Rejected:[/red] Only {allowed_exts} files are allowed")
                    return False

                # Verify it's a regular file (not a device, socket, etc.)
                if not script_path.is_file():
                    console.print(f"[red]Script Rejected:[/red] Target is not a regular file")
                    return False

                result = subprocess.run(args, capture_output=True, text=True, timeout=script_timeout)
                if result.returncode == 0:
                    console.print(f"[green]Script Output:[/green] {result.stdout.strip()}")
                    return result.stdout.strip()
                else:
                    console.print(f"[red]Script Failed:[/red] {result.stderr.strip()}")
                    return False
                    
            elif action == 'api_call':
                # External API call — HARDENED (Phase 23: S-07 SSRF Protection)
                import requests as _requests
                import ipaddress
                import socket
                from urllib.parse import urlparse

                url = params.get('url')
                method = params.get('method', 'GET')
                data = params.get('data', {})

                # Load runtime-configurable SSRF settings
                try:
                    from api.routers.admin import SecurityConfig
                    block_private = SecurityConfig.block_private_ips
                    blocked_hosts = SecurityConfig.blocked_hosts
                    allowed_domains = SecurityConfig.allowed_domains
                except ImportError:
                    block_private = True
                    blocked_hosts = ["169.254.169.254", "metadata.google.internal"]
                    allowed_domains = []

                # URL validation
                try:
                    parsed = urlparse(url)
                    hostname = parsed.hostname
                    if not hostname:
                        console.print(f"[red]API Rejected:[/red] Invalid URL — no hostname")
                        return False

                    # Check blocked hosts
                    if hostname in blocked_hosts:
                        console.print(f"[red]API Rejected:[/red] Blocked host: {hostname}")
                        return False

                    # Check domain allowlist (if configured)
                    if allowed_domains and hostname not in allowed_domains:
                        console.print(f"[red]API Rejected:[/red] Domain not in allowlist: {hostname}")
                        return False

                    # Resolve and check IP ranges
                    if block_private:
                        resolved_ip = socket.gethostbyname(hostname)
                        ip_obj = ipaddress.ip_address(resolved_ip)
                        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                            console.print(f"[red]API Rejected:[/red] Requests to private/internal IPs are blocked ({resolved_ip})")
                            return False
                except Exception as e:
                    console.print(f"[red]API Rejected:[/red] URL validation failed: {e}")
                    return False

                console.print(f"[bold yellow]🌐 Making API Call:[/bold yellow] {method} {url}")
                try:
                    if method == 'POST': res = _requests.post(url, json=data, timeout=15)
                    else: res = _requests.get(url, timeout=15)
                    res.raise_for_status()
                    console.print(f"[green]API Success:[/green] {res.status_code}")
                    return res.text
                except Exception as e:
                    console.print(f"[red]API Failed:[/red] {e}")
                    return False
            
            elif action == 'navigate':
                url = params.get('text')
                # C2 Fix: SSRF protection for navigate action
                if url:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    blocked_schemes = ('file', 'data', 'javascript', 'vbscript', 'blob')
                    if parsed.scheme.lower() in blocked_schemes:
                        console.print(f"[bold red]🛑 SSRF Protection: Blocked navigation to '{parsed.scheme}:' URL[/bold red]")
                        return False
                    # Block private/internal IPs
                    import ipaddress
                    try:
                        host = parsed.hostname or ''
                        ip = ipaddress.ip_address(host)
                        if ip.is_private or ip.is_loopback or ip.is_link_local:
                            console.print(f"[bold red]🛑 SSRF Protection: Blocked navigation to private IP {host}[/bold red]")
                            return False
                    except ValueError:
                        pass  # Not an IP — domain name is fine
                await self.browser.page.goto(url)
                await self.browser.page.wait_for_load_state('networkidle')
                success = True
                
            elif action in ['click', 'type', 'extract_data']:
                node_id = params.get('node_id')
                text = params.get('text')
                
                if place_value:
                    # 9-Tier Stability-Ordered Locator Cascade
                    locators = []
                    tier_labels = []  # Telemetry: track which locators belong to which tier
                    
                    # Tier 1: test-id (highest stability — explicit developer markers)
                    if place_value.get('test_id'):
                        tid = place_value['test_id']
                        for fmt in ['data-testid', 'data-test-id', 'data-test', 'data-cy', 'data-automation-id', 'data-qa']:
                            locators.append(f"[{fmt}='{tid}']")
                            tier_labels.append(f"T1:{fmt}")
                    # Tier 2: ARIA label
                    if place_value.get('aria'):
                        locators.append(f"[aria-label='{place_value['aria']}']")
                        tier_labels.append("T2:aria")
                    # Tier 3: AxesXPath — relational, stability-ordered
                    for axe in place_value.get('axes_xpath', []):
                        if isinstance(axe, dict) and axe.get('xpath'):
                            locators.append(axe['xpath'])
                            tier_labels.append(f"T3:axes:{axe.get('strategy', '?')}")
                        elif isinstance(axe, str):
                            locators.append(axe)
                            tier_labels.append("T3:axes:raw")
                    # Tier 4: Anchor text (proximity-based)
                    if place_value.get('anchor_text'):
                        locators.append(f":right-of(:text('{place_value['anchor_text']}'))")
                        tier_labels.append("T4:anchor")
                    # Tier 5: Inner text / text content match
                    if place_value.get('inner_text'):
                        locators.append(f"text='{place_value['inner_text']}'")
                        tier_labels.append("T5:inner_text")
                    if place_value.get('text'):
                        locators.append(f"text='{place_value['text']}'")
                        tier_labels.append("T5:text")
                    # Tier 6: CSS selector
                    if place_value.get('selector'):
                        locators.append(place_value['selector'])
                        tier_labels.append("T6:css")
                    # Tier 7: Standard XPath (positional — most fragile)
                    if place_value.get('xpath'):
                        locators.append(place_value['xpath'])
                        tier_labels.append("T7:xpath")
                    
                    if action == 'extract_data':
                        res, winning_loc = await _interact(locators, action)
                        if res is not False and res is not None:
                            # Find which tier won
                            if winning_loc:
                                idx = locators.index(winning_loc) if winning_loc in locators else -1
                                tier_info = tier_labels[idx] if 0 <= idx < len(tier_labels) else "unknown"
                                logger.info(f"Locator resolved via {tier_info}: {winning_loc[:60]}")
                            console.print(f"[bold cyan]📊 Extracted Data:[/bold cyan] {res.strip()}")
                            return res.strip()
                    else:
                        success, winning_loc = await _interact(locators, action, text)
                        # Telemetry: log which tier resolved
                        if success and winning_loc:
                            idx = locators.index(winning_loc) if winning_loc in locators else -1
                            tier_info = tier_labels[idx] if 0 <= idx < len(tier_labels) else "unknown"
                            console.print(f"[dim]📍 Resolved via {tier_info}[/dim]")
                            logger.info(f"Locator resolved via {tier_info}: {winning_loc[:80]}")

                    # Tier 8: Coordinate Fallback — scroll-aware using normalized coordinates
                    coord_bbox = face_value.get('bounding_box') if face_value else None
                    if not success and coord_bbox and action in ['click']:
                        console.print("[yellow]⚠️ DOM Selectors Failed. Attempting Coordinate Fallback...[/yellow]")
                        try:
                            # Prefer normalized coordinates (cross-resolution) if available
                            if coord_bbox.get('nx') is not None and coord_bbox.get('ny') is not None:
                                viewport = await self.browser.page.viewport_size
                                if viewport:
                                    vw = viewport.get('width', 1280)
                                    vh = viewport.get('height', 800)
                                else:
                                    vw, vh = 1280, 800
                                click_x = int(coord_bbox['nx'] * vw + coord_bbox.get('nw', 0) * vw / 2)
                                click_y = int(coord_bbox['ny'] * vh + coord_bbox.get('nh', 0) * vh / 2)
                            else:
                                # Fallback to absolute coordinates
                                click_x = coord_bbox.get('x', 0)
                                click_y = coord_bbox.get('y', 0)
                                if 'w' in coord_bbox or 'width' in coord_bbox:
                                    w = coord_bbox.get('w', coord_bbox.get('width', 0))
                                    h = coord_bbox.get('h', coord_bbox.get('height', 0))
                                    click_x = click_x + w // 2
                                    click_y = click_y + h // 2
                                    
                            # Scroll to the position where the element was originally captured
                            if coord_bbox.get('scrollX') is not None or coord_bbox.get('scrollY') is not None:
                                orig_sx = coord_bbox.get('scrollX', 0)
                                orig_sy = coord_bbox.get('scrollY', 0)
                                await self.browser.page.evaluate(f"window.scrollTo({orig_sx}, {orig_sy})")
                                await self.browser.page.wait_for_timeout(200)
                                    
                            await self.browser.page.mouse.click(click_x, click_y)
                            await self.browser.page.wait_for_load_state('networkidle')
                            success = True
                            console.print(f"[green]✅ Coordinate Fallback Succeeded at ({click_x}, {click_y})[/green]")
                            logger.info(f"Locator resolved via T8:coordinate at ({click_x}, {click_y})")
                        except Exception as e:
                            logger.debug(f"Coordinate fallback failed: {e}")

                    # Tier 9: Visual/OpenCV Fallback (most expensive)
                    if not success and place_value.get('visual_base64'):
                        console.print("[yellow]⚠️ Engaging OpenCV Visual Fallback...[/yellow]")
                        import base64
                        full_page_bytes = await self.browser.page.screenshot()
                        full_page_b64 = base64.b64encode(full_page_bytes).decode('utf-8')
                        
                        from core.vision_matcher import VisionMatcher
                        match_res = VisionMatcher.match_template(full_page_b64, place_value['visual_base64'])
                        if match_res['success']:
                            console.print(f"[green]🎯 Visual Match Found at {match_res['x']}, {match_res['y']}! (Confidence: {match_res['confidence']:.2f})[/green]")
                            logger.info(f"Locator resolved via T9:opencv at ({match_res['x']}, {match_res['y']}) conf={match_res['confidence']:.2f}")
                            if action == 'click':
                                await self.browser.page.mouse.click(match_res['x'], match_res['y'])
                                await self.browser.page.wait_for_load_state('networkidle')
                                success = True
                        else:
                            console.print(f"[red]❌ Visual Match Failed (Confidence: {match_res.get('confidence', 0):.2f})[/red]")
                                
                nid_str = str(node_id) if node_id is not None else None
                if not success and nid_str and nid_str in node_map:
                    selector = node_map[nid_str]['selector']
                    if action == 'extract_data':
                        text_content = await self.browser.page.locator(selector).text_content()
                        console.print(f"[bold cyan]📊 Extracted Data:[/bold cyan] {text_content.strip()}")
                        return text_content.strip()
                    else:
                        success, _ = await _interact([selector], action, text)

            elif action == 'scroll_down':
                await self.browser.page.evaluate("window.scrollBy(0, window.innerHeight)")
                success = True
                
            elif action == 'done':
                success = True
                
            if self.enable_screenshots:
                await self.browser.page.screenshot(path=f"data/screenshots/after_{timestamp}.png")
                
            return success
        except Exception as e:
            console.print(f"[red]Execution Error: {e}[/red]")
            return False

    async def _ai_heal_node(self, node: Dict, execution_context: Dict) -> bool:
        """
        W.3: AI Self-Healing — uses LLM to generate an alternative action
        when the cached graph node fails on the current DOM.
        """
        try:
            inspector = DOMInspector(self.browser.page)
            dom_string, node_map = await inspector.get_interactive_elements()
            
            healing_prompt = (
                f"[WORKFLOW SELF-HEALING]\n"
                f"The cached action for intent '{node['intent']}' failed.\n"
                f"Original action: {node['action_type']} with params: {node.get('action_params', {})}\n"
                f"Execution history: {self.current_footprint[-5:]}\n"
                f"Current URL: {self.browser.page.url}\n\n"
                f"DOM:\n{dom_string}\n\n"
                f"Generate the BEST alternative action to accomplish the same intent."
            )
            
            response = self.llm.ask(self.system_instruction, healing_prompt)
            action = response.get('action')
            params = response.get('action_params', {})
            
            if action:
                console.print(f"[green]🧠 AI Heal: {action} {params}[/green]")
                result = await self._execute_playwright_action(action, params, node_map)
                if result is not False:
                    self._breaker.record_success()
                    return True
        except Exception as e:
            logger.warning(f"AI self-healing failed for '{node.get('intent')}': {e}")
        
        return False

    async def _execute_workflow_graph(self, node: Dict, execution_context: Dict = None,
                                       _visited: set = None, _depth: int = 0,
                                       pause_event: "asyncio.Event" = None) -> bool:
        """Recursively executes the Linked Action Graph from Federated Memory."""
        # W.4: Per-node pause checkpoint — blocks if workflow is paused
        if pause_event is not None:
            await pause_event.wait()
        # W.1: Cycle detection during execution
        _visited = _visited if _visited is not None else set()
        node_id = node.get('id') or node.get('intent', '')
        if node_id in _visited:
            console.print(f"[bold red]🔄 CYCLE DETECTED: '{node['intent']}' already visited. Halting.[/bold red]")
            self._write_to_dlq(node, f"Cycle detected: {node_id} revisited")
            return False
        _visited.add(node_id)
        
        # W.1: Depth limit during execution
        MAX_EXECUTION_DEPTH = 50
        if _depth >= MAX_EXECUTION_DEPTH:
            console.print(f"[bold red]📏 MAX DEPTH ({MAX_EXECUTION_DEPTH}) reached. Halting.[/bold red]")
            self._write_to_dlq(node, f"Max execution depth {MAX_EXECUTION_DEPTH} exceeded")
            return False
        
        # Phase 7 → Enterprise Circuit Breaker
        if not self._breaker.allow_request():
            console.print(f"[bold red]🛑 CIRCUIT BREAKER OPEN ({self._breaker.name})! Halt execution.[/bold red]")
            self._write_to_dlq(node, f"Circuit breaker '{self._breaker.name}' is OPEN — too many consecutive failures.")
            return False
            
        console.print(f"[bold magenta]🚀 Executing Workflow Graph Node: {node['intent']} (depth={_depth})[/bold magenta]")
        
        action_type = node['action_type']
        params = node['action_params'].copy()
        execution_context = execution_context or {}
        
        # Phase 9: Multi-domain navigation jump
        current_url = self.browser.page.url
        if current_url and current_url != "about:blank":
            from urllib.parse import urlparse
            current_domain = urlparse(current_url).netloc
            target_domain = node.get('domain', '')
            if target_domain and target_domain not in current_domain:
                console.print(f"[bold yellow]🌐 Cross-Domain Jump Detected:[/bold yellow] Navigating to {target_domain}")
                await self.browser.page.goto(f"https://{target_domain}")
                await self.browser.page.wait_for_load_state('networkidle')
        
        # Inject user data from the execution_context and workflow_vars (Phase 2 & Phase 5)
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("vault://"):
                # Phase 7: Secure secrets injection
                secret_key = v.replace("vault://", "").strip()
                secret_val = self.secret_manager.get_secret(secret_key)
                params[k] = secret_val
                console.print(f"[cyan]🔐 Injected secret for parameter '{k}'[/cyan]")
                continue
                
            if isinstance(v, str):
                import re
                def replace_var(match):
                    var_name = match.group(1).strip()
                    return str(execution_context.get(var_name, self.workflow_vars.get(var_name, match.group(0))))
                
                new_v = re.sub(r'\{\{([^}]+)\}\}', replace_var, v)
                params[k] = new_v
                
            if params[k] == "<REDACTED>" or (isinstance(params[k], str) and params[k].startswith("{") and params[k].endswith("}")):
                # Legacy exact match fallback
                param_key = params[k].strip("{}") if isinstance(params[k], str) and params[k].startswith("{") else f"input_for_{node['intent']}"
                if param_key in execution_context:
                    params[k] = execution_context[param_key]
                elif param_key in self.workflow_vars:
                    params[k] = self.workflow_vars[param_key]
                    
        # Double check no redacted data slipped through
        if params.get("text") == "<REDACTED>":
            console.print(f"[bold red]❌ CANNOT EXECUTE: Input data was redacted for privacy and not provided.[/bold red]")
            return False
            
        place_value = node.get('place_value', {})
        volatility = node.get('volatility_type', 'static')
        plugin = node.get('fallback_plugin')
        
        # --- Pre-Emptive Plugin Execution for Volatile Nodes ---
        if volatility in ['dynamic', 'bubble'] and plugin:
            console.print(f"[bold magenta]🧩 Executing External Plugin for Volatile Node:[/bold magenta] {plugin}")
            plugin_success = await self.plugin_manager.execute_plugin(plugin, self.browser.page, params, self.workflow_vars)
            
            if plugin_success:
                console.print(f"[green]Plugin successfully resolved the volatile block.[/green]")
                # We skip standard playwright logic and just return True since the plugin handled the interaction
                return True
            else:
                console.print(f"[bold red]❌ Plugin failed to resolve block![/bold red]")
                return False
        
        inspector = DOMInspector(self.browser.page)
        dom_string, node_map = await inspector.get_interactive_elements()
        
        # Phase 14: Sub-Workflow Trigger (Hierarchical Intent)
        if action_type == 'trigger_sub_workflow':
            target_intent = params.get('target_intent')
            console.print(f"[bold cyan]🔗 Triggering Sub-Workflow:[/bold cyan] {target_intent}")
            
            # Fetch the sub-graph from memory using a generic search that respects fallback tier
            sub_graph = self.memory.get_workflow_graph(self.browser.page.url, target_intent, self.context_dict, self.max_fallback_tier)
            
            if sub_graph:
                # Recursively execute the sub-graph with shared visited set (W.1: cross-workflow cycle detection)
                sub_success = await self._execute_workflow_graph(sub_graph, execution_context, _visited, _depth + 1, pause_event)
                if not sub_success:
                    console.print(f"[bold red]❌ Sub-Workflow '{target_intent}' Failed![/bold red]")
                    return False
                
                # If sub-workflow succeeds, we consider this node a success and continue the parent graph
                result = True
            else:
                console.print(f"[bold red]❌ Sub-Workflow '{target_intent}' Not Found in Memory![/bold red]")
                return False
        else:
            face_value_from_node = node.get('face_value', {})
            result = await self._execute_playwright_action(action_type, params, node_map, place_value=place_value, face_value=face_value_from_node)
        
        
        if result is not False:
            self.current_footprint.append({"action_type": action_type, "action_params": params, "selector": place_value.get('selector')})
            self.memory.promote_client_secondary(node['id'])
            
            # Save Output Variable
            output_var = node.get('output_var')
            if output_var and isinstance(result, str):
                self.workflow_vars[output_var] = result
                console.print(f"[green]Saved variable '{output_var}' = '{result}'[/green]")
            
            if action_type == 'done':
                return True
                
            # Phase 7: Record success in circuit breaker
            self._breaker.record_success()
            
            if node.get("next_nodes") and len(node["next_nodes"]) > 0:
                # W.5: Dynamic Parallel Execution for independent branches
                if node.get('execution_mode') == 'parallel' and len(node['next_nodes']) > 1:
                    console.print(f"[bold cyan]⚡ Parallel Execution: Launching {len(node['next_nodes'])} branches (max {self._parallel_semaphore._value} concurrent)...[/bold cyan]")

                    async def _guarded_branch(branch, ctx, visited, depth, pe):
                        async with self._parallel_semaphore:
                            return await self._execute_workflow_graph(branch, ctx, visited, depth, pe)

                    tasks = [
                        _guarded_branch(
                            branch, execution_context.copy(), _visited.copy(), _depth + 1, pause_event
                        )
                        for branch in node['next_nodes']
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    all_success = all(r is True for r in results)
                    if not all_success:
                        failed = [node['next_nodes'][i].get('intent', '?') for i, r in enumerate(results) if r is not True]
                        console.print(f"[red]Parallel branches failed: {failed}[/red]")
                    return all_success
                
                # Sequential execution (existing logic with W.1 depth/visited propagation)
                next_node_dict = node["next_nodes"][0]
                if len(node["next_nodes"]) > 1:
                    console.print(f"[yellow]🛤️ Branching detected! Evaluating {len(node['next_nodes'])} options...[/yellow]")
                    available_next_intents = [n['intent'] for n in node["next_nodes"]]
                    chosen_intent = self.preflight_validator.evaluate_branch(available_next_intents, self.workflow_vars)
                    console.print(f"[green]🛣️ Selected path: {chosen_intent}[/green]")
                    next_node_dict = next((n for n in node["next_nodes"] if n['intent'] == chosen_intent), node["next_nodes"][0])
                    
                self.active_graph_parent_intent = node['intent']
                return await self._execute_workflow_graph(next_node_dict, execution_context, _visited, _depth + 1, pause_event)
            else:
                self.active_graph_parent_intent = None
                return True # End of graph
        else:
            if volatility == 'optional':
                console.print(f"[yellow]🫧 Optional Action '{node['intent']}' Skipped.[/yellow]")
                if node.get("next_nodes") and len(node["next_nodes"]) > 0:
                    next_node_dict = node["next_nodes"][0]
                    if len(node["next_nodes"]) > 1:
                        available_next_intents = [n['intent'] for n in node["next_nodes"]]
                        chosen_intent = self.preflight_validator.evaluate_branch(available_next_intents, self.workflow_vars)
                        next_node_dict = next((n for n in node["next_nodes"] if n['intent'] == chosen_intent), node["next_nodes"][0])
                    self.active_graph_parent_intent = node['intent']
                    return await self._execute_workflow_graph(next_node_dict, execution_context, _visited, _depth + 1, pause_event)
                self.active_graph_parent_intent = None
                return True
            
            # W.3: Two-Tiered AI Fallback Chain
            self._breaker.record_failure()
            console.print(f"[bold red]❌ Graph Node Failed! (breaker: {self._breaker.state.value})[/bold red]")
            
            # Tier 1: AI Self-Healing
            console.print("[yellow]🧠 Tier 1 Fallback: AI Self-Healing...[/yellow]")
            heal_success = await self._ai_heal_node(node, execution_context or {})
            if heal_success:
                console.print("[green]✅ AI Self-Healing succeeded![/green]")
                if node.get("next_nodes") and len(node["next_nodes"]) > 0:
                    next_node_dict = node["next_nodes"][0]
                    self.active_graph_parent_intent = node['intent']
                    return await self._execute_workflow_graph(next_node_dict, execution_context, _visited, _depth + 1, pause_event)
                return True
            
            # Tier 2: Plugin-based healing (if defined)
            if plugin:
                console.print(f"[yellow]🧩 Tier 2 Fallback: Plugin '{plugin}'...[/yellow]")
                plugin_success = await self.plugin_manager.execute_plugin(plugin, self.browser.page, params, self.workflow_vars)
                if plugin_success:
                    console.print("[green]✅ Plugin healing succeeded![/green]")
                    if node.get("next_nodes") and len(node["next_nodes"]) > 0:
                        next_node_dict = node["next_nodes"][0]
                        self.active_graph_parent_intent = node['intent']
                        return await self._execute_workflow_graph(next_node_dict, execution_context, _visited, _depth + 1, pause_event)
                    return True
            
            # All tiers exhausted
            self.last_failure_context = f"Failed to execute cached node: {node['intent']}"
            if not self._breaker.allow_request():
                console.print(f"[bold red]🛑 CIRCUIT BREAKER OPEN during fallback chain![/bold red]")
                self._write_to_dlq(node, self.last_failure_context)
                self.workflow_vars = {}  # E-06: Prevent leaked vars
                
            return False

    def _write_to_dlq(self, node: Dict, reason: str):
        """Phase 7: Dead-Letter Queue (DLQ) for failed workflows."""
        from pathlib import Path
        import time
        dlq_dir = Path("data/dlq")
        dlq_dir.mkdir(parents=True, exist_ok=True)
        dlq_file = dlq_dir / f"dlq_{int(time.time())}.json"
        
        # C5 Fix: Scrub resolved vault secrets from workflow_vars before persisting
        safe_vars = {}
        for k, v in self.workflow_vars.items():
            if isinstance(v, str) and any(hint in k.lower() for hint in
                ('password', 'secret', 'token', 'key', 'api_key', 'auth', 'credential')):
                safe_vars[k] = "<REDACTED:vault_secret>"
            else:
                safe_vars[k] = v
        
        dlq_data = {
            "timestamp": time.time(),
            "session_id": self.memory.session_id,
            "failed_node": node,
            "reason": reason,
            "workflow_vars": safe_vars,
            "execution_context": getattr(self, "execution_context", {})
        }
        
        with open(dlq_file, 'w') as f:
            json.dump(dlq_data, f, indent=4)
        console.print(f"[yellow]📥 Failed workflow written to DLQ: {dlq_file}[/yellow]")
            
    def _get_context_hash(self) -> str:
        device = self.context_dict.get('device', 'desktop')
        os_name = self.context_dict.get('os', 'mac')
        browser = self.context_dict.get('browser', 'chromium')
        w = self.context_dict.get('viewport_width', 1280)
        h = self.context_dict.get('viewport_height', 720)
        return self.memory._generate_context_hash(device, os_name, browser, f"{w}x{h}")

    async def chat_step(self, user_intent: str, visibility: str = "public") -> Any:
        url = self.browser.page.url
        console.print(f"[cyan]Current URL:[/cyan] {url}")
        # E-07: Reset circuit breaker for each new user command
        self._breaker.reset()  # E-07: Reset circuit breaker for each new user command
        
        # --- Pre-flight Validation State Check ---
        if self.pending_workflow_graph:
            console.print("[yellow]🔄 Resuming Pre-flight Validation...[/yellow]")
            res = self.preflight_validator.process_intent(user_intent, self.required_params, self.execution_context)
            if res["status"] == "MISSING_DATA":
                return res["question"]
            elif res["status"] == "READY":
                self.execution_context = res["context"]
                graph_to_execute = self.pending_workflow_graph
                # Clear state
                self.pending_workflow_graph = None
                self.required_params = []
                
                success = await self._execute_workflow_graph(graph_to_execute, self.execution_context)
                if success:
                    self.current_footprint = []
                    self.previous_intent = None
                    self.execution_context = {}
                    return True
                return False

        if self.previous_intent is None:
            self.workflow_vars = {}
            
        # --- Map Natural Language to Canonical Intent (Vector-Assisted) ---
        raw_intents = self.memory.search_intents(user_intent)
        available_intents = [item['intent'] for item in raw_intents]
        if not available_intents:
            available_intents = self.memory.get_available_intents(url)
        canonical_intent = self.preflight_validator.map_intent_to_canonical(user_intent, available_intents)
        console.print(f"[cyan]Mapped Intent:[/cyan] {canonical_intent}")
        
        # 1. Lookup Workflow Graph
        graph = self.memory.get_workflow_graph(url, canonical_intent, self.context_dict, self.max_fallback_tier)
        if graph and graph.get("next_nodes"):
            console.print(f"[green]⚡ Workflow Graph Found! Running Pre-flight Check...[/green]")
            req_params = self.preflight_validator.analyze_graph(graph)
            
            res = self.preflight_validator.process_intent(canonical_intent, req_params, self.execution_context)
            if res["status"] == "MISSING_DATA":
                self.pending_workflow_graph = graph
                self.required_params = req_params
                return res["question"]
            elif res["status"] == "READY":
                self.execution_context = res["context"]
                success = await self._execute_workflow_graph(graph, self.execution_context)
                if success:
                    self.current_footprint = []
                    self.previous_intent = None
                    self.execution_context = {}
                    return True
        
        inspector = DOMInspector(self.browser.page)
        dom_string, node_map = await inspector.get_interactive_elements()
        
        intent_key = f"{canonical_intent}_{url_parse(url).path}"
        
        # 2. Lookup Single Action Memory
        cached_action = self.memory.lookup_action(url, intent_key, self.context_dict, self.max_fallback_tier)
        
        if cached_action and cached_action.get('tier') in ['client_primary', 'server_primary']:
            console.print(f"[bold green]⚡ Primary Action Memory Triggered![/bold green]")
            action = cached_action['action_type']
            params = cached_action['action_params']
            place_value = cached_action.get('place_value', {})
            
            success = await self._execute_playwright_action(action, params, node_map, place_value=place_value)
            if success:
                self.current_footprint.append({"action_type": action, "action_params": params, "selector": place_value.get('selector')})
            if action == 'done':
                self.current_footprint = []
                self.previous_intent = None
                self.active_graph_parent_intent = None
                return True
            
            # If we just self-healed, we should link back to the broken graph's parent!
            if self.active_graph_parent_intent:
                console.print(f"[bold magenta]🔗 Linking self-healed node to broken graph parent: {self.active_graph_parent_intent}[/bold magenta]")
                # We overwrite the previous_intent context just for this linking step
                self.previous_intent = f"{self.active_graph_parent_intent}_{url_parse(url).path}"
                self.active_graph_parent_intent = None # Reset after stitching
                
            self.previous_intent = intent_key
            return False
                
        elif cached_action and cached_action.get('tier') in ['client_secondary', 'server_secondary']:
            console.print(f"[bold yellow]🔍 Secondary Memory Found.[/bold yellow] Running LLM Validation...")
            face = cached_action['face_value']
            prompt = f"Goal Intent: {user_intent}\nCached Action: {cached_action['action_type']}\nTarget Element FACE: '{face.get('description', '')}'\nDOM:\n{dom_string}\nIs it valid?"
            try:
                val_res = self.llm.ask(self.validation_instruction, prompt)
                if val_res.get('is_valid'):
                    console.print("[green]✅ Validation Passed. Executing and Promoting...[/green]")
                    action = cached_action['action_type']
                    params = cached_action['action_params']
                    if val_res.get('updated_node_id'):
                        params['node_id'] = val_res.get('updated_node_id')
                        
                    place_value = cached_action.get('place_value', {})
                    success = await self._execute_playwright_action(action, params, node_map, place_value=place_value)
                    if success:
                        self.memory.promote_client_secondary(cached_action['id'])
                        self.current_footprint.append({"action_type": action, "action_params": params, "selector": place_value.get('selector')})
                        if action == 'done':
                            self.current_footprint = []
                            self.previous_intent = None
                            return True
                        self.previous_intent = intent_key
                        return False
                else:
                    self.memory.demote_client_secondary(cached_action['id'])
            except Exception as e:
                logger.warning(f"Secondary memory validation failed: {e}")
        
        # === 3. LLM FALLBACK GENERATION ===
        console.print("[blue]🧠 Generating new action via LLM...[/blue]")
        prompt_context = f"Goal: {user_intent}\nURL: {url}\n\nDOM:\n{dom_string}\n\nWhat is your next action?"
        
        if self.last_failure_context:
            prompt_context = f"[CRITICAL SELF-HEALING EVENT]\nYou were executing a cached workflow which just failed. History of successful steps: {self.current_footprint}.\nFailure context: {self.last_failure_context}\nGenerate the next best action to recover and continue the workflow.\n\n" + prompt_context
            self.last_failure_context = None
            
        try:
            response = self.llm.ask(self.system_instruction, prompt_context)
            action = response.get('action')
            params = response.get('action_params', {})
            console.print(f"⚡ Action: {action} {params}")
            
            success = await self._execute_playwright_action(action, params, node_map)
            
            if success:
                selector = None
                if action in ['click', 'type']:
                    node_id = params.get('node_id')
                    nid_str = str(node_id) if node_id is not None else None
                    if nid_str and nid_str in node_map:
                        node = node_map[nid_str]
                        selector = node['selector']
                        
                        # face_value: semantic identity + physical coordinates
                        face_val = {
                            "description": node['text'],
                            "label_words": [node['text']],
                            "bounding_box": node.get('bounding_box', {
                                "x": node["x"], "y": node["y"],
                                "w": node["width"], "h": node["height"]
                            }),
                            "element_signature": node.get('element_signature', {
                                "tag": node.get("tag", "unknown"),
                                "role": node.get("role", ""),
                            }),
                        }
                        
                        # place_value: structural DOM address + locators
                        place_val = {
                            "selector": selector,
                            "test_id": node.get("test_id"),
                            "aria": node.get("aria_name"),
                            "inner_text": node.get("inner_text"),
                            "text": node.get("text"),
                            "xpath": node.get("xpath"),
                            "axes_xpath": node.get("axes_xpath", []),
                            "anchor_text": node.get("anchor_text"),
                        }
                        
                        try:
                            import base64
                            screenshot_bytes = await self.browser.page.locator(selector).first.screenshot()
                            place_val["visual_base64"] = base64.b64encode(screenshot_bytes).decode('utf-8')
                        except Exception as e:
                            logger.debug(f"Visual screenshot capture failed: {e}")
                        
                        # Add raw input to place_val for potential scrubbing later
                        if action == "type" and "text" in params:
                            place_val["input_data"] = params["text"]
                        
                        self.memory.save_new_action(
                            url=url, 
                            intent=intent_key, 
                            face_value=face_val, 
                            place_value=place_val, 
                            action_type=action, 
                            action_params=params, 
                            previous_intent=self.previous_intent,
                            context_hash=self._get_context_hash(),
                            visibility=visibility
                        )
                
                self.current_footprint.append({"action_type": action, "action_params": params, "selector": selector})
                self.previous_intent = intent_key
                
                if action == 'done':
                    self.current_footprint = []
                    self.previous_intent = None
                    return True
                    
        except Exception as e:
            console.print(f"[red]LLM Generation Error: {e}[/red]")
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            
        return False


# ── Backward-compatible alias (v5.0 migration) ──────────────────────────────
# All existing imports of `from core.agent_loop import AgentLoop` continue to work.
AgentLoop = ActorLoop
