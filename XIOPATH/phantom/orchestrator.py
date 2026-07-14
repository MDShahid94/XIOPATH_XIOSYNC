"""
XIOPATH Phantom Infrastructure — Master Orchestrator
======================================================
End-to-end pipeline: Forge → Chain → Sanitize → Migrate → Age → Harvest → Mesh.
Coordinates all phantom lifecycle phases from creation to mesh deployment.

Educational purpose only.
"""

import json
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("phantom.orchestrator")


class PipelinePhase(Enum):
    """Phases of the phantom provisioning pipeline."""
    IDENTITY_FORGE = "identity_forge"
    GOOGLE_CREATION = "google_creation"
    VERIFICATION = "verification"
    SANITIZATION = "sanitization"
    SESSION_MIGRATION = "session_migration"
    PROFILE_AGING = "profile_aging"
    SERVICE_CHAIN = "service_chain"
    RESOURCE_HARVEST = "resource_harvest"
    MESH_REGISTRATION = "mesh_registration"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ProvisioningJob:
    """Tracks the state of a single phantom provisioning pipeline."""
    phantom_id: str
    member_donor_id: str
    current_phase: PipelinePhase = PipelinePhase.IDENTITY_FORGE
    phases_completed: list = field(default_factory=list)
    identity_data: dict = field(default_factory=dict)
    google_result: dict = field(default_factory=dict)
    sanitize_result: dict = field(default_factory=dict)
    chain_results: dict = field(default_factory=dict)
    harvest_result: dict = field(default_factory=dict)
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    verification_pending: bool = False
    verification_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phantom_id": self.phantom_id,
            "member_donor_id": self.member_donor_id,
            "current_phase": self.current_phase.value,
            "phases_completed": [p.value if isinstance(p, PipelinePhase) else p for p in self.phases_completed],
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "verification_pending": self.verification_pending,
        }


