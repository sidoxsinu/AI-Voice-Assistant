# AI Voice-First Task Assistant

A voice-first task assistant that helps with email drafting, tasks, and Gmail. Audio is transcribed multi-modally via native **Gemini 2.5 Flash-Lite Audio** (with local **faster-whisper** as a fallback) to ensure perfectly spelled, grammatical text. With **`USE_ENGLISH_PIVOT=1`** (default), non-English speech is translated to **English** for the LLM, then assistant outputs are translated back to the user's language for **display and TTS** (Edge).

## Features

- **Voice input**: Browser microphone → WebSocket → **Gemini Native Audio / faster-whisper** (STT)
- **AI processing**: **Gemini 2.5 Flash-Lite** for JSON intents and replies in English, Hindi, or Malayalam
- **Gmail Integration**: Seamlessly draft and send emails
- **Task Management**: Manage to-do items
- **Email Composition**: Natural language email drafting
- **CORS Enabled**: Full frontend-backend communication support

## Prerequisites

Before running this project, ensure you have the following installed:

- **Python** (v3.11+ recommended)
- **ffmpeg** (required for WebM → WAV conversion fallback; included in the Docker image)
- **Node.js** (optional, only if you use the `npm start` shortcut in `project/`)
- **Docker & Docker Compose** (optional, for containerized setup)
- **API Keys**: Get free keys from [Google AI Studio](https://aistudio.google.com/).

## Environment setup

Copy `project/.env.example` to `project/.env` and set variables there. Important options:

| Variable | Purpose |
| -------- | ------- |
| `WHISPER_MODEL_SIZE` | Fallback STT quality vs speed (`large-v3` best for Malayalam) |
| `WHISPER_LANGUAGE` | Optional `ml` / `hi` / `en` to lock Whisper language (reduces wrong-language transcripts) |
| `WHISPER_LIVE_PARTIALS` | `0` = decode only when you stop (fewer errors); `1` = live interim text |
| `TTS_ENGINE` | `edge` (default, neural) |
| `GEMINI_API_KEY` | Gemini API key for Native Audio and LLM capability |
| `GMAIL_USER` / `GMAIL_PASS` | App password for sending mail |
| `USE_ENGLISH_PIVOT` | `1` (default): STT → translate to English → LLM (JSON in English) → translate back for UI/TTS |

## Installation

### 1. Clone/Navigate to Project

```bash
cd path/to/AI-Voice-Assistant
```

### 2. Install Python Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
cd project
pip install -r requirements.txt
```

## Running the Application

### Option 1: Local Development (Python)

1. Ensure your virtual environment is active:
   ```bash
   source venv/bin/activate
   ```
2. Start the FastAPI server:
   ```bash
   cd project
   python backend/server.py
   ```
   *Note: From `project/`, you can run `npm start` to use the venv at `../venv` and launch the server (adjust paths in `package.json` if your venv lives elsewhere).*

3. **Access the application**:
   Open your browser and navigate to:
   ```
   http://localhost:3000
   ```
   *(Important: Do NOT click the `0.0.0.0:3000` link in the terminal if it appears, as some browsers will show a blank page. Manually type `localhost:3000`)*

The server will start on port 3000 and serve the frontend files.

### Option 2: Docker (Recommended for Production)

1. **Ensure Docker is running** on your system

2. **Build and start the container**:
   ```bash
   docker-compose up --build
   ```

3. **Access the application**:
   Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

4. **Stop the application**:
   ```bash
   docker-compose down
   ```

## Verification Steps - ✅ Successfully Tested

### Successful Startup ✅
1. Create `project/.env` from `project/.env.example`
2. Ensure you have added your API keys in the `.env` file.
3. Ensure **ffmpeg** is available on `PATH` (or use Docker)
4. From `project/`, run `python backend/server.py`
5. Server listens on port 3000; open `http://localhost:3000`

### What to expect
- The app serves the frontend on port **3000** (FastAPI + static `index.html`).
- Voice flows: **WebSocket** `/api/listen` (record WebM → Gemini Native Audio / WAV → Whisper fallback); **REST** `/api/parse-command` for the assistant; **`/api/tts`** for spoken replies.
- Config is read from **`project/.env`**.

## Project structure

```
project/
├── index.html              # Frontend (mic, WebSocket, UI)
├── requirements.txt        # Python dependencies
├── package.json            # Optional npm script to start Python venv
├── Dockerfile
├── docker-compose.yml
├── backend/
│   ├── server.py           # FastAPI app (STT, Ollama, TTS, Gmail, todos)
│   └── todo.txt            # To-do storage (created at runtime)
└── .env                    # Create from .env.example (not committed)
```

## Usage

### API endpoints (selected)

- **WebSocket `/api/listen`** — streaming mic audio; final JSON `{ transcript, lang, is_final: true }`
- **POST `/api/transcribe`** — upload audio file → transcript
- **POST `/api/parse-command`** — `{ transcript, lang }` → intent JSON (`send_email`, `add_todo`, `reply`)
- **GET `/api/tts`** — `?text=&lang=` → MP3 stream
- **POST `/api/send-email`**, **POST `/api/add-todo`**, **GET/DELETE `/api/todos`**, **POST `/api/summarize`**

### Voice Command Examples

The assistant understands natural language commands such as:
- "Send an email to John about the project"
- "Draft a message thanking Sarah"
- "Add buy groceries to my to-do list"

## Development

### Running in Development Mode

For active development with auto-reload capabilities, use Docker Compose:

```bash
docker-compose up
```

This sets up volume mounts allowing you to edit files and see changes reflected immediately.

### Debugging

Use Python logging or `--log-level debug` with Uvicorn if you need verbose server traces.

## Dependencies (Python)

- **google-generativeai** — Gemini 2.5 Audio & LLM wrapper
- **faster-whisper** — local STT fallback
- **edge-tts** — text-to-speech
- **langdetect** — fallback language tagging for short text
- **python-dotenv** — environment variables

## Troubleshooting

### Port 3000 Already in Use

If port 3000 is already in use:
- **Local**: Modify the port in `docker-compose.yml` or use environment variable
- **Docker**: Change the port mapping in docker-compose.yml from `"3000:3000"` to `"3001:3000"`

### Python import or model errors

```bash
cd project
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Ensure **ffmpeg** is installed (`brew install ffmpeg` on macOS, or use the Docker image, which includes it).

### Environment variables not loading

- Verify `.env` file is in the `project` directory
- Ensure variable names match exactly (case-sensitive)
- Restart the server after changes

## Docker Troubleshooting

### Rebuild Docker Image

```bash
docker-compose build --no-cache
```

### View Logs

```bash
docker-compose logs -f
```

### Remove Containers and Volumes

```bash
docker-compose down -v
```

## Performance notes

- Use **`WHISPER_MODEL_SIZE=large-v3`** (and GPU if possible) for harder Malayalam audio.
- Set **`WHISPER_LANGUAGE=ml`** if users speak mostly Malayalam to avoid English/Hindi mis-detection.
- **`WHISPER_LIVE_PARTIALS=0`** avoids decoding incomplete WebM during recording (fewer nonsense interim lines).

## MacBook Air (Apple Silicon — M3 / M4 / M5, etc.)

**faster-whisper** does not use the GPU on macOS today; it runs on the CPU with optimized math libraries. The server auto-tunes on **`darwin` + `arm64`** when you leave these unset:

| Setting | Apple Silicon default | Why |
| -------- | --------------------- | --- |
| `WHISPER_DEVICE` | `auto` | Resolves to CPU on Mac (CUDA only on NVIDIA). |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8_float16` is often **unsupported** on macOS CPU (CTranslate2); the server falls back to `int8` / `default` if your override fails. |
| `WHISPER_CPU_THREADS` | about `(CPU cores − 2)`, between 4 and 12 | Leaves headroom for **Ollama** (Metal) and the browser so the Air does not stutter. |

Practical model sizes on a **MacBook Air**:

- **8 GB RAM:** keep **`medium`** (or **`small`** for speed); use **`distil-large-v3`** if you want faster passes than `large-v3` with decent quality.
- **16 GB RAM:** **`large-v3`** is a good default for Malayalam accuracy (first run downloads ~3 GB). If startup feels heavy, use **`distil-large-v3`** or **`medium`**.

**Gemini Usage**
Since we're using Gemini 2.5 Flash-Lite under the hood, running locally is no longer bounded by your machine's hardware! Native Gemini Multi-Modal audio offloads the STT bottleneck perfectly, so the MacBook Air fans shouldn't spin up under heavy load anymore.

## Production deployment

1. Use environment-specific `.env` files and restrict `allow_origins` in `CORSMiddleware` if exposing beyond localhost.
2. Run Uvicorn behind a reverse proxy (TLS, timeouts); disable `reload=True` in `server.py` for production.
3. Harden Gmail credentials (app passwords, least privilege) and add monitoring/logging as needed.

## License

Specify your project license here.

## Support

For issues or questions, please refer to the main project documentation or create an issue in the repository.
