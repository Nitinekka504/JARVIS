import os
import re
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ConfigLoader:
    """Loads YAML configuration and substitutes environment variable placeholders (${ENV_VAR})."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._raw_config: Dict[str, Any] = {}
        self.load()

    def _replace_env_vars(self, item: Any) -> Any:
        if isinstance(item, str):
            pattern = re.compile(r"\$\{([^}]+)\}")
            matches = pattern.findall(item)
            for match in matches:
                env_val = os.environ.get(match, "")
                item = item.replace(f"${{{match}}}", env_val)
            return item
        elif isinstance(item, dict):
            return {k: self._replace_env_vars(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._replace_env_vars(i) for i in item]
        return item

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            self._raw_config = self._default_fallback_config()
            return self._raw_config
        
        if YAML_AVAILABLE:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
                self._raw_config = self._replace_env_vars(raw)
                return self._raw_config
            except Exception as e:
                print(f"[ConfigLoader] YAML parse warning: {e}")

        self._raw_config = self._default_fallback_config()
        return self._raw_config

    def _default_fallback_config(self) -> Dict[str, Any]:
        return {
            "system": {"name": "JARVIS", "version": "1.0.0", "worker_threads": 4},
            "models": {"primary_reasoning": "claude-3-5-sonnet-20241022", "vision_model": "gpt-4o"},
            "memory": {"sqlite_path": "jarvis_memory.db", "chroma_db_path": "./chroma_db"},
            "audio": {"wake_word": "jarvis", "stt_provider": "whisper", "tts_provider": "console"}
        }

    def get(self, key_path: str, default: Any = None) -> Any:
        """Access nested keys using dot notation (e.g. 'models.primary_reasoning')."""
        keys = key_path.split(".")
        val = self._raw_config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

# Global config singleton instance
try:
    CONFIG = ConfigLoader()
except Exception:
    CONFIG = None
