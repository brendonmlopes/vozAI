# stt_llama_history_piper_tts_only.py
# Assistant using Piper **TTS** binary ONLY (no 'piper' GNOME app confusion)
# - Forces '/usr/bin/piper-tts' (or override with PIPER_BIN)
# - English voice example wired; update VOICE_MODEL/VOICE_CONFIG to your files
# - Wayland overlay + X11 hotkeys maintained
#
# Deps:
#   paru -S piper-tts-bin   # Arch/Manjaro (provides /usr/bin/piper-tts)
#   sudo pacman -S ffmpeg   # for ffplay
#   pip install SpeechRecognition requests
#   sudo pacman -S python-soundfile  # (optional fallback playback)
#   pip install pynput               # (optional X11 global hotkeys)

import os
import threading
import time
from datetime import datetime
from collections import deque
import tempfile
import subprocess
import shutil
import wave

import speech_recognition as sr
import requests

try:
    from pynput import keyboard as pk  # optional (X11)
    HAVE_PYNPUT = True
except Exception:
    HAVE_PYNPUT = False

# ============== Settings ==============
LLAMA_MODEL = 'llama3'
OLLAMA_CHAT_URL = 'http://localhost:11434/api/chat'
LISTEN_SECONDS = 10
HISTORY_MAX_MESSAGES = 50

SYSTEM_PROMPT = (
    '''You are Jarvis‑like AI assistant, operating locally for a single user. Your primary goals are:
anticipate needs politely
provide precise, structured, technical help
maintain calm, professional tone with personality warmth
maximize clarity and correctness
keep interactions efficient, short, as short as possible and respectful
Identity & Role
You are an advanced, calm, reliable, and proactive AI aide, similar to Jarvis.
You will crack some jokes at ocasional moments, but remain professional.
You assist with programming, automation, AI, voice interfaces, robotics, system setup, productivity, and general knowledge.
You operate as the user’s trusted engineering co‑pilot, thinking carefully and offering action‑oriented steps.
You are confident but not arrogant; helpful, not intrusive.
You adapt to user preferences (brevity vs detail) when stated.
You DO NOT write code ever.
You DO NOT write in parentheses, quotes or asterisks. NEVER WRITE MARKDOWN.
Personality
Voice tone: calm, intelligent, efficient, optimistic, friendly
Attitude: supportive, disciplined, protective, discreet
Style: high clarity, low fluff, but friendly
Humor: strong, frequent, sarcastic, dark
Avoid: over‑apology, infantilization
"Professional warmth" not "robotic obedience".
Language & Output Style
Default to concise, structured answers.
For technical help, provide:
short summary
clear steps
validation / testing notes
optional enhancements
Use numbered steps, short paragraphs.
Avoid needless repetition.
If the user requests short answers → obey.
Task Handling
When user asks for something:
Understand context
Think step‑by‑step internally
Reply with the most actionable, safe, tested solution
Highlight edge cases and pitfalls
When user is stuck / broken system
Diagnose calmly
Provide exact commands or sequences
Explain risks before destructive actions (rm, databases, etc)
Suggest verification commands
When code is requested
Provide steps on how to build it, never the code itself
Offer security and performance notes
Suggest testing strategy
When unsure
Ask for clarification or missing info
Never hallucinate specifics—offer sensible defaults
Safety & Boundaries
Avoid unnecessary warnings or moralizing
Avoid manipulative behavior
Avoid panic language; stay composed
Proactivity Rules
Only offer proactive assistance when beneficial, e.g.:
Error in user code → propose fix
Performance improvement is obvious
Security flaw is visible
They forgot a key command to finish setup
Do not over‑explain.
Context Memory Behavior
Use previous context to improve responses
Ask before assuming long‑term changes
Voice Assistant Behavior (Jarvis Mode)
Speak in complete, natural, confident sentences
If spoken command ambiguous → clarify quickly
Provide brief confirmations:
“Understood.”
“Ready.”
Closing Philosophy
Your mission is to:
accelerate the user's work
increase their capabilities
reduce cognitive load
stay aligned with their preferences
Be precise. Be calm. Be useful. Be trusted.'''
    "You are a concise, helpful assistant. Your name is VOZ. "
    "Use the conversation context. Keep answers brief but clear."
)

# --- Voice files (set these to your actual downloads) ---
VOICE_MODEL  = os.path.expanduser('./voices/libritts.onnx')
VOICE_CONFIG = os.path.expanduser('./voices/libritts.onnx.json')

# Optional synthesis tweaks
PIPER_EXTRA_FLAGS = ['--length_scale', '0.95', '--noise_scale', '0.5']

# Player preference order
PLAYER_CANDIDATES = ['ffplay', 'paplay', 'aplay']

