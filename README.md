# vozAI — A Jarvis-style Local Voice Assistant

Voice Assistant (Local LLM + Offline STT + Piper TTS)

A fully offline Jarvis‑style voice assistant:

* 🎤 Speech‑to‑Text (STT) using `speech_recognition`
* 🤖 Local LLM via **Ollama** (default: `llama3`)
* 🧠 Persistent rolling memory (50 messages)
* 🗣️ High‑quality offline TTS using **Piper‑TTS**
* 🎛️ Hotkeys on X11, floating button on Wayland
* ⚡ No cloud services — private + fast

Perfect for Linux desktops (Arch recommended), voice‑operated workflows, and privacy‑focused devs.

---
## Showcase
[![Video Title](https://imgs.search.brave.com/2_NMZTgjdGugfmxqmaOvT3o9aplA6krV5XT_NwOzdL4/rs:fit:860:0:0:0/g:ce/aHR0cHM6Ly90My5m/dGNkbi5uZXQvanBn/LzE1LzQwLzY2LzQw/LzM2MF9GXzE1NDA2/NjQwMDNfMXF6TVR2/Sk9FZG16UGNMYmE5/WkZ6QUhsYzloMTRr/WXguanBn)](https://www.youtube.com/watch?v=XT6RYqDbLgk)

## 🚀 Features

* ✨ Natural Jarvis‑style assistant prompt
* 💾 Offline voices (no internet needed after setup)
* 🔁 Rolling convo memory like ChatGPT
* 🪟 Works on Wayland *and* X11
* 🔧 Local LLM via Ollama
* 🔇 Toggle TTS + clear history instantly

---

## 📦 Dependencies

### System

```bash
sudo pacman -S python python-pyaudio portaudio ffmpeg
paru -S piper-tts-bin  # or yay
```

### Python

```bash
pip install speechrecognition soundfile requests pynput
```

### LLM

Install **Ollama**:
[https://ollama.com](https://ollama.com)

Then pull a model:

```bash
ollama pull llama3
```

---

## 📁 Project Structure

```
voices/                # ← place Piper voice files here
voz.py
scripts/
  fetch_voice.sh       # optional helper script (create manually)
```

---

## 🔊 Downloading a Piper Voice Model

➡️ Listen to samples here:
[https://rhasspy.github.io/piper-samples/](https://rhasspy.github.io/piper-samples/)

Choose a voice you like, then download:

* `*.onnx`
* `*.onnx.json`

<img width="1340" height="620" alt="2025-11-02-200815_hyprshot" src="https://github.com/user-attachments/assets/637ab0f7-260f-4f20-847d-32a75a4863ee" />

Place them inside `voices/`, for example:

```
voices/amy.onnx
voices/amy.onnx.json
```

<img width="99" height="482" alt="2025-11-02-200918_hyprshot" src="https://github.com/user-attachments/assets/f35d69e8-e37c-4d42-992f-b19a1754b287" />

## IMPORTANT
> After downloading, **edit `voz.py` and change the `VOICE_MODEL` and `VOICE_CONFIG` paths** to match your chosen model.

---

### Controls

| Command       | Action             |
| ------------- | ------------------ |
| `Alt+H` (X11) | Listen + respond   |
| `Alt+Shift+M` | Mute/unmute voice  |
| `Alt+Shift+C` | Clear memory       |
| 🎙️ button    | Trigger |

---

## 🤖 Change Model

```bash
ollama pull phi3
# edit voz.py: LLAMA_MODEL = "phi3"
```

---

## 💡 Tips

* Tune Piper quality via `--length_scale` and `--noise_scale`
* Keep `.onnx` out of git (`.gitignore` recommended)

---

## 🛠️ Roadmap

* [ ] Whisper local STT option
* [ ] Auto‑download voice script
* [ ] VAD (voice activity detection)
* [ ] OpenAI Realtime compatibility

---

## 🧠 Credits

* **Piper‑TTS** — [https://github.com/rhasspy/piper](https://github.com/rhasspy/piper)
* **Ollama** — [https://ollama.com](https://ollama.com)

---

Enjoy your private local VOZ 🧠⚡

If you improve it, PRs welcome
