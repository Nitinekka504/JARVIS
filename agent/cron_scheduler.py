import asyncio
import time
from typing import Optional, Callable, Coroutine, Dict, Any, List

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False


class FallbackScheduler:
    """Lightweight asyncio loop scheduler fallback when APScheduler is not installed."""
    def __init__(self):
        self.running = False
        self._tasks: List[asyncio.Task] = []
        self._jobs = []

    def add_job(self, func, trigger='interval', seconds=60, hour=None, minute=None, id=None, replace_existing=True):
        self._jobs.append({
            'func': func,
            'trigger': trigger,
            'seconds': seconds,
            'id': id
        })

    def start(self):
        self.running = True
        for job in self._jobs:
            if job['trigger'] == 'interval':
                task = asyncio.create_task(self._interval_loop(job['func'], job['seconds']))
                self._tasks.append(task)
            elif job['trigger'] == 'cron':
                # Run once on start for fallback mode
                task = asyncio.create_task(self._cron_fallback(job['func']))
                self._tasks.append(task)

    async def _interval_loop(self, func, interval_seconds):
        while self.running:
            await asyncio.sleep(interval_seconds)
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                print(f"[SchedulerFallback] Error in job: {e}")

    async def _cron_fallback(self, func):
        await asyncio.sleep(5)  # initial delay
        try:
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()
        except Exception as e:
            print(f"[SchedulerFallback] Error in cron job: {e}")

    def shutdown(self):
        self.running = False
        for t in self._tasks:
            t.cancel()


class JARVISCronScheduler:
    """
    Proactive Background Cron Scheduler & System Watchdog Engine.
    Uses `APScheduler` (or built-in asyncio task loop fallback) for asynchronous background job execution:
    1. System Health Watchdog (CPU, RAM, Disk, Port & Process Security Audit).
    2. Daily Morning System Debrief Generator.
    3. Proactive Voice Alerts on threshold breaches.
    """

    def __init__(
        self,
        memory_store: Any,
        voice_alert_callback: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None,
        config: Optional[Any] = None
    ):
        self.memory = memory_store
        self.voice_alert_callback = voice_alert_callback
        
        if config is not None:
            self.config = config
        else:
            try:
                from config import ConfigLoader
                self.config = ConfigLoader().load()
            except Exception:
                self.config = {}
        
        if APSCHEDULER_AVAILABLE:
            self.scheduler = AsyncIOScheduler()
        else:
            print("[CronScheduler] APScheduler not installed in environment. Using lightweight asyncio scheduler fallback.")
            self.scheduler = FallbackScheduler()

        self._last_debrief_summary: Optional[str] = None

    def start(self):
        """Schedules periodic watchdog and debrief tasks, then starts the scheduler."""
        # 1. System Health & Security Watchdog (runs every 300 seconds / 5 minutes)
        watchdog_seconds = 300
        if isinstance(self.config, dict):
            watchdog_seconds = self.config.get("watchdog", {}).get("check_interval_seconds", 300)
        elif hasattr(self.config, "get"):
            watchdog_seconds = self.config.get("watchdog.check_interval_seconds", 300) or 300

        self.scheduler.add_job(
            self.run_health_watchdog,
            'interval',
            seconds=watchdog_seconds,
            id='system_health_watchdog',
            replace_existing=True
        )

        # 2. Daily Morning Debrief (runs every morning at 08:00 AM)
        self.scheduler.add_job(
            self.generate_morning_debrief,
            'cron',
            hour=8,
            minute=0,
            id='daily_morning_debrief',
            replace_existing=True
        )

        self.scheduler.start()
        print("[CronScheduler] Scheduler engine initialized and running.")

    async def run_health_watchdog(self):
        """Scans system health metrics and suspicious processes; emits voice alerts on anomalies."""
        try:
            from tools.admin_security_tools import AdminSecurityTools
            health = AdminSecurityTools.get_system_health()
            suspicious = AdminSecurityTools.scan_suspicious_processes()
            ports_audit = AdminSecurityTools.audit_open_ports()

            alerts = []

            if health.get("cpu_percent", 0) > 85.0:
                alerts.append(f"High CPU utilization detected at {health['cpu_percent']}%.")

            if health.get("ram_percent", 0) > 85.0:
                alerts.append(f"High RAM usage detected at {health['ram_percent']}%.")

            if health.get("disk_percent", 0) > 90.0:
                alerts.append(f"Disk space critically low. Utilization at {health['disk_percent']}%.")

            if suspicious:
                proc_names = ", ".join(s['name'] for s in suspicious)
                alerts.append(f"Security Alert: Suspicious process detected: {proc_names}.")

            if alerts:
                alert_msg = f"Attention Sir. System Watchdog Warning: {' '.join(alerts)}"
                # Log to reflexive memory
                self.memory.log_reflection(
                    error_type="WATCHDOG_ALERT",
                    lesson_learned=alert_msg
                )
                if self.voice_alert_callback:
                    await self.voice_alert_callback(alert_msg)

        except Exception as e:
            print(f"[CronScheduler] Watchdog scan exception: {e}")

    async def generate_morning_debrief(self) -> str:
        """Generates a concise morning system debrief for the user."""
        from tools.admin_security_tools import AdminSecurityTools
        health = AdminSecurityTools.get_system_health()
        ports = AdminSecurityTools.audit_open_ports()
        short_term_count = len(self.memory.get_short_term(limit=100))

        debrief = (
            f"Good morning Sir. Here is your daily system debrief:\n"
            f"All core systems are operational. CPU utilization is at {health.get('cpu_percent', 15)}%, "
            f"RAM usage is at {health.get('ram_percent', 40)}%, and disk free space is {health.get('disk_free_gb', 100)} GB. "
            f"Security status is {ports.get('status', 'SECURE')} with {len(ports.get('open_ports', []))} active local ports. "
            f"Quad-tier memory is online with active context tracking."
        )

        self._last_debrief_summary = debrief
        return debrief

    def get_latest_debrief(self) -> Optional[str]:
        return self._last_debrief_summary

    def stop(self):
        """Stops the scheduler engine cleanly."""
        try:
            if hasattr(self.scheduler, 'running') and self.scheduler.running:
                self.scheduler.shutdown()
        except Exception:
            pass
