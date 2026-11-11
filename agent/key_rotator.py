import json
import asyncio
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple
from tools.api_vault import APIVault
from memory.quad_store import QuadMemoryStore

class KeyRotator:
    """
    Multi-Provider Load Balancer & Zero-Downtime 429 Rate-Limit Failover Rotator.
    Manages high-power open-source cloud model inference (Groq, OpenRouter, Cerebras, GitHub Models).
    Automatically rotates to the next active provider upon receiving a 429 rate-limit error.
    """

    def __init__(self, vault: APIVault, memory: QuadMemoryStore):
        self.vault = vault
        self.memory = memory

    async def query_with_429_failover(
        self,
        prompt: str,
        system_prompt: str = ""
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Executes query against active free API providers.
        If a provider returns 429 or fails, logs reflexive correction and rotates to next provider instantly.
        Returns Tuple[response_text, provider_name_used].
        """
        active_providers = self.vault.get_active_providers()
        if not active_providers:
            return None, None

        for pinfo in active_providers:
            pid = pinfo["provider_id"]
            pname = pinfo["name"]
            api_base = pinfo["api_base"]
            model = pinfo["default_model"]
            key = pinfo["key"]

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4
            }

            req = urllib.request.Request(
                api_base,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                }
            )

            try:
                loop = asyncio.get_running_loop()
                def _do_request():
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return json.loads(resp.read().decode("utf-8"))

                res_json = await loop.run_in_executor(None, _do_request)
                
                # Parse OpenAI-compatible choices array
                choices = res_json.get("choices", [])
                if choices and len(choices) > 0:
                    text = choices[0]["message"]["content"]
                    return text, f"{pname} ({model})"

            except urllib.error.HTTPError as he:
                if he.code == 429:
                    print(f"[KeyRotator] Provider {pname} hit 429 Rate Limit. Initiating failover rotation...")
                    self.vault.mark_rate_limited(pid)
                    self.memory.log_self_correction_tuple(
                        context=f"API_Provider_{pid}",
                        mistake="429 Too Many Requests rate limit exceeded",
                        correct_rule=f"Rotated away from {pid} to secondary active free provider."
                    )
                else:
                    print(f"[KeyRotator] Provider {pname} HTTP Error {he.code}: {he.reason}")
            except Exception as e:
                print(f"[KeyRotator] Provider {pname} execution exception: {e}")

        # If all cloud providers failed or rate-limited
        return None, None
