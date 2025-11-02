import keyboard
import speech_recognition as sr
import requests
import time

# ---- Settings ----
HOTKEY = 'alt+h'
LLAMA_MODEL = 'llama3'       # e.g., 'llama3', 'llama3.1', 'llama3:8b'
OLLAMA_URL = 'http://localhost:11434/api/generate'
LISTEN_SECONDS = 5

recognizer = sr.Recognizer()
mic = sr.Microphone()

def transcribe_seconds(seconds: int) -> str:
    """Record from default mic for `seconds` seconds and return text (Google SR)."""
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

def ask_llama(prompt: str) -> str:
    """Send prompt to local Llama via Ollama and return the model's reply."""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": (
            "You are a concise, helpful assistant.\n"
            f'User said: "{prompt}"\n'
            "Answer helpfully and briefly."
        ),
        "stream": False
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return ("Could not reach Ollama at http://localhost:11434.\n"
                "Make sure Ollama is installed, running, and the model is pulled "
                f"(e.g., `ollama pull {LLAMA_MODEL}`).")
    except Exception as e:
        return f"LLM error: {e}"

def run_stt_and_llm():
    text = transcribe_seconds(LISTEN_SECONDS)
    if not text:
        print("🤷 Could not understand anything clearly.")
        return
    print(f"🗣 You said: {text}")

    print("🤖 Asking local Llama...")
    reply = ask_llama(text)
    print("💬 Llama:", reply)

def main():
    # Prime the mic once (avoids first-use latency later)
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)

    keyboard.add_hotkey(HOTKEY, run_stt_and_llm)
    print(f"Ready. Press {HOTKEY.upper()} to record {LISTEN_SECONDS}s and ask Llama. Ctrl+C to quit.")
    keyboard.wait()  # keep the script running

if __name__ == "__main__":
    main()

