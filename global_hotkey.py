# Single-file solution: Global hotkeys on X11 via pynput; on Wayland (no system tinkering),
# shows a tiny always-on-top overlay button (and Alt+H works while the overlay has focus).
#
# Run:  python stt_llama_history_tts_pynput_or_overlay.py
# Deps: speech_recognition, requests, pyttsx3, (optional) pynput on X11 (pip install pynput)
# GUI uses only tkinter (stdlib). No system config needed.

import os
import threading
import time
from datetime import datetime
from collections import deque

import speech_recognition as sr
import requests
import pyttsx3

# Try to import pynput, but only used on X11
try:
    from pynput import keyboard as pk  # type: ignore
    HAVE_PYNPUT = True
except Exception:
    HAVE_PYNPUT = False

# ---- Settings ----
LLAMA_MODEL = 'llama3'
OLLAMA_CHAT_URL = 'http://localhost:11434/api/chat'
LISTEN_SECONDS = 5
HISTORY_MAX_MESSAGES = 50

SYSTEM_PROMPT = (
    "You are a concise, helpful local assistant. "
    "Use the conversation context. Keep answers brief but clear."
)

# ---- Globals ----
recognizer = sr.Recognizer()
mic = sr.Microphone()
chat_history = deque(maxlen=HISTORY_MAX_MESSAGES)

tts_engine = pyttsx3.init()
tts_muted = False
tts_lock = threading.Lock()
run_lock = threading.Lock()
last_trigger = 0.0
COOLDOWN = 0.5

# ---- Core functions ----
def speak(text: str):
    global tts_muted
    if tts_muted or not text:
        return
    def _run():
        with tts_lock:
            try:
                tts_engine.say(text)
                tts_engine.runAndWait()
            except Exception as e:
                print(f"[TTS error] {e}")
    threading.Thread(target=_run, daemon=True).start()


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
    if now - last_trigger < COOLDOWN:
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
    global tts_muted
    tts_muted = not tts_muted
    print(f"🔈 TTS {'muted' if tts_muted else 'unmuted'}.")

# ---- X11 hotkeys via pynput ----
listener_obj = None

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

# ---- Wayland-friendly overlay (tkinter stdlib) ----

def start_overlay_button():
    import tkinter as tk

    root = tk.Tk()
    root.title("Voice")
    root.attributes("-topmost", True)
    # small always-on-top window
    size = 80
    root.geometry(f"{size}x{size}+40+40")
    root.resizable(False, False)

    # make it minimalistic
    frame = tk.Frame(root, bg="#111", bd=1, relief=tk.SOLID)
    frame.pack(fill=tk.BOTH, expand=True)

    status = tk.StringVar(value="🎙️")

    btn = tk.Button(frame, textvariable=status, font=("Segoe UI", 18),
                    command=lambda: trigger())
    btn.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    # keyboard shortcuts when focused
    def on_key(event):
        if event.keysym.lower() == 'h' and (event.state & 0x0008):  # Alt mask
            trigger()
        elif event.keysym.lower() == 'm' and (event.state & 0x0001):  # Shift mask
            toggle_tts()
        elif event.keysym.lower() == 'c' and (event.state & 0x0001):  # Shift mask
            clear_history()

    root.bind('<Key>', on_key)

    # show usage hint once
    print("Overlay ready. Click 🎙️ to talk (no system config). If window is focused:")
    print("  Alt+H → talk   |  Shift+M → mute/unmute  |  Shift+C → clear history")

    root.mainloop()

# ---- Main ----

def main():
    print("Session:", os.environ.get('XDG_SESSION_TYPE'), " DISPLAY=", os.environ.get('DISPLAY'), " WAYLAND_DISPLAY=", os.environ.get('WAYLAND_DISPLAY'))

    # Mic prime (non-fatal)
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
        print("Mic primed.")
    except Exception as e:
        print(f"[Mic prime warning] {e}")

    session = (os.environ.get('XDG_SESSION_TYPE') or '').lower()
    if session == 'x11':
        if start_hotkeys_x11():
            print("Ready. Use Alt+H anywhere (X11). Also supports overlay if you want.")
            # keep process alive
            if listener_obj is not None:
                listener_obj.join()
            else:
                threading.Event().wait()
        else:
            print("Falling back to overlay button (no config needed).")
            start_overlay_button()
    else:
        # Wayland or unknown → overlay approach, no system config
        start_overlay_button()

if __name__ == '__main__':
    main()

