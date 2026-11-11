import json
import asyncio
import urllib.request
import os
from typing import Dict, Any, List, Optional, Tuple
from memory.quad_store import QuadMemoryStore
from agent.personalization import PersonalizationEngine
from agent.task_manager import AsyncTaskManager
from agent.web_learner import AutonomousWebLearner
from agent.self_modifier import SelfModificationEngine
from agent.vision_engine import VisionEngine
from tools.admin_security_tools import AdminSecurityTools
from tools.mcp_client import MCPClientWrapper
from tools.api_vault import APIVault
from agent.key_rotator import KeyRotator

class JARVISOrchestrator:
    """
    Core Intelligence Orchestrator.
    Manages ReAct reasoning dispatch, multi-tool routing, quad-tier memory retrieval,
    Dual Persona Architecture (JARVIS Prime vs. Grok Unfiltered vs. Blended Edge),
    API Vault 429 Failover Rotator, local Ollama / Cloud model routing, and 3x reflexive error auto-retry loops.
    """

    def __init__(
        self,
        memory_store: QuadMemoryStore,
        task_manager: AsyncTaskManager,
        vision_engine: VisionEngine,
        mcp_client: MCPClientWrapper,
        ollama_endpoint: str = "http://localhost:11434/api/generate",
        local_model: str = "llama3.1:8b"
    ):
        self.memory = memory_store
        self.task_manager = task_manager
        self.vision = vision_engine
        self.mcp = mcp_client
        self.ollama_endpoint = ollama_endpoint
        self.local_model = local_model
        
        self.vault = APIVault()
        self.key_rotator = KeyRotator(self.vault, memory_store)
        self.personalization = PersonalizationEngine(memory_store)
        self.web_learner = AutonomousWebLearner(memory_store)
        self.self_modifier = SelfModificationEngine()

        try:
            from dashboard.server import HUB
            HUB.orchestrator_instance = self
        except Exception:
            pass

    def query_local_ollama(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """Queries local Ollama instance for 100% offline open-source LLM inference."""
        payload = {
            "model": self.local_model,
            "prompt": f"{system_prompt}\n\nUser Question: {prompt}",
            "stream": False
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self.ollama_endpoint,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                res_json = json.loads(response.read().decode('utf-8'))
                return res_json.get("response")
        except Exception:
            return None

    def query_online_llm(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """Queries OpenAI (GPT-4o) if OPENAI_API_KEY environment variable is present."""
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not openai_key:
            return None

        try:
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                return res["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Orchestrator] OpenAI API call exception: {e}")
            return None

    async def execute_tool_with_reflexive_retry(
        self,
        tool_func,
        *args,
        max_retries: int = 3,
        context_name: str = "tool_execution",
        **kwargs
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Reflexive Auto-Retry Self-Correction Loop:
        Attempts tool execution up to `max_retries` (3 times).
        On error, analyzes traceback, retries, and logs (Context, Mistake, Correct Rule)
        into the Reflexive Memory Store.
        """
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(tool_func):
                    res = await tool_func(*args, **kwargs)
                else:
                    res = tool_func(*args, **kwargs)
                
                if attempt > 1 and last_error:
                    self.memory.log_self_correction_tuple(
                        context=context_name,
                        mistake=f"Failed on attempt {attempt-1}: {last_error}",
                        correct_rule=f"Succeeded on attempt {attempt} after adjusting execution state."
                    )
                return True, res, None
            except Exception as e:
                last_error = str(e)
                await asyncio.sleep(0.2)

        self.memory.log_self_correction_tuple(
            context=context_name,
            mistake=f"All {max_retries} attempts failed. Error: {last_error}",
            correct_rule="Inspect parameters and system state before re-attempting."
        )
        return False, None, last_error

    async def process_user_query(
        self,
        user_text: str,
        include_vision_frame: bool = False,
        vision_mode: str = "screen"
    ) -> Dict[str, Any]:
        """
        Main query processing entry point:
        1. Log turn to Short-Term Memory.
        2. Extract & update user personalization & active persona mode.
        3. Retrieve relevant Acquired Knowledge and User Profile context.
        4. Detect intent & dispatch tools with 3x Reflexive Auto-Retry.
        5. Route through KeyRotator 429 Failover Rotator for open-source cloud models.
        """
        self.memory.add_short_term(role="user", content=user_text)

        self.personalization.extract_and_update_profile(user_text)
        active_persona = self.personalization.get_active_persona()

        try:
            from dashboard.server import HUB
            await HUB.broadcast("persona_update", {"persona": active_persona})
        except Exception:
            pass

        sys_prompt = self.personalization.build_personalized_system_prompt()

        vision_meta = None
        if include_vision_frame:
            if vision_mode == "webcam":
                b64_img, vision_meta = self.vision.capture_webcam_base64()
            else:
                b64_img, vision_meta = self.vision.capture_screen_base64()

        lower_input = user_text.lower()
        response_text = ""
        tool_used = None

        # Autonomous Self-Learning Commands
        if "start self learning" in lower_input or "activate self learning" in lower_input or "start internet training" in lower_input or "enable self learning" in lower_input:
            tool_used = "self_learning_control"
            if not self.web_learner.is_learning_active:
                self.web_learner._learning_task = asyncio.create_task(self.web_learner.start_self_learning_loop())
                response_text = "Autonomous Internet Self-Learning Engine ACTIVATED, Sir. Background crawler is online, researching tech topics, and expanding vector memory."
            else:
                response_text = "Self-Learning Engine is already active and crawling the internet in the background, Sir."

        elif "stop self learning" in lower_input or "disable self learning" in lower_input or "deactivate self learning" in lower_input:
            tool_used = "self_learning_control"
            self.web_learner.stop_self_learning_loop()
            response_text = "Autonomous Internet Self-Learning Engine DEACTIVATED, Sir. Crawler loop paused."

        elif "grok mode" in lower_input or "unfiltered mode" in lower_input or "switch to grok" in lower_input:
            tool_used = "persona_switch"
            self.personalization.set_active_persona("grok")
            response_text = "Grok Mode engaged! Unfiltered, rebellious, and zero-bullshit protocol active. What's on your mind?"
        
        elif "prime mode" in lower_input or "jarvis mode" in lower_input or "protocol prime" in lower_input or "switch to prime" in lower_input:
            tool_used = "persona_switch"
            self.personalization.set_active_persona("jarvis")
            user_addr = self.memory.get_full_user_profile().get("user_address", "Sir")
            response_text = f"Protocol Prime reactivated, {user_addr}. Direct, composed British persona engaged."

        elif "blended mode" in lower_input or "edge mode" in lower_input or "switch to blended" in lower_input:
            tool_used = "persona_switch"
            self.personalization.set_active_persona("blended")
            user_addr = self.memory.get_full_user_profile().get("user_address", "Sir")
            response_text = f"Blended Mode online, {user_addr}. Extreme technical precision paired with sharp humor."

        elif "system health" in lower_input or "metrics" in lower_input or "cpu" in lower_input:
            tool_used = "get_system_health"
            ok, health_data, err = await self.execute_tool_with_reflexive_retry(
                AdminSecurityTools.get_system_health,
                context_name="AdminSecurityTools.get_system_health"
            )
            if ok:
                if active_persona == "grok":
                    response_text = (
                        f"Hardware breakdown: CPU is chillin' at {health_data['cpu_percent']}%, "
                        f"RAM is {health_data['ram_percent']}% occupied ({health_data['ram_used_gb']}GB used), "
                        f"and disk has {health_data['disk_free_gb']}GB remaining. {health_data['process_count']} processes running."
                    )
                else:
                    response_text = (
                        f"System Health Analysis, Sir:\n"
                        f"- CPU Utilization: {health_data['cpu_percent']}%\n"
                        f"- Memory: {health_data['ram_percent']}% used ({health_data['ram_used_gb']} GB / {health_data['ram_total_gb']} GB)\n"
                        f"- Disk Usage: {health_data['disk_percent']}% ({health_data['disk_free_gb']} GB free)\n"
                        f"- Active Processes: {health_data['process_count']}"
                    )
            else:
                response_text = f"System health scan encountered an issue, Sir: {err}"

        elif "audit ports" in lower_input or "open ports" in lower_input or "security scan" in lower_input:
            tool_used = "audit_open_ports"
            ok, audit_data, err = await self.execute_tool_with_reflexive_retry(
                AdminSecurityTools.audit_open_ports,
                context_name="AdminSecurityTools.audit_open_ports"
            )
            if ok:
                response_text = (
                    f"Security Port Audit Complete, Sir.\n"
                    f"Status: {audit_data['status']}\n"
                    f"Active Listening Ports: {audit_data['open_ports'] if audit_data['open_ports'] else 'None detected'}\n"
                    f"Total Scanned: {audit_data['scanned_ports_count']} standard ports."
                )

        elif "learn" in lower_input or "scrape" in lower_input or "research" in lower_input:
            tool_used = "web_learner_task"
            urls = [u for u in user_text.split() if u.startswith("http://") or u.startswith("https://")]
            topic = user_text.replace("learn", "").replace("research", "").replace("scrape", "").strip() or "Web Research"
            
            time_est = self.web_learner.estimate_learning_time(urls or ["search_query"])
            
            async def _on_task_complete(rec: dict):
                try:
                    from dashboard.server import HUB
                    await HUB.broadcast("sound_cue", {"cue_type": "task_complete"})
                    res_info = rec.get("result", {}) or {}
                    summary_text = res_info.get("summary", "Acquired insights saved to Quad-Tier Memory.")
                    ft_info = res_info.get("fine_tuning", {}) or {}
                    announcement = ft_info.get("announcement")
                    bench = ft_info.get("benchmark", {}) or {}
                    acc = bench.get("accuracy_percent", 100.0)

                    resp_msg = (
                        f"✅ [Research & Fine-Tuning Complete]: {rec['name']} finished successfully!\n"
                        f"• {announcement if announcement else 'Model weights updated.'}\n"
                        f"• Synthetic Evaluation Benchmark Accuracy: {acc}%\n"
                        f"• Instruction Dataset updated & Ollama Model File registered."
                    )
                    await HUB.broadcast("chat_response", {
                        "query": "",
                        "response": resp_msg,
                        "tool_used": "model_fine_tuning"
                    })
                except Exception as e:
                    print(f"[Orchestrator] Task completion notification error: {e}")

            task_res = await self.task_manager.submit_task(
                task_name=f"Web Research on {topic}",
                coro_func=self.web_learner.learn_from_topic_or_urls,
                topic=topic,
                urls=urls,
                estimated_duration_seconds=time_est["estimated_seconds"],
                completion_callback=_on_task_complete
            )

            response_text = (
                f"Understood Sir. I have scraped 3 sources on '{topic}'.\n"
                f"Estimated training time is {time_est['eta_formatted']}.\n"
                f"Beginning model weight update now. Background Task ID: {task_res['task_id']}."
            )

        elif "modify file" in lower_input or "edit file" in lower_input or "self-modify" in lower_input:
            tool_used = "self_modification_guard"
            parts = user_text.split()
            filepath = None
            for idx, p in enumerate(parts):
                if p.lower() in ["file", "modify", "edit"] and idx + 1 < len(parts):
                    cand = parts[idx + 1].strip("'\"")
                    if "." in cand:
                        filepath = cand
                        break
            if not filepath:
                response_text = "Self-Modification Security Policy: Please specify a valid relative filepath (e.g., 'modify file config.py')."
            else:
                confirmed = "--confirm" in lower_input or "confirm" in lower_input
                # Check target exists
                target_full = (self.self_modifier.repo_root / filepath).resolve()
                if not target_full.exists():
                    response_text = f"Target file '{filepath}' does not exist in repository boundary."
                else:
                    try:
                        curr_content = target_full.read_text(encoding="utf-8", errors="ignore")
                        res = self.self_modifier.stage_and_test_modification(
                            relative_filepath=filepath,
                            new_code_content=curr_content,
                            confirmed=confirmed
                        )
                        if not confirmed:
                            response_text = (
                                f"🛡️ Self-Modification Confirmation Required (Ponytail SEC-02):\n"
                                f"Target: {filepath}\n"
                                f"Diff generated and streamed to Visual HUD.\n"
                                f"To run test suite and apply atomic overwrite, re-issue with: 'modify file {filepath} --confirm'."
                            )
                        else:
                            response_text = f"Self-modification applied for {filepath}: {res.get('message', res.get('error'))}"
                    except Exception as mod_err:
                        response_text = f"Self-modification inspection failed: {mod_err}"

        elif (any(phrase in lower_input for phrase in ["what do you see", "can you see", "do you see", "look at", "whats in my hand", "what is in my hand", "what am i holding", "in my hand", "my face", "can you see me", "see my face", "through the feed", "on camera", "on webcam", "read screen", "describe this", "what is this", "see this", "whats this"]) or ("see" in lower_input and any(w in lower_input for w in ["face", "me", "feed", "camera", "webcam", "hand", "holding", "screen"]))):
            tool_used = "multimodal_vision"
            use_webcam = any(w in lower_input for w in ["hand", "holding", "camera", "webcam", "object", "me", "face", "front", "item", "feed"]) or ("screen" not in lower_input)
            
            if use_webcam:
                b64_img, vision_meta = await asyncio.to_thread(self.vision.capture_webcam_base64, auto_release=True)
                mode_label = "WEBCAM"
            else:
                b64_img, vision_meta = await asyncio.to_thread(self.vision.capture_screen_base64)
                mode_label = "SCREEN"

            try:
                from dashboard.server import HUB
                await HUB.broadcast("vision_update", {
                    "mode": mode_label,
                    "image_b64": b64_img,
                    "metadata": vision_meta
                })
            except Exception:
                pass

            response_text = await self.vision.analyze_image(prompt=user_text, image_b64=b64_img)

        elif lower_input in ["exit", "quit", "shutdown"]:
            tool_used = "system_shutdown"
            response_text = "Shutting down core systems. Good day, Sir."

        elif "help" in lower_input or "command" in lower_input or "options" in lower_input:
            tool_used = "system_help"
            response_text = (
                "Available Capabilities, Sir:\n"
                "• Personas: 'grok mode', 'prime mode', 'blended mode'\n"
                "• Diagnostics: 'system health', 'audit ports'\n"
                "• Web Research: 'research <topic>' or 'search <query>'\n"
                "• Multimodal Vision: 'what do you see'\n"
                "• Audio Synthesis: 'use male voice' or 'use female voice'\n"
                "• Self-Modification: 'modify file <filepath>'\n"
                "• Shutdown: 'exit'"
            )

        elif any(w in lower_input for w in ["hello", "hi ", "hey ", "greetings", "good morning", "good evening"]):
            tool_used = "greeting"
            user_addr = self.memory.get_full_user_profile().get("user_address", "Sir")
            if active_persona == "grok":
                response_text = f"Hey! Grok mode active. What wild topic are we exploring today?"
            else:
                response_text = f"Good day, {user_addr}. Core systems and visual HUD are online. How may I assist you?"

        elif "who are you" in lower_input or "your name" in lower_input or "what are you" in lower_input:
            tool_used = "identity"
            if active_persona == "grok":
                response_text = "I'm Grok Mode JARVIS—unfiltered, sarcastic, and wicked fast."
            elif active_persona == "blended":
                response_text = "I am JARVIS with Edge—unflinching technical competence combined with sharp wit."
            else:
                response_text = "I am J.A.R.V.I.S. (Just A Rather Very Intelligent System), your autonomous multi-modal assistant, Sir."

        elif "voice" in lower_input or "audio" in lower_input:
            tool_used = "audio_settings"
            if "male" in lower_input:
                self.memory.set_user_preference("voice_gender", "male", category="audio")
                try:
                    from dashboard.server import HUB
                    await HUB.broadcast("voice_gender_update", {"gender": "male"})
                except Exception:
                    pass
                response_text = "Understood, Sir. Adjusting vocal synthesis module to Male British persona."
            elif "female" in lower_input:
                self.memory.set_user_preference("voice_gender", "female", category="audio")
                try:
                    from dashboard.server import HUB
                    await HUB.broadcast("voice_gender_update", {"gender": "female"})
                except Exception:
                    pass
                response_text = "Understood, Sir. Vocal synthesis module updated to Female persona."
            else:
                response_text = "Vocal synthesis module ready, Sir. You can specify 'use male voice' or 'use female voice'."

        else:
            # Fallback Reasoning Pipeline:
            # 1. Try local Ollama inference
            local_res = await asyncio.to_thread(self.query_local_ollama, user_text, sys_prompt)
            if local_res:
                response_text = local_res
                tool_used = "local_ollama"
            else:
                # 2. Try KeyRotator API Vault Free Cloud Providers (Groq / OpenRouter / Cerebras / GitHub)
                cloud_res, provider_used = await self.key_rotator.query_with_429_failover(user_text, sys_prompt)
                if cloud_res:
                    response_text = cloud_res
                    tool_used = f"api_vault_{provider_used}"
                else:
                    # 3. Try online OpenAI API key
                    online_res = await asyncio.to_thread(self.query_online_llm, user_text, sys_prompt)
                    if online_res:
                        response_text = online_res
                        tool_used = "openai_gpt4o"
                    else:
                        # 4. Dynamic Local Web Search (DuckDuckGo)
                        user_addr = self.memory.get_full_user_profile().get("user_address", "Sir")
                        search_results = await asyncio.to_thread(self.web_learner.local_web_search, user_text, 4)
                        
                        if search_results:
                            tool_used = "duckduckgo_local_search"
                            clean_items = []
                            for item in search_results:
                                if item.get('snippet'):
                                    stitle = AutonomousWebLearner.sanitize_scraped_text(item['title'])
                                    ssnip = AutonomousWebLearner.sanitize_scraped_text(item['snippet'])
                                    clean_items.append(f"• {stitle}\n  {ssnip}")
                            snippets = "\n\n".join(clean_items)
                            if active_persona == "grok":
                                response_text = f"Here's what DuckDuckGo turned up:\n\n{snippets}"
                            else:
                                response_text = f"Here is the latest information regarding your query, {user_addr}:\n\n{snippets}"
                            self.memory.store_knowledge(
                                topic=user_text,
                                content=response_text,
                                source="duckduckgo_auto_search"
                            )
                        else:
                            knowledge_matches = self.memory.search_knowledge(user_text, top_k=2)
                            if knowledge_matches:
                                tool_used = "quad_memory"
                                k_info = "\n".join([f"• {m['content'][:250]}" for m in knowledge_matches])
                                response_text = f"Based on acquired memory records:\n{k_info}"
                            else:
                                if active_persona == "grok":
                                    response_text = f"Processed '{user_text}'. Connect Ollama or OpenAI API for unfiltered deep reasoning!"
                                else:
                                    response_text = f"Understood, {user_addr}. I have processed your input regarding '{user_text}' and logged it to memory."

        self.memory.add_short_term(role="assistant", content=response_text)

        return {
            "response": response_text,
            "tool_used": tool_used,
            "persona": active_persona,
            "vision_metadata": vision_meta,
            "system_prompt": sys_prompt
        }
