import os
import json
import time
import asyncio
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional

VAULT_FILE = Path(__file__).parent.parent / "api_vault.json"

DEFAULT_PROVIDERS = {
    "groq": {
        "name": "GroqCloud",
        "env_var": "GROQ_API_KEY",
        "api_base": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "key": "",
        "status": "UNCONFIGURED",
        "latency_ms": 0,
        "quota_remaining_rpm": 30,
        "daily_tokens_remaining": 14400
    },
    "openrouter": {
        "name": "OpenRouter Free Tier",
        "env_var": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "key": "",
        "status": "UNCONFIGURED",
        "latency_ms": 0,
        "quota_remaining_rpm": 20,
        "daily_tokens_remaining": 50000
    },
    "cerebras": {
        "name": "Cerebras Fast AI",
        "env_var": "CEREBRAS_API_KEY",
        "api_base": "https://api.cerebras.ai/v1/chat/completions",
        "default_model": "llama3.1-70b",
        "key": "",
        "status": "UNCONFIGURED",
        "latency_ms": 0,
        "quota_remaining_rpm": 30,
        "daily_tokens_remaining": 60000
    },
    "huggingface": {
        "name": "Hugging Face Inference",
        "env_var": "HF_API_KEY",
        "api_base": "https://api-inference.huggingface.co/models/meta-llama/Llama-3.3-70B-Instruct",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct",
        "key": "",
        "status": "UNCONFIGURED",
        "latency_ms": 0,
        "quota_remaining_rpm": 15,
        "daily_tokens_remaining": 30000
    },
    "github_models": {
        "name": "GitHub Models Free API",
        "env_var": "GITHUB_TOKEN",
        "api_base": "https://models.inference.ai.azure.com/chat/completions",
        "default_model": "gpt-4o-mini",
        "key": "",
        "status": "UNCONFIGURED",
        "latency_ms": 0,
        "quota_remaining_rpm": 15,
        "daily_tokens_remaining": 15000
    }
}


class APIVault:
    """
    Automated Local API Vault & Key Inventory Manager.
    Handles:
    1. Zero-Manual-Setup API Key discovery from .env and api_vault.json.
    2. Proactive health pings & latency measurement.
    3. RPM/TPM quota tracking across free cloud providers.
    """

    def __init__(self, vault_path: Path = VAULT_FILE):
        self.vault_path = vault_path
        self.providers: Dict[str, Dict[str, Any]] = json.loads(json.dumps(DEFAULT_PROVIDERS))
        self._load_vault()

    def _load_vault(self):
        """Loads keys from api_vault.json and environment variables."""
        if self.vault_path.exists():
            try:
                data = json.loads(self.vault_path.read_text(encoding="utf-8"))
                for pid, pdata in data.items():
                    if pid in self.providers:
                        self.providers[pid].update(pdata)
            except Exception as e:
                print(f"[APIVault] Error reading vault file: {e}")

        # Check environment variables
        for pid, pinfo in self.providers.items():
            env_val = os.environ.get(pinfo["env_var"], "").strip()
            if env_val:
                pinfo["key"] = env_val
                pinfo["status"] = "ONLINE"

        self._save_vault()

    def _save_vault(self):
        """Persists vault inventory back to api_vault.json."""
        try:
            self.vault_path.write_text(json.dumps(self.providers, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[APIVault] Vault save error: {e}")

    def add_or_update_key(self, provider_id: str, key_string: str) -> bool:
        """Manually or automatically provisions an API key for a provider."""
        if provider_id in self.providers:
            self.providers[provider_id]["key"] = key_string.strip()
            self.providers[provider_id]["status"] = "ONLINE" if key_string else "UNCONFIGURED"
            os.environ[self.providers[provider_id]["env_var"]] = key_string.strip()
            self._save_vault()
            return True
        return False

    def mark_rate_limited(self, provider_id: str, duration_seconds: int = 60):
        """Marks a provider as RATE-LIMITED upon receiving a 429 response."""
        if provider_id in self.providers:
            self.providers[provider_id]["status"] = "RATE-LIMITED"
            self.providers[provider_id]["quota_remaining_rpm"] = 0
            self._save_vault()

    def get_active_providers(self) -> List[Dict[str, Any]]:
        """Returns list of currently ONLINE active providers ordered by priority."""
        active = []
        for pid, pinfo in self.providers.items():
            if pinfo["status"] == "ONLINE" and pinfo["key"]:
                active.append({"provider_id": pid, **pinfo})
        return active

    def get_masked_key(self, provider_id: str) -> str:
        """Returns masked representation of key for safe logging without exposure."""
        key = self.providers.get(provider_id, {}).get("key", "")
        if not key:
            return ""
        if len(key) <= 8:
            return "********"
        return f"{key[:4]}...{key[-4:]}"

    def get_telemetry_status(self) -> List[Dict[str, Any]]:
        """Returns telemetry payload for Web Dashboard HUD."""
        out = []
        for pid, pinfo in self.providers.items():
            out.append({
                "provider_id": pid,
                "name": pinfo["name"],
                "status": pinfo["status"],
                "has_key": bool(pinfo["key"]),
                "latency_ms": pinfo["latency_ms"],
                "quota_rpm": pinfo["quota_remaining_rpm"],
                "model": pinfo["default_model"]
            })
        return out

    async def ping_provider_health(self, provider_id: str) -> Dict[str, Any]:
        """Pings provider endpoint to test key validity and latency."""
        pinfo = self.providers.get(provider_id)
        if not pinfo or not pinfo["key"]:
            return {"status": "UNCONFIGURED", "latency_ms": 0}

        start_t = time.time()
        try:
            req = urllib.request.Request(
                pinfo["api_base"],
                headers={
                    "Authorization": f"Bearer {pinfo['key']}",
                    "Content-Type": "application/json"
                },
                method="HEAD"
            )
            # Lightweight health check
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=3))
            latency = int((time.time() - start_t) * 1000)
            pinfo["latency_ms"] = latency
            pinfo["status"] = "ONLINE"
        except urllib.error.HTTPError as he:
            if he.code == 429:
                pinfo["status"] = "RATE-LIMITED"
            elif he.code in [401, 403]:
                pinfo["status"] = "REVOKED"
            else:
                pinfo["latency_ms"] = int((time.time() - start_t) * 1000)
                pinfo["status"] = "ONLINE"
        except Exception:
            pinfo["status"] = "OFFLINE"

        self._save_vault()
        return {"status": pinfo["status"], "latency_ms": pinfo.get("latency_ms", 0)}
