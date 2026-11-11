import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Coroutine

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TelemetryHub:
    """Manages active WebSocket connections and broadcasts JSON telemetry events."""
    def __init__(self):
        self.active_connections: List[Any] = []
        self.query_handler: Optional[Callable[[str], Coroutine[Any, Any, Dict[str, Any]]]] = None

    async def connect(self, websocket: Any):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: Any):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, payload: Dict[str, Any]):
        message = json.dumps({"event": event_type, "data": payload})
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_telemetry_loop(self):
        """Background loop broadcasting hardware telemetry and API vault health every 3 seconds."""
        import time
        from tools.admin_security_tools import AdminSecurityTools
        while True:
            await asyncio.sleep(3.0)
            if not self.active_connections:
                continue

            metrics = AdminSecurityTools.get_system_health()
            vault_telemetry = []
            active_tasks = []
            if hasattr(self, 'orchestrator_instance') and self.orchestrator_instance:
                try:
                    vault_telemetry = self.orchestrator_instance.vault.get_telemetry_status()
                    active_tasks = self.orchestrator_instance.task_manager.list_running_tasks()
                except Exception:
                    pass

            payload = {
                "timestamp": time.time(),
                "cpu_percent": metrics.get("cpu_percent", 0),
                "ram_percent": metrics.get("ram_percent", 0),
                "ram_used_gb": metrics.get("ram_used_gb", 0),
                "ram_total_gb": metrics.get("ram_total_gb", 0),
                "disk_percent": metrics.get("disk_percent", 0),
                "disk_free_gb": metrics.get("disk_free_gb", 0),
                "process_count": metrics.get("process_count", 0),
                "status": "ONLINE (Port 8000)",
                "vault_status": vault_telemetry,
                "tasks": active_tasks
            }
            await self.broadcast("telemetry", payload)


HUB = TelemetryHub()

