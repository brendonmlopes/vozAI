import keyboard
import speech_recognition as sr
import requests
from collections import deque
from datetime import datetime

# ---- Settings ----
HOTKEY = 'alt+h'
CLEAR_HISTORY_HOTKEY = 'alt+shift+c'  # optional convenience
LLAMA_MODEL = 'llama3'
OLLAMA_CHAT_URL = 'http://localhost:11434/api/chat'
LISTEN_SECONDS = 5
HISTORY_MAX_MESSAGES = 50  # tracks both user and assistant messages

recognizer = sr.Recognizer()
mic = sr.Microphone()

# Rolling chat history (messages are dicts with 'role' and 'content')
chat_history = deque(maxlen=HISTORY_MAX_MESSAGES)

# Optional: a brief system message that anchors behavior
SYSTEM_PROMPT = (
    "You are a concise, helpful local assistant. "
    "Use the provided conversation context. Keep answers brief but clear."
)

def transcribe_seconds(seconds: int) -> str:
    print(f"🎤 Listening for {seconds} seconds...")
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        audio = recognizer.listen(source, phrase_time_limit=seconds)
    print("🧠 Transcribing...")
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"STT service error: {e}")
        return ""

def call_llama_with_history(history_messages):
    """Use Ollama's chat API with full message history."""
    payload = {
        "model": LLAMA_MODEL,
        "messages": history_messages,
        "stream": False,
        # You can pass options here, e.g., temperature:
        # "options": {"temperature": 0.5}
    }
    try:
        r = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=180)
        r.raise_for_status()
        data = r.json()
        # Ollama chat returns the final assistant message under data["message"]["content"]
        msg = data.get("message", {}) or {}
        return msg.get("content", "").strip()
    except requests.exceptions.ConnectionError:
        return ("Could not reach Ollama at http://localhost:11434.\n"
                "Ensure Ollama is running and a model is pulled "
                f"(e.g., `ollama pull {LLAMA_MODEL}`).")
    except Exception as e:
        return f"LLM error: {e}"

def build_messages_for_llm(user_text: str):
    """
    Compose the message list: optional system message + (up to) last 50 messages + new user message.
    """
    messages = []

    # Optional system message to set behavior (not counted in your 50 unless you want it to be)
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    # Add the rolling history
    messages.extend(list(chat_history))

    # Add the fresh user message
    messages.append({"role": "user", "content": user_text})

    return messages

def run_stt_and_llm():
    text = transcribe_seconds(LISTEN_SECONDS)
    if not text:
        print("🤷 Didn't catch anything. (No history updated.)")
        return

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"🗣 [{timestamp}] You said: {text}")

    # Build full message list for LLM
    messages = build_messages_for_llm(text)

    print("🤖 Asking local Llama with last 50 messages of context...")
    reply = call_llama_with_history(messages)
    print("💬 Llama:", reply)

    # Update rolling history: only add if we had user text and an LLM reply
    chat_history.append({"role": "user", "content": text})
    chat_history.append({"role": "assistant", "content": reply})

def clear_history():
    chat_history.clear()
    print("🧹 Conversation history cleared.")

def main():
    # Prime mic to reduce first-run latency
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)

    keyboard.add_hotkey(HOTKEY, run_stt_and_llm)
    keyboard.add_hotkey(CLEAR_HISTORY_HOTKEY, clear_history)

    print(f"Ready. Press {HOTKEY.upper()} to record {LISTEN_SECONDS}s and ask Llama.")
    print(f"Press {CLEAR_HISTORY_HOTKEY.upper()} to clear the stored history. Ctrl+C to quit.")
    keyboard.wait()

if __name__ == "__main__":
    main()

