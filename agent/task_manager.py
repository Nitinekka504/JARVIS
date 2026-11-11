import asyncio
import uuid
import time
from typing import Dict, Any, Callable, Coroutine, Optional, List

class AsyncTaskManager:
    """
    Asynchronous Multi-Tasking & Worker Pool Manager.
    Offloads long-running heavy workloads (web research, vector indexing, self-modifications)
    to background tasks without blocking the main voice conversational loop.
    
    Provides:
    - Task ID generation and progress tracking.
    - Time-to-completion (ETA) estimates.
    - Non-blocking execution release.
    - Async completion callbacks & WebSocket broadcast updates.
    """

    def __init__(self, max_concurrent_workers: int = 4):
        self.max_workers = max_concurrent_workers
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.completed_tasks: Dict[str, Dict[str, Any]] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent_workers)

    async def _notify_hub(self):
        """Broadcasts active tasks to Web Dashboard WebSockets."""
        try:
            from dashboard.server import HUB
            await HUB.broadcast("tasks_update", {"tasks": self.list_running_tasks()})
        except Exception:
            pass

    async def submit_task(
        self,
        task_name: str,
        coro_func: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        *args,
        estimated_duration_seconds: float = 5.0,
        completion_callback: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Submits an asynchronous background task.
        Returns task submission status, Task ID, and estimated duration immediately.
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        eta_timestamp = start_time + estimated_duration_seconds

        task_record = {
            "task_id": task_id,
            "name": task_name,
            "status": "RUNNING",
            "progress_percent": 15.0,
            "submitted_at": start_time,
            "estimated_seconds": estimated_duration_seconds,
            "eta_timestamp": eta_timestamp,
            "result": None,
            "error": None
        }

        self.active_tasks[task_id] = task_record

        # Broadcast active task update immediately
        await self._notify_hub()

        # Schedule background execution wrapper task
        asyncio.create_task(
            self._worker_wrapper(task_id, coro_func, args, kwargs, completion_callback)
        )

        minutes = int(estimated_duration_seconds // 60)
        seconds = int(estimated_duration_seconds % 60)
        eta_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        return {
            "task_id": task_id,
            "task_name": task_name,
            "status": "QUEUED_AND_RUNNING",
            "estimated_duration": eta_str,
            "message": f"Task '{task_name}' launched in background (ID: {task_id}). Estimated completion time: {eta_str}."
        }

    async def _worker_wrapper(
        self,
        task_id: str,
        coro_func: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        args: tuple,
        kwargs: dict,
        completion_callback: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]]
    ):
        async with self.semaphore:
            try:
                task_rec = self.active_tasks[task_id]
                task_rec["status"] = "IN_PROGRESS"
                task_rec["progress_percent"] = 50.0
                await self._notify_hub()

                result = await coro_func(*args, **kwargs)

                task_rec["status"] = "COMPLETED"
                task_rec["progress_percent"] = 100.0
                task_rec["completed_at"] = time.time()
                task_rec["result"] = result

                self.completed_tasks[task_id] = task_rec
                del self.active_tasks[task_id]

                await self._notify_hub()

                if completion_callback:
                    await completion_callback(task_rec)

            except Exception as e:
                if task_id in self.active_tasks:
                    task_rec = self.active_tasks[task_id]
                    task_rec["status"] = "FAILED"
                    task_rec["error"] = str(e)
                    task_rec["failed_at"] = time.time()
                    self.completed_tasks[task_id] = task_rec
                    del self.active_tasks[task_id]
                    await self._notify_hub()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Queries current status and progress of a task by ID."""
        if task_id in self.active_tasks:
            rec = self.active_tasks[task_id]
            remaining = max(0.0, rec["eta_timestamp"] - time.time())
            return {
                "task_id": task_id,
                "status": rec["status"],
                "name": rec["name"],
                "progress_percent": rec["progress_percent"],
                "remaining_seconds": round(remaining, 1)
            }
        elif task_id in self.completed_tasks:
            rec = self.completed_tasks[task_id]
            return {
                "task_id": task_id,
                "status": rec["status"],
                "name": rec["name"],
                "result": rec.get("result"),
                "error": rec.get("error")
            }
        return {"status": "NOT_FOUND", "message": f"No task found with ID {task_id}"}

    def list_running_tasks(self) -> List[Dict[str, Any]]:
        """Lists all active background tasks."""
        return [
            {
                "task_id": tid,
                "name": t["name"],
                "status": t["status"],
                "progress": t["progress_percent"],
                "elapsed": round(time.time() - t["submitted_at"], 1)
            }
            for tid, t in self.active_tasks.items()
        ]
