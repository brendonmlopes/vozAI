import keyboard
import speech_recognition as sr
import time

recognizer = sr.Recognizer()
mic = sr.Microphone()

def run_stt():
    print("Listening for 5 seconds...")

    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source, phrase_time_limit=5)

    print("Processing...")

    try:
        text = recognizer.recognize_google(audio)
        print("You said:", text)
    except sr.UnknownValueError:
        print("Could not understand audio")
    except sr.RequestError:
        print("Speech recognition service unavailable")

# Hotkey: Alt+H
keyboard.add_hotkey('alt+h', run_stt)

print("Press Alt+H to record 5 seconds of audio. Ctrl+C to quit.")
keyboard.wait()

