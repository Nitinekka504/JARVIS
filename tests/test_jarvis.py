import pytest
import asyncio
import os
import shutil
from pathlib import Path

from memory.quad_store import QuadMemoryStore
from tools.admin_security_tools import AdminSecurityTools
from tools.mcp_client import MCPClientWrapper
from agent.vision_engine import VisionEngine
from agent.self_modifier import SelfModificationEngine
from agent.web_learner import AutonomousWebLearner
from agent.personalization import PersonalizationEngine
from agent.task_manager import AsyncTaskManager
from agent.cron_scheduler import JARVISCronScheduler
from agent.orchestrator import JARVISOrchestrator

@pytest.fixture
def temp_memory(tmp_path):
    db_file = tmp_path / "test_memory.db"
    chroma_dir = tmp_path / "test_chroma"
    return QuadMemoryStore(db_path=str(db_file), chroma_path=str(chroma_dir))

def test_quad_memory_store(temp_memory):
    # Tier 1: Short term
    temp_memory.add_short_term(role="user", content="Hello JARVIS")
    history = temp_memory.get_short_term(limit=5)
    assert len(history) == 1
    assert history[0]["content"] == "Hello JARVIS"

    # Tier 2: Reflexive
    temp_memory.log_reflection("TEST_ERR", "Always double check imports")
    reflections = temp_memory.get_reflections()
    assert len(reflections) == 1
    assert reflections[0]["error_type"] == "TEST_ERR"

    # Tier 3: Acquired Knowledge
    doc_id = temp_memory.store_knowledge("Python", "Python is a high-level language.", "docs")
    assert doc_id > 0
    results = temp_memory.search_knowledge("high-level")
    assert len(results) >= 1

    # Tier 4: User Profile
    temp_memory.set_user_preference("user_address", "Boss")
    profile = temp_memory.get_full_user_profile()
    assert profile.get("user_address") == "Boss"

def test_admin_security_tools():
    health = AdminSecurityTools.get_system_health()
    assert "cpu_percent" in health
    assert "ram_percent" in health
    assert "disk_percent" in health

    ports_audit = AdminSecurityTools.audit_open_ports()
    assert "open_ports" in ports_audit
    assert ports_audit["scanned_ports_count"] > 0

def test_self_modification_engine(tmp_path):
    engine = SelfModificationEngine(repo_root=str(tmp_path))
    
    # Create target python file
    sample_file = tmp_path / "sample.py"
    sample_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    # Valid modification
    new_code = "def hello():\n    return 'JARVIS'\n"
    res = engine.stage_and_test_modification("sample.py", new_code)
    assert res["success"] is True
    assert sample_file.read_text(encoding="utf-8") == new_code

    # Invalid AST syntax check
    bad_code = "def broken():\n    return 'JARVIS"
    res_bad = engine.stage_and_test_modification("sample.py", bad_code)
    assert res_bad["success"] is False
    assert "AST" in res_bad["stage"]

def test_web_learner_estimator(temp_memory):
    learner = AutonomousWebLearner(temp_memory)
    urls = ["https://example.com/1", "https://example.com/2"]
    est = learner.estimate_learning_time(urls, depth=1)
    assert est["target_urls_count"] == 2
    assert est["estimated_seconds"] > 0

@pytest.mark.asyncio
async def test_task_manager():
    tm = AsyncTaskManager(max_concurrent_workers=2)
    
    async def sample_job(val):
        await asyncio.sleep(0.1)
        return {"result": val * 2}

    task = await tm.submit_task("Sample Task", sample_job, 21, estimated_duration_seconds=1.0)
    assert "task_id" in task
    assert task["status"] in ["QUEUED_AND_RUNNING", "IN_PROGRESS"]

    # Wait briefly for completion
    await asyncio.sleep(0.3)
    status = tm.get_task_status(task["task_id"])
    assert status["status"] == "COMPLETED"
    assert status["result"] == {"result": 42}

@pytest.mark.asyncio
async def test_orchestrator(temp_memory):
    tm = AsyncTaskManager()
    vision = VisionEngine()
    mcp = MCPClientWrapper()
    
    orchestrator = JARVISOrchestrator(temp_memory, tm, vision, mcp)
    res = await orchestrator.process_user_query("Check system health")
    assert "response" in res
    assert "System Health Analysis" in res["response"]