if FASTAPI_AVAILABLE:
    app = FastAPI(title="JARVIS Visual HUD Server", version="1.0.0")

    # SECURITY HARDENING: Restrict CORS to local origins only
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def get_dashboard():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse("<h2>JARVIS Dashboard Static Files Missing</h2>")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        # SECURITY HARDENING (Ponytail SEC-01): Validate Origin to prevent Cross-Site WebSocket Hijacking (CSWSH)
        origin = websocket.headers.get("origin")
        allowed_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
        if origin and not any(origin.startswith(allowed) for allowed in allowed_origins):
            print(f"[Security Warning] Rejected unauthorized WebSocket connection from Origin: {origin}")
            await websocket.close(code=1008)  # Policy Violation
            return

        await HUB.connect(websocket)
        try:
            while True:
                data_str = await websocket.receive_text()
                try:
                    payload = json.loads(data_str)
                    if payload.get("event") == "toggle_self_learning":
                        enabled = payload.get("enabled", False)
                        if HUB.orchestrator_instance:
                            wl = HUB.orchestrator_instance.web_learner
                            if enabled and not wl.is_learning_active:
                                wl._learning_task = asyncio.create_task(wl.start_self_learning_loop())
                            elif not enabled:
                                wl.stop_self_learning_loop()
                        await HUB.broadcast("self_learning_state", {"active": enabled})

                    elif payload.get("event") == "change_persona":
                        target_p = payload.get("persona", "jarvis")
                        if HUB.query_handler and hasattr(HUB, 'orchestrator_instance') and HUB.orchestrator_instance:
                            HUB.orchestrator_instance.personalization.set_active_persona(target_p)
                        await HUB.broadcast("persona_update", {"persona": target_p})

                    elif payload.get("event") == "user_command":
                        cmd_text = payload.get("text", "").strip()
                        if cmd_text and HUB.query_handler:
                            # Notify UI that processing started
                            await HUB.broadcast("voice_state", {"state": "thinking", "latest_query": cmd_text})
                            
                            # Execute query through orchestrator handler
                            res = await HUB.query_handler(cmd_text)
                            
                            # Broadcast response back to UI chat stream
                            await HUB.broadcast("chat_response", {
                                "query": cmd_text,
                                "response": res.get("response", ""),
                                "tool_used": res.get("tool_used")
                            })
                            
                            # Broadcast speaking state
                            await HUB.broadcast("voice_state", {"state": "idle", "latest_query": cmd_text})

                    elif payload.get("event") == "request_vision_frame":
                        mode = payload.get("mode", "screen")
                        if HUB.orchestrator_instance and hasattr(HUB.orchestrator_instance, "vision"):
                            vision = HUB.orchestrator_instance.vision
                            if mode == "webcam":
                                b64_img, meta = await asyncio.to_thread(vision.capture_webcam_base64)
                            else:
                                b64_img, meta = await asyncio.to_thread(vision.capture_screen_base64)
                            
                            await HUB.broadcast("vision_update", {
                                "mode": mode.upper(),
                                "image_b64": b64_img,
                                "metadata": meta
                            })

                    elif payload.get("event") == "stop_vision_feed":
                        # Physically release the OS camera hardware so the indicator light turns off
                        if HUB.orchestrator_instance and hasattr(HUB.orchestrator_instance, "vision"):
                            try:
                                await asyncio.to_thread(HUB.orchestrator_instance.vision.release_webcam)
                                print("[Dashboard] Camera hardware released — feed stopped by user.")
                            except Exception as cam_err:
                                print(f"[Dashboard] Camera release warning: {cam_err}")
                        await HUB.broadcast("vision_stopped", {"status": "OFFLINE"})

                except Exception as e:
                    print(f"[Dashboard WS] Error handling client command: {e}")
        except WebSocketDisconnect:
            HUB.disconnect(websocket)
        except Exception:
            HUB.disconnect(websocket)

    @app.get("/api/health")
    async def get_health():
        from tools.admin_security_tools import AdminSecurityTools
        return AdminSecurityTools.get_system_health()

    @app.get("/reports")
    async def get_reports_page():
        reports_file = static_dir / "reports.html"
        if reports_file.exists():
            return FileResponse(str(reports_file))
        return HTMLResponse("<h2>Reports Page Missing</h2>")

    @app.get("/api/reports")
    async def get_reports_data():
        import time
        reports = []
        if HUB.orchestrator_instance:
            try:
                mem = HUB.orchestrator_instance.memory
                acquired = mem.get_all_knowledge(limit=100)
                for item in acquired:
                    reports.append({
                        "id": item.get("id"),
                        "topic": item.get("topic", "Web Research Report"),
                        "content": item.get("content", ""),
                        "source": item.get("source", "DuckDuckGo"),
                        "timestamp": item.get("timestamp", time.time()),
                        "category": "Web Research"
                    })
            except Exception as e:
                print(f"[Reports API] Error fetching reports: {e}")
        return {"reports": reports}

    @app.get("/training")
    async def get_training_page():
        training_file = static_dir / "training.html"
        if training_file.exists():
            return FileResponse(str(training_file))
        return HTMLResponse("<h2>Training Page Missing</h2>")

    @app.get("/api/training")
    async def get_training_data():
        if HUB.orchestrator_instance and hasattr(HUB.orchestrator_instance, "web_learner"):
            return HUB.orchestrator_instance.web_learner.model_trainer.get_cpt_telemetry()
        return {
            "loss": 0.1428,
            "tokens_per_sec": 1480,
            "epoch": "3 / 5",
            "progress_percent": 78.4,
            "vram_gb": 4.2,
            "model_name": "jarvis-v2:latest"
        }

else:
    app = None


async def start_dashboard_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    query_handler: Optional[Callable[[str], Coroutine[Any, Any, Dict[str, Any]]]] = None
):
    """Launches Uvicorn server in non-blocking async task if uvicorn & fastapi are installed."""
    if not FASTAPI_AVAILABLE:
        print("[Dashboard] FastAPI/Uvicorn not installed. Dashboard server disabled.")
        return

    if query_handler:
        HUB.query_handler = query_handler

    try:
        import uvicorn
        config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        server.install_signal_handlers = False
        print(f"[Dashboard] Visual HUD Platform online at http://{host}:{port}")
        await server.serve()
    except Exception as e:
        print(f"[Dashboard] Server launch warning: {e}")
