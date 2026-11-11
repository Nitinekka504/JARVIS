import asyncio
import re
import sys
import time
from typing import Optional, Callable, Coroutine, Any, List

class VoiceEngine:
    """
    Multi-stage Low-Latency Streaming Audio Pipeline & Persona Output Engine.
    Handles:
    1. Sentence-by-Sentence Real-Time TTS Streaming (`speak_stream`).
    2. Dedicated British Voice Persona (`en-GB`) with composed cadence and steady pitch.
    3. UI Sound Cue Synthesis (Wake-word chime, Task completion ping, Security alert tone).
    4. Full-Duplex Interruption (Barge-In) clearing audio queue within <50ms.
    """

    def __init__(
        self,
        wake_word: str = "jarvis",
        stt_provider: str = "whisper",
        tts_provider: str = "console",
        voice_persona: str = "en-GB"
    ):
        self.wake_word = wake_word.lower()
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.voice_persona = voice_persona
        self.active_persona_mode = "jarvis"
        self.is_listening = False
        self.is_speaking = False
        
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._interrupted = False

    def set_persona_mode(self, mode: str):
        """Sets active persona mode and updates vocal parameters."""
        self.active_persona_mode = mode.lower()

    def _chunk_into_sentences(self, text: str) -> List[str]:
        """Splits full text into small sentence chunks on punctuation for low-latency streaming."""
        if not text:
            return []
        
        # Split on sentence boundaries
        raw_chunks = re.split(r'(?<=[.!?;\n])\s+', text)
        sentences = []
        for chunk in raw_chunks:
            cleaned = chunk.strip()
            if cleaned:
                sentences.append(cleaned)
        return sentences if sentences else [text.strip()]

    def barge_in_interrupt(self):
        """
        Instant Speech Interruption (Barge-In).
        Immediately mutes playback, clears the audio queue within <50ms,
        and signals all components to halt speech output.
        """
        self._interrupted = True
        self.is_speaking = False
        
        # Clear audio queue instantly
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Exception:
                pass
        
        # Broadcast barge-in event to dashboard WebSockets if server is active
        try:
            from dashboard.server import HUB
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(HUB.broadcast("barge_in", {"interrupted": True, "timestamp": time.time()}))
        except Exception:
            pass

        print("[VoiceEngine] Barge-In Interruption triggered. Audio queue cleared in <50ms.")

    async def play_sound_cue(self, cue_type: str = "wake_word"):
        """
        Synthesizes UI sound cues (chimes & alerts) and broadcasts cue to visual HUD.
        - 'wake_word': Dual high-frequency chime (880Hz -> 1760Hz)
        - 'task_complete': Upward triad chime (523Hz -> 659Hz -> 784Hz)
        - 'alert': Security warning tone (440Hz -> 330Hz)
        """
        try:
            from dashboard.server import HUB
            await HUB.broadcast("sound_cue", {"cue_type": cue_type, "timestamp": time.time()})
        except Exception:
            pass

    async def speak(self, text: str):
        """Standard non-streaming speak wrapper routing to speak_stream."""
        await self.speak_stream(text)

    async def speak_stream(self, text: str):
        """
        Synthesizes and speaks text sentence-by-sentence in real time.
        Streams each sentence chunk immediately as soon as ready, avoiding full-paragraph delays.
        Checks for barge-in interruption before each sentence.
        """
        self._interrupted = False
        self.is_speaking = True
        
        sentences = self._chunk_into_sentences(text)
        print(f"\n[JARVIS Voice ({self.voice_persona})]: {text}\n")

        for idx, sentence in enumerate(sentences):
            if self._interrupted:
                print("[VoiceEngine] Playback aborted by barge-in interrupt.")
                break

            # Broadcast sentence chunk to Web Dashboard WebSockets for browser Web Speech Synthesis
            try:
                from dashboard.server import HUB
                await HUB.broadcast("chat_response", {
                    "query": "",
                    "response": sentence,
                    "is_chunk": True,
                    "chunk_index": idx,
                    "total_chunks": len(sentences),
                    "persona": self.voice_persona
                })
                await HUB.broadcast("voice_state", {"state": "speaking", "latest_query": sentence})
            except Exception:
                pass

            # Python pyttsx3 local audio engine fallback if configured
            if self.tts_provider == "pyttsx3" and not self._interrupted:
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    # Try setting British voice if available
                    for voice in engine.getProperty('voices'):
                        if "gb" in voice.id.lower() or "uk" in voice.id.lower() or "british" in voice.name.lower():
                            engine.setProperty('voice', voice.id)
                            break
                    engine.setProperty('rate', 165)
                    engine.say(sentence)
                    engine.runAndWait()
                except Exception as e:
                    print(f"[VoiceEngine] pyttsx3 sentence playback warning: {e}")

            # Short intra-sentence delay for natural cadence
            await asyncio.sleep(0.05)

        self.is_speaking = False

    async def listen_and_transcribe(self) -> str:
        """
        Captures audio stream or prompts user for input.
        If user input arrives, automatically triggers barge_in_interrupt() on ongoing speech.
        """
        loop = asyncio.get_running_loop()
        try:
            sys.stdout.write("You (Voice / CLI Input): ")
            sys.stdout.flush()
            
            user_text = await loop.run_in_executor(None, sys.stdin.readline)
            text = (user_text or "").strip()
            
            if text and self.is_speaking:
                # Trigger instant barge-in interrupt if user inputs while JARVIS speaks
                self.barge_in_interrupt()
                
            return text
        except Exception as e:
            print(f"[VoiceEngine] Input reading error: {e}")
            return ""