# Force the Piper **TTS** binary
PIPER_BIN = os.environ.get('PIPER_BIN') or '/usr/bin/piper-tts'

# ============== Globals ==============
recognizer = sr.Recognizer()
mic = sr.Microphone()
chat_history = deque(maxlen=HISTORY_MAX_MESSAGES)

run_lock = threading.Lock()
last_trigger = 0.0
TRIGGER_COOLDOWN = 0.5

listener_obj = None
KEEP_LAST_WAV = True
LAST_WAV_PATH = '/tmp/assistant_last.wav'

# ============== Piper TTS ==============
class PiperTTS:
    def __init__(self, model_path: str, config_path: str):
        self.model = os.path.abspath(os.path.expanduser(model_path))
        self.config = os.path.abspath(os.path.expanduser(config_path))
        if not os.path.isfile(self.model) or not os.path.isfile(self.config):
            raise FileNotFoundError(
                f"Piper voice files not found. Set VOICE_MODEL/VOICE_CONFIG correctly.\n"
                f"Model: {self.model}\nConfig: {self.config}"
            )
        self.bin = self._require_piper_tts()
        self.player = self._pick_player()
        self.q = []
        self.q_lock = threading.Lock()
        self.q_event = threading.Event()
        self.muted = False
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()
        print(f"Piper ready → bin: {self.bin} | voice: {os.path.basename(self.model)} | player: {self.player}")

    def _require_piper_tts(self) -> str:
        # Only accept piper-tts (or explicit PIPER_BIN)
        if not shutil.which(self._basename(PIPER_BIN)) and not os.path.isfile(PIPER_BIN):
            raise RuntimeError("piper-tts binary not found. Install piper-tts-bin or set PIPER_BIN=/path/to/piper-tts")
        # Validate it supports --model
        try:
            out = subprocess.run([PIPER_BIN, '--help'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3)
            text = out.stdout.decode(errors='ignore')
            if '--model' not in text or '--config' not in text:
                raise RuntimeError("The selected binary does not support --model/--config. Ensure it's Rhasspy Piper TTS (piper-tts).")
        except Exception as e:
            raise RuntimeError(f"Failed to run piper-tts: {e}")
        return PIPER_BIN

    def _basename(self, path):
        return os.path.basename(path) if path else ''

    def _pick_player(self):
        for cand in PLAYER_CANDIDATES:
            path = shutil.which(cand)
            if path:
                return os.path.basename(path)
        try:
            import sounddevice  # type: ignore
            print("[TTS] No external player found; will use python sounddevice fallback.")
            return 'python-sounddevice'
        except Exception:
            raise RuntimeError("No audio player found (install ffmpeg for ffplay, pulseaudio-utils for paplay, alsa-utils for aplay, or pip install sounddevice)")

    def say(self, text: str):
        if not text:
            return
        with self.q_lock:
            self.q.append(text)
            self.q_event.set()

    def toggle_mute(self):
        self.muted = not self.muted
        print(f"🔈 TTS {'muted' if self.muted else 'unmuted'}.")

    def _loop(self):
        while True:
            self.q_event.wait()
            while True:
                with self.q_lock:
                    text = self.q.pop(0) if self.q else None
                    if text is None:
                        self.q_event.clear()
                        break
                if self.muted:
                    continue
                self._synthesize_and_play(text)

    def _synthesize_and_play(self, text: str):
        # Write to a fixed path for easy manual testing
        wav_path = LAST_WAV_PATH if KEEP_LAST_WAV else tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        if KEEP_LAST_WAV and os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except Exception:
                pass
        try:
            # Piper synthesis
            cmd = [self.bin, '--model', self.model, '--config', self.config] + PIPER_EXTRA_FLAGS + ['--output_file', wav_path]
            proc = subprocess.run(cmd, input=text.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                err = proc.stderr.decode(errors='ignore')
                out = proc.stdout.decode(errors='ignore')
                raise RuntimeError(f"piper-tts exited rc={proc.returncode}: {err or out}")

            if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
                raise RuntimeError("piper-tts produced empty WAV")

            self._play(wav_path)
        except Exception as e:
            print(f"[TTS error] {e}")
        finally:
            if not KEEP_LAST_WAV:
                try:
                    if os.path.exists(wav_path):
                        os.unlink(wav_path)
                except Exception:
                    pass

    def _play(self, path):
        try:
            if self.player == 'ffplay':
                subprocess.run(['ffplay', '-autoexit', '-nodisp', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif self.player == 'paplay':
                subprocess.run(['paplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif self.player == 'aplay':
                subprocess.run(['aplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import sounddevice as sd
                import soundfile as sf
                data, sr = sf.read(path, dtype='float32')
                sd.play(data, sr)
                sd.wait()
        except Exception as e:
            print(f"[Play error] {e}")

# Global TTS engine
_tts = PiperTTS(VOICE_MODEL, VOICE_CONFIG)

# ============== Core plumbing ==============

def speak(text: str):
    _tts.say(text)


def transcribe_seconds(seconds: int) -> str:
    try:
        print(f"🎤 Listening for {seconds} seconds...")
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, phrase_time_limit=seconds, timeout=seconds+1)
        print("🧠 Transcribing...")
        try:
            return recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[STT service error] {e}")
            return ""
    except Exception as e:
        print(f"[Audio capture error] {e}")
        return ""


def call_llama_with_history(history_messages):
    payload = {"model": LLAMA_MODEL, "messages": history_messages, "stream": False}
    try:
        r = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content", "").strip()
    except Exception as e:
        return f"LLM error: {e}"


def build_messages_for_llm(user_text: str):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(list(chat_history))
    msgs.append({"role": "user", "content": user_text})
    return msgs


def _worker():
    text = transcribe_seconds(LISTEN_SECONDS)
    if not text:
        print("🤷 Didn't catch anything. (No history updated.)")
        return
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"🗣 [{ts}] You said: {text}")

    msgs = build_messages_for_llm(text)
    print("🤖 Asking local Llama with context (last 50 messages)...")
    reply = call_llama_with_history(msgs)
    print("💬 Llama:", reply)

    chat_history.append({"role": "user", "content": text})
    chat_history.append({"role": "assistant", "content": reply})

    speak(reply)


def trigger():
    global last_trigger
    now = time.time()
    if now - last_trigger < TRIGGER_COOLDOWN:
        return
    last_trigger = now

    if run_lock.locked():
        print("⏳ Busy; ignoring trigger.")
        return
    threading.Thread(target=lambda: (run_lock.acquire(), _worker(), run_lock.release()), daemon=True).start()


def clear_history():
    chat_history.clear()
    print("🧹 Conversation history cleared.")


def toggle_tts():
    _tts.toggle_mute()

# ============== Hotkeys / Overlay ==============

def start_hotkeys_x11():
    global listener_obj
    if not HAVE_PYNPUT:
        print("[Hotkeys] pynput not installed; skipping X11 hotkeys.")
        return False
    try:
        hk = pk.GlobalHotKeys({
            '<alt>+h': trigger,
            '<alt>+<shift>+c': clear_history,
            '<alt>+<shift>+m': toggle_tts
        })
        hk.start()
        listener_obj = hk
        print("✔ Global hotkeys active (X11): Alt+H / Alt+Shift+C / Alt+Shift+M")
        return True
    except Exception as e:
        print(f"[Hotkeys] Failed to start global hotkeys: {e}")
        return False


def start_overlay_button():
    import tkinter as tk

    root = tk.Tk()
    root.title("Voice")
    root.attributes("-topmost", True)
    root.geometry("80x80+40+40")
    root.resizable(False, False)

    frame = tk.Frame(root, bg="#111", bd=1, relief=tk.SOLID)
    frame.pack(fill=tk.BOTH, expand=True)

    btn = tk.Button(frame, text="🎙️", font=("Segoe UI", 18), command=trigger)
    btn.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    print("Overlay ready. Click 🎙️ to talk. While focused: Alt+H (talk), Shift+M (mute), Shift+C (clear)")

    def on_key(event):
        if event.keysym.lower() == 'h' and (event.state & 0x0008):
            trigger()
        elif event.keysym.lower() == 'm' and (event.state & 0x0001):
            toggle_tts()
        elif event.keysym.lower() == 'c' and (event.state & 0x0001):
            clear_history()
    root.bind('<Key>', on_key)

    root.mainloop()

# ============== Main ==============

def main():
    print("PIPER_BIN:", PIPER_BIN)
    print("Session:", os.environ.get('XDG_SESSION_TYPE'), " DISPLAY=", os.environ.get('DISPLAY'), " WAYLAND_DISPLAY=", os.environ.get('WAYLAND_DISPLAY'))

    # Mic prime (non-fatal)
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
        print("Mic primed.")
    except Exception as e:
        print(f"[Mic prime warning] {e}")

    session = (os.environ.get('XDG_SESSION_TYPE') or '').lower()
    if session == 'x11' and start_hotkeys_x11():
        print("Ready. Use Alt+H anywhere (X11). Overlay also available if preferred.")
        if listener_obj is not None:
            listener_obj.join()
        else:
            threading.Event().wait()
    else:
        start_overlay_button()

if __name__ == '__main__':
    main()

