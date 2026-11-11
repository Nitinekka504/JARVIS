import asyncio
import sys
import os
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from config import CONFIG
from memory.quad_store import QuadMemoryStore
from tools.admin_security_tools import AdminSecurityTools
from tools.mcp_client import MCPClientWrapper
from agent.vision_engine import VisionEngine
from agent.task_manager import AsyncTaskManager
from agent.cron_scheduler import JARVISCronScheduler
from agent.orchestrator import JARVISOrchestrator
from audio.voice_engine import VoiceEngine
from dashboard.server import start_dashboard_server, HUB

BANNER = r"""
====================================================================
               _____  ___   ______ _   _ _____ _____ 
              |_   _|/ _ \  | ___ \ | | |_   _/  ___|
                | | / /_\ \ | |_/ / | | | | | \ `--. 
                | | |  _  | |    /| | | | | |  `--. \
            /\__/ / | | | | | |\ \| \_/ /_| |_/\__/ /
            \____/\_| |_|_\_| \_| \___/ \___/\____/  
                                                     
         Autonomous Voice-Driven Multi-Modal AI System
====================================================================
"""

class JARVISSystem:
    """Primary JARVIS Assistant Master System Controller."""

    def __init__(self):
        print(BANNER)
        print("[System Init] Booting JARVIS Core Architecture...")

        # 1. Quad-Tier Memory Initialization
        print("[Memory] Initializing Quad-Tier Memory Store (SQLite + ChromaDB)...")
        self.memory = QuadMemoryStore(
            db_path=CONFIG.get("memory.sqlite_path", "jarvis_memory.db") if CONFIG else "jarvis_memory.db",
            chroma_path=CONFIG.get("memory.chroma_db_path", "./chroma_db") if CONFIG else "./chroma_db"
        )

        # 2. Tools & MCP Integration
        print("[Tools] Registering Admin/Security Auditing & MCP Tools...")
        self.mcp_client = MCPClientWrapper()

        # 3. Vision Engine
        print("[Vision] Initializing Multimodal Screen & Webcam Vision Engine...")
        self.vision = VisionEngine()

        # 4. Asynchronous Task Manager & Worker Pool
        print("[TaskManager] Launching Asynchronous Multi-Tasking Worker Pool...")
        self.task_manager = AsyncTaskManager(
            max_concurrent_workers=CONFIG.get("system.worker_threads", 4) if CONFIG else 4
        )

        # 5. Audio Pipeline & Voice Engine
        print("[Voice] Initializing Audio STT/TTS & Wake-Word Pipeline...")
        self.voice = VoiceEngine(
            wake_word=CONFIG.get("audio.wake_word", "jarvis") if CONFIG else "jarvis",
            stt_provider=CONFIG.get("audio.stt_provider", "whisper") if CONFIG else "whisper",
            tts_provider=CONFIG.get("audio.tts_provider", "console") if CONFIG else "console"
        )

        # 6. Proactive Background Cron Scheduler & Health Watchdog
        print("[Cron] Starting APScheduler System Watchdog & Proactive Debriefs...")
        self.cron = JARVISCronScheduler(
            memory_store=self.memory,
            voice_alert_callback=self.voice.speak
        )

        # 7. LangGraph / ReAct Orchestrator
        print("[Orchestrator] Binding Reasoning Engine, Persona Directives & Routing...")
        self.orchestrator = JARVISOrchestrator(
            memory_store=self.memory,
            task_manager=self.task_manager,
            vision_engine=self.vision,
            mcp_client=self.mcp_client
        )

        self.running = False

    async def _telemetry_broadcaster_loop(self):
        """Periodically streams system health metrics & running tasks to the visual HUD via WebSockets."""
        while self.running:
            try:
                health = AdminSecurityTools.get_system_health()
                tasks = self.task_manager.list_running_tasks()
                
                await HUB.broadcast("telemetry", health)
                await HUB.broadcast("tasks_update", {"tasks": tasks})
            except Exception:
                pass
            await asyncio.sleep(2.0)

    async def start(self):
        """Starts background services, launches web HUD dashboard, and launches conversational event loop."""
        self.running = True

        # Launch FastAPI & WebSocket Dashboard Server on Port 8000
        asyncio.create_task(start_dashboard_server(
            host="127.0.0.1",
            port=8000,
            query_handler=self.orchestrator.process_user_query
        ))
        
        # Connect MCP Client
        await self.mcp_client.connect()

        # Start Cron Scheduler
        self.cron.start()

        # Launch Telemetry Broadcaster
        asyncio.create_task(self._telemetry_broadcaster_loop())

        # Initial Morning System Debrief
        debrief = await self.cron.generate_morning_debrief()
        await self.voice.speak(debrief)

        print("\n" + "="*66)
        print(" [STATUS] JARVIS IS ONLINE AND LISTENING. TYPE OR SPEAK YOUR COMMANDS.")
        print(" Visual HUD Platform running at: http://localhost:8000")
        print(" Commands: 'exit' to shutdown | 'health' for metrics | 'research <topic>'")
        print("="*66 + "\n")

        # Conversational Main Loop
        try:
            while self.running:
                user_input = await self.voice.listen_and_transcribe()
                
                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "shutdown"]:
                    await self.voice.speak("Shutting down core systems. Good day, Sir.")
                    self.running = False
                    break

                # Broadcast voice state: listening / thinking
                await HUB.broadcast("voice_state", {"state": "thinking", "latest_query": user_input})

                # Process query through Orchestrator
                result = await self.orchestrator.process_user_query(user_input)
                
                # Broadcast voice state: speaking
                await HUB.broadcast("voice_state", {"state": "speaking", "latest_query": user_input})

                # Deliver response via Voice/TTS
                await self.voice.speak(result["response"])

                # Broadcast voice state back to idle
                await HUB.broadcast("voice_state", {"state": "idle", "latest_query": user_input})

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[System Shutdown] Interrupted by user.")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Cleanly stops all background threads, MCP processes, and cron jobs."""
        print("[Shutdown] Stopping Cron Scheduler...")
        self.cron.stop()
        print("[Shutdown] Closing MCP Client Connection...")
        await self.mcp_client.close()
        # Always release the camera hardware on shutdown
        if hasattr(self, 'vision') and self.vision:
            print("[Shutdown] Releasing camera hardware...")
            self.vision.release_webcam()
        print("[Shutdown] Core systems offline.")

def main():
    system = JARVISSystem()
    try:
        asyncio.run(system.start())
    except KeyboardInterrupt:
        print("\nShutdown complete.")

if __name__ == "__main__":
    main()