class PhantomOrchestrator:
    """
    Master pipeline that orchestrates the full phantom lifecycle.
    
    Pipeline Flow:
        1. Identity Forge → Generate synthetic identity
        2. Google Creation → Create Google account (may need member verification)
        3. Sanitization → Sever device linkage, rotate creds, enable 2FA
        4. Session Migration → 3-day IP migration
        5. Profile Aging → 30-day warm-up (can overlap with migration)
        6. Service Chain → Register CF, GitHub, Kaggle via OAuth cascade
        7. Resource Harvest → Deploy Node Agent, create D1/R2/KV, generate notebooks
        8. Mesh Registration → Wire into Control Plane
    """

    def __init__(self, vault, browser_manager, proxy_pool, control_plane_url: str,
                 ontology_bridge=None):
        """
        Args:
            vault: CredentialVault instance
            browser_manager: BrowserProfileManager instance
            proxy_pool: ProxyPool instance
            control_plane_url: URL of the XIOPATH Control Plane
            ontology_bridge: Optional PhantomOntologyBridge for ontology integration
        """
        self.vault = vault
        self.browser_manager = browser_manager
        self.proxy_pool = proxy_pool
        self.control_plane_url = control_plane_url
        self.bridge = ontology_bridge
        self._jobs: dict[str, ProvisioningJob] = {}

    async def provision_phantom(self, member_donor_id: str, locale: str = "en-US",
                                 timezone_name: str = "America/New_York",
                                 member_ip_country: str = "US") -> ProvisioningJob:
        """
        Start a new phantom provisioning pipeline.
        
        This is the main entry point. It runs through the pipeline phases,
        pausing at verification if member interaction is required.
        
        Args:
            member_donor_id: ID of the member donating compute resources
            locale: Locale for the synthetic identity
            timezone_name: Timezone for the browser fingerprint
            member_ip_country: Country code for session migration planning
        
        Returns:
            ProvisioningJob with current state
        """
        from phantom.identity_forge import IdentityForge, IdentityValidator
        from phantom.crypto import uuid7

        phantom_id = uuid7()
        job = ProvisioningJob(
            phantom_id=phantom_id,
            member_donor_id=member_donor_id,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._jobs[phantom_id] = job

        logger.info(f"Starting provisioning pipeline for phantom {phantom_id[:8]}")

        # ═══ Register phantom in ontology ═══
        if self.bridge:
            identity_summary = {"locale": locale, "timezone": timezone_name}
            self.bridge.register_phantom_as_agent(phantom_id, identity_summary, member_donor_id)

        # ════ Phase 1: Identity Forge ════
        try:
            job.current_phase = PipelinePhase.IDENTITY_FORGE
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "identity_forge", "provisioning", "provisioning", "pending")

            forge = IdentityForge(locale)
            identity = forge.forge_identity()

            # Validate
            valid, issues = IdentityValidator.validate(identity)
            if not valid:
                job.error = f"Identity validation failed: {issues}"
                job.current_phase = PipelinePhase.FAILED
                if self.bridge:
                    self.bridge.record_provision_phase(phantom_id, "identity_forge", "provisioning", "provisioning", "failed", str(issues))
                return job

            job.identity_data = identity
            job.phases_completed.append(PipelinePhase.IDENTITY_FORGE)
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "identity_forge", "provisioning", "provisioning", "success")
            logger.info(f"Phase 1 (Identity Forge) complete: {identity['email']}")

        except Exception as e:
            job.error = str(e)
            job.current_phase = PipelinePhase.FAILED
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "identity_forge", "provisioning", "provisioning", "failed", str(e))
            return job

        # ════ Phase 2: Create Browser Profile ════
        profile = self.browser_manager.create_profile(
            phantom_id=phantom_id,
            locale=locale,
            timezone_name=timezone_name,
        )
        pw_options = self.browser_manager.get_playwright_context_options(phantom_id)
        fp_script = self.browser_manager.get_fingerprint_injection_script(phantom_id)

        # ════ Phase 3: Google Account Creation ════
        try:
            job.current_phase = PipelinePhase.GOOGLE_CREATION
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "google_creation", "provisioning", "provisioning", "pending")

            from phantom.chains.google import GoogleAccountCreator

            creator = GoogleAccountCreator(
                identity=identity,
                browser_profile_options=pw_options,
                fingerprint_script=fp_script,
                proxy_config=profile.proxy_config,
            )
            google_result = await creator.create_account()
            job.google_result = google_result

            if google_result.get("verification_needed"):
                # Pause pipeline — member must verify
                job.verification_pending = True
                job.verification_data = google_result["verification_needed"]
                job.current_phase = PipelinePhase.VERIFICATION
                if self.bridge:
                    self.bridge.record_provision_phase(phantom_id, "verification", "provisioning", "provisioning", "pending", "Awaiting member device verification")
                logger.info(f"Verification needed for {phantom_id[:8]}: {google_result['verification_needed']['type']}")
                return job

            if not google_result.get("success"):
                job.error = google_result.get("error", "Google creation failed")
                job.current_phase = PipelinePhase.FAILED
                if self.bridge:
                    self.bridge.record_provision_phase(phantom_id, "google_creation", "provisioning", "provisioning", "failed", job.error)
                return job

            # Store initial identity in vault
            vault_data = {
                "synthetic": identity,
                "google": {
                    "email": google_result["email"],
                    "password": google_result["password"],
                    "session_cookies": google_result["session_cookies"],
                    "totp_seed": None,
                    "backup_codes": [],
                },
                "services": {},
                "member_donor_id": member_donor_id,
                "state": "provisioning",
            }
            self.vault.store_identity(phantom_id, vault_data)
            job.phases_completed.append(PipelinePhase.GOOGLE_CREATION)
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "google_creation", "provisioning", "provisioning", "success")
            logger.info(f"Phase 3 (Google Creation) complete: {google_result['email']}")

        except Exception as e:
            job.error = str(e)
            job.current_phase = PipelinePhase.FAILED
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "google_creation", "provisioning", "provisioning", "failed", str(e))
            return job

        # Continue with post-creation phases
        return await self._continue_post_creation(job, member_ip_country)

    async def resume_after_verification(self, phantom_id: str,
                                         verification_response: dict,
                                         member_ip_country: str = "US") -> ProvisioningJob:
        """
        Resume the pipeline after member verification.
        
        Args:
            phantom_id: The phantom being provisioned
            verification_response: {type: 'otp'|'link', value: '...'}
            member_ip_country: Country for session migration
        """
        job = self._jobs.get(phantom_id)
        if not job:
            raise ValueError(f"No provisioning job found for {phantom_id}")

        # Handle the verification
        # (In practice, this would interact with the browser session that's waiting)
        job.verification_pending = False
        job.phases_completed.append(PipelinePhase.VERIFICATION)
        job.phases_completed.append(PipelinePhase.GOOGLE_CREATION)

        # Store initial identity
        vault_data = {
            "synthetic": job.identity_data,
            "google": {
                "email": job.google_result.get("email"),
                "password": job.google_result.get("password"),
                "session_cookies": job.google_result.get("session_cookies"),
            },
            "services": {},
            "member_donor_id": job.member_donor_id,
            "state": "provisioning",
        }
        self.vault.store_identity(phantom_id, vault_data)

        return await self._continue_post_creation(job, member_ip_country)

    async def _continue_post_creation(self, job: ProvisioningJob,
                                       member_ip_country: str) -> ProvisioningJob:
        """Continue the pipeline after Google account creation is confirmed."""
        phantom_id = job.phantom_id
        pw_options = self.browser_manager.get_playwright_context_options(phantom_id)
        fp_script = self.browser_manager.get_fingerprint_injection_script(phantom_id)

        # ════ Phase 4: Sanitization ════
        try:
            job.current_phase = PipelinePhase.SANITIZATION
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "sanitization", "provisioning", "provisioning", "pending")

            from phantom.sanitize import SanitizationPipeline

            sanitizer = SanitizationPipeline(self.vault, pw_options, fp_script)

            # We need a page for sanitization — open one
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(**pw_options)
                await context.add_init_script(fp_script)
                page = await context.new_page()

                # Restore session
                identity = self.vault.get_identity(phantom_id)
                if identity and identity.get("google", {}).get("session_cookies"):
                    cookies = identity["google"]["session_cookies"].get("cookies", [])
                    if cookies:
                        await context.add_cookies(cookies)

                sanitize_result = await sanitizer.sanitize_google_account(phantom_id, page)
                job.sanitize_result = sanitize_result

                # Save updated session
                storage = await context.storage_state()
                self.browser_manager.save_session_state(phantom_id, storage)

                await browser.close()

            job.phases_completed.append(PipelinePhase.SANITIZATION)
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "sanitization", "provisioning", "provisioning", "success")
            logger.info(f"Phase 4 (Sanitization) complete for {phantom_id[:8]}")

        except Exception as e:
            logger.error(f"Sanitization failed: {e}")
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "sanitization", "provisioning", "provisioning", "failed", str(e))
            # Non-fatal — continue with remaining phases

        # ════ Phase 5: Plan Session Migration (runs async over 3 days) ════
        try:
            job.current_phase = PipelinePhase.SESSION_MIGRATION
            from phantom.session_migration import SessionMigrator

            migrator = SessionMigrator(self.vault, self.proxy_pool, self.browser_manager)
            migration_plan = await migrator.plan_migration(phantom_id, member_ip_country)
            # Execute Day 0 steps immediately
            await migrator.run_migration(phantom_id)

            job.phases_completed.append(PipelinePhase.SESSION_MIGRATION)
            logger.info(f"Phase 5 (Migration Day 0) complete, remaining steps scheduled")

        except Exception as e:
            logger.error(f"Session migration failed: {e}")

        # ════ Phase 6: Start Profile Aging (runs over 30 days) ════
        try:
            job.current_phase = PipelinePhase.PROFILE_AGING
            from phantom.aging import ProfileAger

            ager = ProfileAger(self.vault, self.browser_manager, self.proxy_pool)
            aging_result = await ager.run_daily_aging(phantom_id)

            job.phases_completed.append(PipelinePhase.PROFILE_AGING)
            logger.info(f"Phase 6 (Aging Day 1) complete: {aging_result}")

        except Exception as e:
            logger.error(f"Profile aging failed: {e}")

        # ════ Phase 7: Service Chain (CF, GitHub, Kaggle) ════
        try:
            job.current_phase = PipelinePhase.SERVICE_CHAIN
            chain_results = await self._run_service_chains(phantom_id)
            job.chain_results = chain_results

            job.phases_completed.append(PipelinePhase.SERVICE_CHAIN)
            logger.info(f"Phase 7 (Service Chain) complete: {list(chain_results.keys())}")

        except Exception as e:
            logger.error(f"Service chain failed: {e}")

        # ════ Phase 8: Resource Harvest ════
        try:
            job.current_phase = PipelinePhase.RESOURCE_HARVEST
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "resource_harvest", "provisioning", "provisioning", "pending")

            from phantom.harvester import ResourceHarvester

            harvester = ResourceHarvester(self.vault, self.control_plane_url)
            harvest_result = await harvester.harvest_phantom(phantom_id)
            job.harvest_result = harvest_result

            # Register each harvested resource as a child agent in ontology
            if self.bridge:
                for resource in harvest_result.get("resources", []):
                    self.bridge.register_child_resource(
                        phantom_id,
                        resource.get("resource_type", "worker"),
                        resource,
                    )

            job.phases_completed.append(PipelinePhase.RESOURCE_HARVEST)
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "resource_harvest", "provisioning", "provisioning", "success")
            logger.info(f"Phase 8 (Harvest) complete: {harvest_result.get('total_resources', 0)} resources")

        except Exception as e:
            logger.error(f"Resource harvest failed: {e}")
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "resource_harvest", "provisioning", "provisioning", "failed", str(e))

        # ════ Phase 9: Mesh Registration ════
        try:
            job.current_phase = PipelinePhase.MESH_REGISTRATION
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "mesh_registration", "provisioning", "active", "pending")

            await self._register_in_mesh(phantom_id)

            job.phases_completed.append(PipelinePhase.MESH_REGISTRATION)
            self.vault.update_field(phantom_id, "state", "active")
            self.browser_manager.update_profile_state(phantom_id, "active")

            # ═══ Mark phantom as active in ontology ═══
            if self.bridge:
                self.bridge.update_phantom_state(phantom_id, "active", "Provisioning pipeline complete")
                self.bridge.record_provision_phase(phantom_id, "mesh_registration", "provisioning", "active", "success")
                self.bridge.grant_phantom_capabilities(phantom_id)

        except Exception as e:
            logger.error(f"Mesh registration failed: {e}")
            if self.bridge:
                self.bridge.record_provision_phase(phantom_id, "mesh_registration", "provisioning", "provisioning", "failed", str(e))

        # Pipeline complete
        job.current_phase = PipelinePhase.COMPLETE
        job.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(f"Provisioning complete for phantom {phantom_id[:8]}")

        return job

    async def _run_service_chains(self, phantom_id: str) -> dict:
        """Execute OAuth cascade: Google → CF → GitHub → Kaggle."""
        identity = self.vault.get_identity(phantom_id)
        if not identity:
            return {"error": "Identity not found"}

        google_cookies = identity.get("google", {}).get("session_cookies", {})
        pw_options = self.browser_manager.get_playwright_context_options(phantom_id)
        fp_script = self.browser_manager.get_fingerprint_injection_script(phantom_id)
        results = {}

        # Cloudflare
        try:
            from phantom.chains.cloudflare import CloudflareChain
            cf = CloudflareChain(google_cookies, pw_options, fp_script)
            cf_result = await cf.register()
            results["cloudflare"] = cf_result

            if cf_result.get("success"):
                self.vault.update_field(phantom_id, "services.cloudflare", {
                    "account_id": cf_result.get("account_id"),
                    "email": cf_result.get("email"),
                    "api_token": None,  # Will be set after token creation
                    "state": "active",
                })
        except Exception as e:
            results["cloudflare"] = {"error": str(e)}

        # GitHub
        try:
            from phantom.chains.github import GitHubChain
            gh = GitHubChain(google_cookies, pw_options, fp_script)
            gh_result = await gh.register()
            results["github"] = gh_result

            if gh_result.get("success"):
                self.vault.update_field(phantom_id, "services.github", {
                    "username": gh_result.get("username"),
                    "token": None,  # Will be set after PAT creation
                    "state": "active",
                })
        except Exception as e:
            results["github"] = {"error": str(e)}

        # Kaggle
        try:
            from phantom.chains.colab import KaggleChain
            kg = KaggleChain(google_cookies, pw_options, fp_script)
            kg_result = await kg.register()
            results["kaggle"] = kg_result

            if kg_result.get("success"):
                self.vault.update_field(phantom_id, "services.kaggle", {
                    "username": kg_result.get("username"),
                    "api_key": None,
                    "state": "active",
                })
        except Exception as e:
            results["kaggle"] = {"error": str(e)}

        return results

    async def _register_in_mesh(self, phantom_id: str) -> None:
        """Register the phantom's resources in the XIOPATH mesh Control Plane."""
        import urllib.request

        identity = self.vault.get_identity(phantom_id)
        if not identity:
            return

        # Build node capabilities from harvested resources
        capabilities = []
        services = identity.get("services", {})

        if services.get("cloudflare", {}).get("account_id"):
            capabilities.extend(["edge_compute", "kv_store", "d1_sql", "r2_storage"])
        if identity.get("google", {}).get("email"):
            capabilities.append("colab_gpu")
        if services.get("kaggle", {}).get("username"):
            capabilities.append("kaggle_gpu")
        if services.get("github", {}).get("username"):
            capabilities.append("ci_cd_compute")

        node_data = {
            "node_id": f"phantom-{phantom_id[:8]}",
            "phantom_id": phantom_id,
            "capabilities": capabilities,
            "services": list(services.keys()),
            "trust_score": 0.5,  # Default for new phantoms
            "state": "active",
        }

        try:
            url = f"{self.control_plane_url}/api/v1/mesh/nodes"
            body = json.dumps(node_data).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            logger.error(f"Mesh registration failed: {e}")

    # ════ Job Management ════

    def get_job(self, phantom_id: str) -> Optional[dict]:
        """Get the current state of a provisioning job."""
        job = self._jobs.get(phantom_id)
        return job.to_dict() if job else None

    def list_jobs(self, phase: str = None) -> list[dict]:
        """List all provisioning jobs, optionally filtered by phase."""
        jobs = []
        for job in self._jobs.values():
            if phase and job.current_phase.value != phase:
                continue
            jobs.append(job.to_dict())
        return jobs

    def calculate_fleet_status(self) -> dict:
        """Calculate overall fleet status across all phantoms."""
        total = len(self._jobs)
        complete = sum(1 for j in self._jobs.values() if j.current_phase == PipelinePhase.COMPLETE)
        failed = sum(1 for j in self._jobs.values() if j.current_phase == PipelinePhase.FAILED)
        pending = sum(1 for j in self._jobs.values() if j.verification_pending)
        in_progress = total - complete - failed - pending

        return {
            "total_phantoms": total,
            "complete": complete,
            "failed": failed,
            "verification_pending": pending,
            "in_progress": in_progress,
        }
