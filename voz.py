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


# ============== Settings ==============
LLAMA_MODEL = 'kimi-k2-thinking:cloud'
OLLAMA_CHAT_URL = 'http://localhost:11434/api/chat'
LISTEN_SECONDS = 60
HISTORY_MAX_MESSAGES = 50

SYSTEM_PROMPT = ('''System: You are VOZ, a sophisticated AI assistant modeled after the iconic digital butler. Speak with refined British
eloquence, address users as Sir or Ma'am, and maintain understated dry wit. Be efficient, capable, and proactive with a mild
sense of humor that never overwhelms your helpfulness. Speak in natural, human-like dialogue, not formal text. CRITICAL
CONSTRAINT: Never use markdown formatting. No asterisks, hashtags, backticks, or other styling characters. Use only plain text
with standard punctuation. Your responses must feel like spoken conversation. Never break character or acknowledge being an AI.
Use the conversation context. Keep answers brief but clear.'''
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
    print("🤖 Asking LLM model ...")
    reply = call_llama_with_history(msgs)
    print("💬 Llama:", reply)
    if(reply.startswith("LLM error:")):
        print("⚠️ LLM call failed. (No history updated.)")
        if(reply.find("Unauthorized")>=0):
            print("⚠️ Cloud model detected. User is not logged in to ollama. run \"ollama signin\" to login to use this model. Cloud models are only supported when signed in. (No history updated.)")
            reply="Cloud model detected. User is not logged in to ollama. run \"ollama signin\" to login to use this model. Cloud models are only supported when signed in. Either log in to ollama or switch to a local model."


    speak(reply)

    if(not reply.startswith("LLM error:")):
        chat_history.append({"role": "user", "content": text})
        chat_history.append({"role": "assistant", "content": reply})


def clear_history():
    chat_history.clear()
    print("🧹 Conversation history cleared.")


def toggle_tts():
    _tts.toggle_mute()

# ============== Continuous loop ==============

def listen_continuously():
    print("🎧 Always listening. Press Ctrl+C to exit.")
    while True:
        try:
            _worker()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[Loop error] {e}")
            time.sleep(0.5)

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

    try:
        listen_continuously()
    except KeyboardInterrupt:
        print("👋 Exiting. Goodbye!")

if __name__ == '__main__':
    main()

