# Vani-Kanoon Setup Guide

## Overview

Vani-Kanoon is a voice-based multilingual legal assistant for Indian users. It supports
Hindi, Kannada, Marathi, Tamil, and Telugu, and provides real-time access to Indian legal
information including IPC/BNS sections, tenancy law, family law, and property law.

---

## Prerequisites

- Python 3.9+
- Node.js 16+ (for the Express backend)
- MongoDB (for user/patient data)
- A Google Gemini API key

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/Sa1ndesh/Vani.git
cd Vani
```

### 2. Set up the AI service

```bash
cd ai-service

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env        # Windows
# OR
cp .env.example .env          # Linux/macOS

# Edit .env and add your GEMINI_API_KEY
```

### 3. Start the AI service

```bash
uvicorn app:app --reload --port 8000
```

The service starts at **http://localhost:8000**. Open the interactive API docs at
http://localhost:8000/docs.

### 4. Open the legal assistant UI

Open `frontend/legal-assistant.html` in your browser:

```bash
# Windows PowerShell
Start-Process "frontend\legal-assistant.html"

# Linux/macOS
open frontend/legal-assistant.html
# or
xdg-open frontend/legal-assistant.html
```

---

## Optional Heavy Dependencies

These are commented out in `requirements.txt` to keep the default install lightweight.
Install them manually if you need their specific features.

### Whisper STT (high-accuracy speech recognition)

```bash
pip install openai-whisper
# Also requires ffmpeg:
# Windows: choco install ffmpeg
# macOS:   brew install ffmpeg
# Ubuntu:  apt-get install ffmpeg
```

### Coqui TTS (natural-sounding voice synthesis)

```bash
pip install TTS
```

### FAISS (fast vector search for RAG)

```bash
pip install faiss-cpu
# GPU version:
# pip install faiss-gpu
```

### Sentence Transformers (better semantic search)

```bash
pip install sentence-transformers
```

---

## Feature Overview

| Feature | Status | Notes |
|---------|--------|-------|
| Legal query (text) | ✅ Ready | Gemini AI + RAG |
| Multilingual response | ✅ Ready | 6 languages |
| Voice STT | ✅ Ready | Browser API + optional Whisper |
| Voice TTS | ✅ Ready | gTTS (lightweight) |
| State-specific laws | ✅ Ready | 8 states |
| Simplified explanations | ✅ Ready | Child-friendly mode |
| Dialect detection | ✅ Ready | 5 languages × dialects |
| Legal document analysis | ✅ Ready | |
| FAISS semantic search | ⚙️ Optional | Requires `faiss-cpu` |
| Whisper STT | ⚙️ Optional | Requires `openai-whisper` |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | **Yes** | Google Gemini API key |
| `WHISPER_MODEL` | No | Whisper model size (`tiny`/`base`/`small`) |
| `GEMINI_MODEL` | No | Override Gemini model name |
| `IPINFO_TOKEN` | No | ipinfo.io token for IP geolocation |

---

## Troubleshooting

### `python legal_data_loader.py: No such file or directory`

The file now exists. Pull the latest code:

```bash
git pull origin main
```

### `uvicorn was unexpected at this time`

You copied a shell command into Windows CMD. Run just:

```bash
uvicorn app:app --reload --port 8000
```

### `google.generativeai FutureWarning`

This is a warning, not an error. The app still works. To silence it, you can upgrade:

```bash
pip install google-genai
```

But the current `google-generativeai` package works fine for now.

### `ImportError: No module named 'gtts'`

```bash
pip install gTTS
```

### Port 8000 already in use

```bash
uvicorn app:app --reload --port 8080
```

---

## API Quick Reference

See [API_REFERENCE.md](API_REFERENCE.md) for the complete API documentation.
