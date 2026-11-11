import sqlite3
import threading
import json
import time
import math
from typing import List, Dict, Any, Optional

try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

class QuadMemoryStore:
    """
    Quad-Tier Memory Architecture:
    1. Short-Term Memory: Active conversational sliding buffer.
    2. Reflexive Store: Error logs, stack traces, lessons learned & self-corrections.
    3. Acquired Knowledge Store: Scraped docs, research topics, code snippets (semantic search).
    4. User Profile Store: User preferences, coding habits, daily routines, explicit rules.
    """

    def __init__(self, db_path: str = "jarvis_memory.db", chroma_path: str = "./chroma_db"):
        self.db_path = db_path
        self.chroma_path = chroma_path
        self._lock = threading.Lock()
        
        self._init_sqlite()
        self._init_chroma()

    def _init_sqlite(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Tier 1: Short-Term Memory
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS short_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Tier 2: Reflexive Store
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reflexive_store (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    traceback TEXT,
                    lesson_learned TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Tier 3: Acquired Knowledge Store (SQLite fallback + Metadata)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS acquired_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            
            # Tier 4: User Profile Store
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    updated_at REAL NOT NULL
                )
            """)
            
            conn.commit()
            conn.close()

    def _init_chroma(self):
        self.chroma_client = None
        self.knowledge_collection = None
        if CHROMA_AVAILABLE:
            try:
                # Use default persistent client with lightweight settings
                self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)
                self.knowledge_collection = self.chroma_client.get_or_create_collection(
                    name="acquired_knowledge",
                    embedding_function=None  # Use default embedding or SQLite fallback
                )
            except Exception as e:
                print(f"[QuadMemory] ChromaDB init warning (using SQLite fallback): {e}")

    # --- Tier 1: Short-Term Memory ---
    def add_short_term(self, role: str, content: str):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO short_term_memory (role, content, timestamp) VALUES (?, ?, ?)",
                (role, content, time.time())
            )
            conn.commit()
            conn.close()

    def get_short_term(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, timestamp FROM short_term_memory ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            rows.reverse()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]

    def clear_short_term(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM short_term_memory")
            conn.commit()
            conn.close()

    # --- Tier 2: Reflexive Store ---
    def log_reflection(self, error_type: str, lesson_learned: str, traceback: Optional[str] = None):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reflexive_store (error_type, traceback, lesson_learned, timestamp) VALUES (?, ?, ?, ?)",
                (error_type, traceback or "", lesson_learned, time.time())
            )
            conn.commit()
            conn.close()

    def log_self_correction_tuple(self, context: str, mistake: str, correct_rule: str):
        """Stores structured reflexive self-correction tuple (Context, Mistake, Correct Rule)."""
        formatted_lesson = f"Context: {context} | Mistake: {mistake} | Correct Rule: {correct_rule}"
        self.log_reflection(error_type="SELF_CORRECTION_TUPLE", lesson_learned=formatted_lesson)

    def get_reflections(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, error_type, traceback, lesson_learned, timestamp FROM reflexive_store ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [{
                "id": r[0], "error_type": r[1], "traceback": r[2],
                "lesson_learned": r[3], "timestamp": r[4]
            } for r in rows]

    # --- Tier 3: Acquired Knowledge Store ---
    def store_knowledge(self, topic: str, content: str, source: str = "web_learning") -> int:
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO acquired_knowledge (topic, content, source, timestamp) VALUES (?, ?, ?, ?)",
                (topic, content, source, now)
            )
            doc_id = cursor.lastrowid
            conn.commit()
            conn.close()

        if self.knowledge_collection is not None:
            try:
                self.knowledge_collection.add(
                    documents=[content],
                    metadatas=[{"topic": topic, "source": source, "timestamp": now}],
                    ids=[str(doc_id)]
                )
            except Exception as e:
                print(f"[QuadMemory] ChromaDB indexing error: {e}")

        return doc_id

    def search_knowledge(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self.knowledge_collection is not None:
            try:
                res = self.knowledge_collection.query(query_texts=[query], n_results=top_k)
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                results = []
                for doc, meta in zip(docs, metas):
                    results.append({
                        "topic": meta.get("topic", "General"),
                        "content": doc,
                        "source": meta.get("source", "Unknown"),
                        "timestamp": meta.get("timestamp", 0.0)
                    })
                if results:
                    return results
            except Exception as e:
                print(f"[QuadMemory] ChromaDB search error (falling back to SQLite): {e}")

        # Fallback SQLite keyword search
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT topic, content, source, timestamp FROM acquired_knowledge WHERE content LIKE ? OR topic LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", top_k)
            )
            rows = cursor.fetchall()
            conn.close()
    def get_all_knowledge(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, topic, content, source, timestamp FROM acquired_knowledge ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return [{
                "id": r[0], "topic": r[1], "content": r[2],
                "source": r[3], "timestamp": r[4]
            } for r in rows]

    # --- Tier 4: User Profile Store ---
    def set_user_preference(self, key: str, value: Any, category: str = "preference"):
        str_val = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO user_profile (key, value, category, updated_at) VALUES (?, ?, ?, ?)",
                (key, str_val, category, time.time())
            )
            conn.commit()
            conn.close()

    def get_full_user_profile(self) -> Dict[str, Any]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT key, value, category FROM user_profile")
            rows = cursor.fetchall()
            conn.close()
            
            profile = {}
            for key, val, cat in rows:
                try:
                    parsed = json.loads(val)
                except Exception:
                    parsed = val
                profile[key] = parsed
            return profile
