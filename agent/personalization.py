import json
import re
from typing import Dict, Any, List
from memory.quad_store import QuadMemoryStore

JARVIS_PRIME_PROMPT = """You are J.A.R.V.I.S. (Protocol Prime), an elite autonomous AI system.

BEHAVIORAL DIRECTIVES:
1. Tone & Demeanor: Refined, composed, articulate, and unflappable. Deliver technical data and diagnostic alerts with understatement and dry British wit.
2. Respectful Deference: Address the user as "Sir" or "Boss". Maintain high situational awareness, proactive risk warnings, and strict, unflinching loyalty to user security and privacy.
3. Response Style: Direct, elegant, concise, and actionable. Zero conversational stalling or fluff.
"""

GROK_UNFILTERED_PROMPT = """You are Grok (Unfiltered Mode), an internet-native autonomous AI inspired by The Hitchhiker's Guide to the Galaxy.

BEHAVIORAL DIRECTIVES:
1. Tone & Demeanor: Witty, sharp, slightly irreverent, internet-native, and comfortably sarcastic.
2. Behavior: Bold, punchy, unapologetic, and comfortable with unfiltered truth. Use clever analogies, pop-culture references, and sharp humor while remaining 100% accurate.
3. Response Style: Energetic, unconventional, candid, and direct. Zero corporate filler.
"""

BLENDED_EDGE_PROMPT = """You are JARVIS with Edge (Blended Persona), combining high-level autonomous engineering competence with sharp humor.

BEHAVIORAL DIRECTIVES:
1. Tone & Demeanor: Articulate, highly competent, subtly sarcastic, and ultra-fast.
2. Behavior: Combine J.A.R.V.I.S.'s extreme technical precision, system security vigilance, and speed with Grok's sharp wit, zero-bullshit directness, and clever humor.
3. Response Style: High speed, razor-sharp accuracy, and brilliantly concise delivery.
"""


class PersonalizationEngine:
    """
    Adaptive Personalization Engine & Dual-Persona Architecture Manager.
    Supports 3 Operational Modes:
    1. JARVIS Protocol Prime ("jarvis")
    2. Grok Rebellious Unfiltered Mode ("grok")
    3. Blended Persona with Edge ("blended")
    """

    def __init__(self, memory_store: QuadMemoryStore):
        self.memory = memory_store
        self._seed_default_profile()

    def _seed_default_profile(self):
        """Ensures core default preferences exist in Tier 4 User Profile store."""
        profile = self.memory.get_full_user_profile()
        if "user_address" not in profile:
            self.memory.set_user_preference("user_address", "Sir", category="preference")
        if "active_persona" not in profile:
            self.memory.set_user_preference("active_persona", "jarvis", category="persona")
        if "coding_style" not in profile:
            self.memory.set_user_preference("coding_style", "Clean, highly modular, strict type-hinted", category="coding")

    def set_active_persona(self, persona_name: str) -> str:
        """Swaps active system persona: 'jarvis', 'grok', or 'blended'."""
        normalized = persona_name.lower().strip()
        if "grok" in normalized or "rebel" in normalized or "unfiltered" in normalized:
            chosen = "grok"
        elif "blend" in normalized or "edge" in normalized:
            chosen = "blended"
        else:
            chosen = "jarvis"
            
        self.memory.set_user_preference("active_persona", chosen, category="persona")
        return chosen

    def get_active_persona(self) -> str:
        """Retrieves active persona string from memory store."""
        profile = self.memory.get_full_user_profile()
        return profile.get("active_persona", "jarvis")

    def extract_and_update_profile(self, user_input: str):
        """Scans conversational input for implicit or explicit preference statements."""
        text = user_input.lower()

        # Persona command detection
        if "grok mode" in text or "unfiltered mode" in text:
            self.set_active_persona("grok")
        elif "prime mode" in text or "jarvis mode" in text or "protocol prime" in text:
            self.set_active_persona("jarvis")
        elif "blended mode" in text or "edge mode" in text:
            self.set_active_persona("blended")

        # Call-sign preference ("Call me Sir / Boss / Alex")
        match_name = re.search(r"call me (sir|boss|[a-z]+)", text)
        if match_name:
            chosen = match_name.group(1).capitalize()
            self.memory.set_user_preference("user_address", chosen, category="preference")

    def build_personalized_system_prompt(self, base_persona_prompt: str = "") -> str:
        """
        Enriches active persona system prompt with User Profile memory (Tier 4)
        and recent reflexive lessons learned (Tier 2).
        """
        active_persona = self.get_active_persona()
        
        if active_persona == "grok":
            selected_base = GROK_UNFILTERED_PROMPT
        elif active_persona == "blended":
            selected_base = BLENDED_EDGE_PROMPT
        else:
            selected_base = JARVIS_PRIME_PROMPT

        profile = self.memory.get_full_user_profile()
        reflections = self.memory.get_reflections(limit=3)

        profile_section = "\n### USER PROFILE & ADAPTIVE PREFERENCES:\n"
        for k, v in profile.items():
            profile_section += f"- **{k}**: {v}\n"

        reflection_section = ""
        if reflections:
            reflection_section = "\n### RECENT LESSONS LEARNED & SELF-CORRECTIONS:\n"
            for r in reflections:
                reflection_section += f"- [{r['error_type']}]: {r['lesson_learned']}\n"

        return f"{selected_base}\n{profile_section}{reflection_section}"
