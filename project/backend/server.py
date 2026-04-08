import os
import io
import json
import sys
import platform
import smtplib
from email.message import EmailMessage
from fastapi import FastAPI, UploadFile, File, Request, WebSocket, WebSocketDisconnect
import asyncio
import queue
import threading
import tempfile
import subprocess
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import edge_tts
from faster_whisper import WhisperModel
import google.generativeai as genai
from groq import AsyncGroq
from langdetect import detect
from gtts import gTTS

# Load environment variables
PROJECT_DOTENV = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(PROJECT_DOTENV)
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
if _cred and not os.path.isabs(_cred):
    _abs_cred = os.path.abspath(os.path.join(PROJECT_DIR, _cred))
    if os.path.isfile(_abs_cred):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _abs_cred

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TODO_FILE = os.path.join(PROJECT_DIR, "backend", "todo.txt")


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _env_str(key: str) -> str | None:
    v = os.getenv(key)
    return v.strip() if v and v.strip() else None


def _default_whisper_device() -> str:
    # "auto" picks CUDA when present, else CPU (correct for Mac + Apple Silicon).
    return _env_str("WHISPER_DEVICE") or "auto"


def _default_whisper_compute_type() -> str:
    if (override := _env_str("WHISPER_COMPUTE_TYPE")):
        return override
    # Default int8 everywhere; macOS CPU often rejects int8_float16 with CTranslate2.
    return "int8"


def _default_whisper_cpu_threads() -> int:
    if (raw := _env_str("WHISPER_CPU_THREADS")):
        return max(1, int(raw))
    # Leave ~2 cores for Ollama, browser, and thermals on Air-class machines.
    if _is_apple_silicon():
        n = os.cpu_count() or 8
        return max(4, min(n - 2, 12))
    return 0



USE_ENGLISH_PIVOT = os.getenv("USE_ENGLISH_PIVOT", "1").lower() in ("1", "true", "yes")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
llm_model = genai.GenerativeModel("gemini-2.5-flash-lite")

groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = AsyncGroq(api_key=groq_api_key) if groq_api_key else None

VOICE_EMAIL_DRAFT_EN = (
    "I have drafted the email. Please review it and confirm to send."
)
VOICE_EMAIL_SENT_EN = "Your email has been sent successfully."

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium")
WHISPER_DEVICE = _default_whisper_device()
WHISPER_COMPUTE_TYPE = _default_whisper_compute_type()
WHISPER_CPU_THREADS = _default_whisper_cpu_threads()
# Set to ml / hi / en to skip Whisper language detection (improves accuracy when you mostly speak one language)
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "").strip() or None
# Live partial transcripts re-decode incomplete WebM; off by default to avoid garbage interim text.
WHISPER_LIVE_PARTIALS = os.getenv("WHISPER_LIVE_PARTIALS", "0").lower() in ("1", "true", "yes")
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge").lower()
# STT: local = faster-whisper; google = Google Cloud Speech-to-Text (live captions, often more accurate).
STT_PROVIDER_REQUESTED = os.getenv("STT_PROVIDER", "local").lower().strip()
_gst_langs = [x.strip() for x in os.getenv("GOOGLE_STT_LANGUAGES", "ml-IN,en-IN,hi-IN").split(",") if x.strip()]
GOOGLE_STT_PRIMARY = _gst_langs[0] if _gst_langs else "ml-IN"
GOOGLE_STT_ALTERNATIVES = _gst_langs[1:4] if len(_gst_langs) > 1 else ["en-IN", "hi-IN"]


def _whisper_load_attempts(preferred: str) -> list[str]:
    order = [preferred, "int8", "default"]
    seen: set[str] = set()
    out: list[str] = []
    for x in order:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


speech_client = None
STT_PROVIDER_ACTIVE = "local"

if STT_PROVIDER_REQUESTED == "google":
    try:
        from google.cloud import speech_v1 as speech_v1

        speech_client = speech_v1.SpeechClient()
        STT_PROVIDER_ACTIVE = "google"
        print("STT provider: Google Cloud Speech-to-Text")
    except Exception as e:
        print(f"STT provider: Google unavailable ({e}); falling back to local Whisper")

LANGUAGE_MAP = {
    "ml": {
        "name": "Malayalam",
        "gtts_code": "ml",
        "edge_voice": "ml-IN-SobhanaNeural",
    },
    "hi": {
        "name": "Hindi",
        "gtts_code": "hi",
        "edge_voice": "hi-IN-SwaraNeural",
    },
    "en": {
        "name": "English",
        "gtts_code": "en",
        "edge_voice": "en-US-AvaMultilingualNeural",
    },
}

ML_PROMPT_HINT = (
    "For Malayalam: use proper Malayalam script in JSON string values where appropriate; "
    "keep email addresses and proper nouns accurate."
)

def detect_language_safe(text: str) -> str:
    try:
        lang = detect(text)
        return lang if lang in LANGUAGE_MAP else "en"
    except Exception:
        return "en"


LANG_FULL_NAME = {"en": "English", "ml": "Malayalam", "hi": "Hindi"}


def _translate_lang_label(code: str) -> str:
    return LANG_FULL_NAME.get(
        code, LANGUAGE_MAP.get(code, {}).get("name", f"language ({code})")
    )


async def ollama_translate(text: str, *, source_code: str, target_code: str) -> str:
    text = (text or "").strip()
    if not text or source_code == target_code:
        return text
    src = _translate_lang_label(source_code)
    tgt = _translate_lang_label(target_code)
    prompt = (
        f"Translate the following from {src} to {tgt}.\n"
        f"Preserve proper names, email addresses, URLs, and numbers exactly.\n"
        f"Output ONLY the translation, with no quotes or explanation.\n\n{text}"
    )
    try:
        response = await llm_model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini translate error: {e}")
        return text


def _google_bcp47_to_app(code: str) -> str:
    c = (code or "").lower()
    if c.startswith("ml"):
        return "ml"
    if c.startswith("hi"):
        return "hi"
    return "en"


stt_model: WhisperModel | None = None
if STT_PROVIDER_ACTIVE != "google":
    print("Loading Whisper STT model...")
    if _is_apple_silicon():
        print(
            f"  Apple Silicon: device={WHISPER_DEVICE!r}, compute_type={WHISPER_COMPUTE_TYPE!r}, "
            f"cpu_threads={WHISPER_CPU_THREADS}"
        )
    _load_err: BaseException | None = None
    for _try_ct in _whisper_load_attempts(WHISPER_COMPUTE_TYPE):
        try:
            stt_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=_try_ct,
                cpu_threads=WHISPER_CPU_THREADS,
            )
            if _try_ct != WHISPER_COMPUTE_TYPE:
                print(f"  Whisper compute_type fallback: {WHISPER_COMPUTE_TYPE!r} -> {_try_ct!r}")
            break
        except ValueError as e:
            _load_err = e
            msg = str(e).lower()
            if "compute" in msg or "backend" in msg:
                continue
            raise
    else:
        assert _load_err is not None
        raise _load_err
    print("Whisper model loaded.")
else:
    print("STT: Skipping Whisper load (Google Cloud Speech-to-Text only)")

# ---- Request Models ----
class ParseCommandRequest(BaseModel):
    transcript: str
    lang: str = "en"

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str

class SummarizeRequest(BaseModel):
    text: str

class AddTodoRequest(BaseModel):
    transcript: str
    lang: str = "en"
    task_english: str | None = None


class TranslateTextRequest(BaseModel):
    text: str
    target_lang: str


def _webm_bytes_to_linear16_16k_mono(audio_bytes: bytes | bytearray) -> bytes:
    if len(audio_bytes) < 100:
        return b""
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        p = tmp_in.name
    raw_path = p + ".s16le"
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-i", p,
                "-ar", "16000", "-ac", "1", "-f", "s16le", "-acodec", "pcm_s16le",
                raw_path,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0 or not os.path.exists(raw_path):
            return b""
        with open(raw_path, "rb") as rf:
            return rf.read()
    finally:
        for x in (p, raw_path):
            if os.path.exists(x):
                try:
                    os.remove(x)
                except OSError:
                    pass


def _google_recognize_linear16(pcm: bytes) -> tuple[str, str]:
    from google.cloud import speech_v1 as speech

    if not speech_client or not pcm:
        return "", "en"
    audio = speech.RecognitionAudio(content=pcm)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code=GOOGLE_STT_PRIMARY,
        alternative_language_codes=GOOGLE_STT_ALTERNATIVES[:3],
        enable_automatic_punctuation=True,
    )
    resp = speech_client.recognize(config=config, audio=audio)
    lines: list[str] = []
    glang = GOOGLE_STT_PRIMARY
    for res in resp.results:
        if res.alternatives:
            lines.append(res.alternatives[0].transcript.strip())
        if getattr(res, "language_code", ""):
            glang = res.language_code
    text = " ".join(lines).strip()
    return text, _google_bcp47_to_app(glang)


def _webm_to_wav_16k(webm_path: str, wav_path: str) -> bool:
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-i", webm_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            wav_path,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("ffmpeg failed:", (r.stderr or "")[:500])
    return r.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 0


def _whisper_decode(
    wav_path: str,
    *,
    final: bool,
) -> tuple[str, str]:
    if stt_model is None:
        return "", "en"
    lang_kw: dict = {}
    if WHISPER_LANGUAGE:
        lang_kw["language"] = WHISPER_LANGUAGE

    initial_prompt = (
        "നമസ്കാരം. മലയാള വാചകം. "
        "Hindi: नमस्ते. English: Hello."
    )

    if final:
        segments, info = stt_model.transcribe(
            wav_path,
            beam_size=5,
            best_of=5,
            patience=1.0,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            condition_on_previous_text=True,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            initial_prompt=initial_prompt,
            **lang_kw,
        )
    else:
        segments, info = stt_model.transcribe(
            wav_path,
            beam_size=5,
            best_of=2,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
            **lang_kw,
        )

    text = "".join(seg.text for seg in segments).strip()
    detected = info.language if info.language in LANGUAGE_MAP else "en"
    return text, detected


def _transcribe_webm_bytes(audio_bytes: bytes | bytearray, *, final: bool) -> tuple[str, str]:
    if len(audio_bytes) < 1000:
        return "", "en"

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path.replace(".webm", ".wav")
    try:
        if not _webm_to_wav_16k(tmp_in_path, tmp_out_path):
            return "", "en"
        return _whisper_decode(tmp_out_path, final=final)
    finally:
        for p in (tmp_in_path, tmp_out_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


async def fix_grammar_with_llm(text: str, lang: str) -> str:
    if not text.strip():
        return text
        
    lang_map = {
        "en": "English",
        "ml": "Malayalam",
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "kn": "Kannada",
        "mr": "Marathi",
        "gu": "Gujarati",
        "bn": "Bengali"
    }
    full_lang_name = lang_map.get(lang, lang)
    
    try:
        grammar_model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""
You are a native-level expert in {full_lang_name}.

The following sentence is generated by speech recognition and may contain:
- phonetic mistakes
- wrong words
- broken grammar
- incorrect names or numbers

This is a voice assistant command.

Your task:
1. Understand the REAL meaning of the sentence
2. Convert it into the most natural, grammatically perfect sentence in {full_lang_name}
3. Fix names, places, and numbers intelligently
4. DO NOT translate — keep same language
5. DO NOT output explanation — ONLY final corrected sentence
6. If input is unclear, infer the most likely sentence a human intended to say

Input:
{text}

Output:
"""
        response = await grammar_model.generate_content_async(prompt)
        corrected = response.text.strip()
        if corrected.startswith('"') and corrected.endswith('"'):
            corrected = corrected[1:-1]
            
        return corrected
    except Exception as e:
        print(f"Grammar correction failed: {e}")
        return text


async def run_whisper_on_buffer(
    audio_bytes: bytearray | bytes, final: bool = False
) -> tuple[str, str]:
    text, lang = await _run_whisper_on_buffer_internal(audio_bytes, final)
    if final and text:
        text = await fix_grammar_with_llm(text, lang)
    return text, lang


async def _run_whisper_on_buffer_internal(
    audio_bytes: bytearray | bytes, final: bool = False
) -> tuple[str, str]:
    if STT_PROVIDER_ACTIVE == "google" and speech_client:
        pcm = await asyncio.to_thread(_webm_bytes_to_linear16_16k_mono, audio_bytes)
        if not pcm:
            return "", "en"
        return await asyncio.to_thread(_google_recognize_linear16, pcm)
    
    if groq_client and final:
        tmp_in_path = ""
        tmp_out_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                tmp_in_path = tmp_in.name
                
            tmp_out_path = tmp_in_path.replace(".webm", ".wav")
            success = await asyncio.to_thread(_webm_to_wav_16k, tmp_in_path, tmp_out_path)
            
            if success:
                kwargs = {}
                if WHISPER_LANGUAGE:
                    kwargs["language"] = WHISPER_LANGUAGE
                
                # Nudge model toward exact accurate transcription and multi-lingual capability
                prompt_text = "നമസ്കാരം. മലയാള വാചകം. Hindi: नमस्ते. English: Hello. 0 1 2 3 4 5 6 7 8 9"
                
                with open(tmp_out_path, "rb") as f:
                    transcription = await groq_client.audio.transcriptions.create(
                        file=("audio.wav", f.read()),
                        model="whisper-large-v3-turbo",
                        prompt=prompt_text,
                        temperature=0.0,
                        **kwargs
                    )
                
                final_text = transcription.text.strip()
                final_lang = WHISPER_LANGUAGE or detect_language_safe(final_text)
                return final_text, final_lang
            else:
                print("ffmpeg wav conversion failed for Groq.")
        except Exception as e:
            print(f"Groq Audio failed: {e}. Falling back to local Whisper.")
        finally:
            for p in (tmp_in_path, tmp_out_path):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    # Partial or fallback -> faster-whisper
    return await asyncio.to_thread(_transcribe_webm_bytes, audio_bytes, final=final)


async def _google_websocket_session(websocket: WebSocket) -> None:
    from google.cloud import speech_v1 as speech

    audio_q: queue.Queue[bytes | None] = queue.Queue()
    out_q: queue.Queue[tuple[str, object] | None] = queue.Queue()

    streaming_config = speech.StreamingRecognitionConfig(
        config=speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=GOOGLE_STT_PRIMARY,
            alternative_language_codes=GOOGLE_STT_ALTERNATIVES[:3],
            enable_automatic_punctuation=True,
        ),
        interim_results=True,
    )

    def worker() -> None:
        client = speech.SpeechClient()

        def gen_requests():
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            while True:
                chunk = audio_q.get()
                if chunk is None:
                    return
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

        try:
            for response in client.streaming_recognize(gen_requests()):
                out_q.put(("ok", response))
        except Exception as e:
            out_q.put(("err", e))
        finally:
            out_q.put(None)

    th = threading.Thread(target=worker, daemon=True)
    th.start()

    parts: list[str] = []
    interim_tail = ""
    last_app_lang = _google_bcp47_to_app(GOOGLE_STT_PRIMARY)

    async def consume_responses() -> None:
        nonlocal interim_tail, last_app_lang
        while True:
            item = await asyncio.to_thread(out_q.get)
            if item is None:
                break
            kind, payload = item
            if kind == "err":
                print("Google Speech streaming error:", payload)
                break
            response = payload
            for result in response.results:
                if not result.alternatives:
                    continue
                raw_txt = result.alternatives[0].transcript
                gcode = getattr(result, "language_code", None) or GOOGLE_STT_PRIMARY
                last_app_lang = _google_bcp47_to_app(gcode)
                if result.is_final:
                    if raw_txt.strip():
                        parts.append(raw_txt.strip())
                    interim_tail = ""
                    shown = " ".join(parts).strip()
                else:
                    interim_tail = raw_txt
                    shown = (" ".join(parts) + " " + interim_tail).strip()
                if shown:
                    try:
                        await websocket.send_json({
                            "transcript": shown,
                            "is_final": False,
                            "lang": last_app_lang,
                        })
                    except Exception:
                        return

    consumer = asyncio.create_task(consume_responses())

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                audio_q.put(bytes(message["bytes"]))
            elif "text" in message:
                data = json.loads(message["text"])
                if data.get("type") == "CloseStream":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        audio_q.put(None)
        await consumer
        th.join(timeout=60.0)

    final_text = (" ".join(parts) + " " + interim_tail).strip()
    try:
        await websocket.send_json({
            "transcript": final_text,
            "lang": last_app_lang,
            "is_final": True,
        })
        await websocket.close()
    except Exception:
        pass


async def _whisper_websocket_session(websocket: WebSocket) -> None:
    audio_buffer = bytearray()

    last_transcribed_len = 0
    is_recording = True

    async def transcribe_loop():
        nonlocal audio_buffer, last_transcribed_len, is_recording
        while is_recording:
            await asyncio.sleep(1.0)
            if len(audio_buffer) - last_transcribed_len > 8000:
                current_len = len(audio_buffer)
                text, _ = await run_whisper_on_buffer(audio_buffer[:current_len], final=False)
                if text:
                    try:
                        await websocket.send_json({"transcript": text, "is_final": False})
                    except Exception:
                        pass
                last_transcribed_len = current_len

    partial_task = asyncio.create_task(transcribe_loop()) if WHISPER_LIVE_PARTIALS else None

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                audio_buffer.extend(message["bytes"])
            elif "text" in message:
                data = json.loads(message["text"])
                if data.get("type") == "CloseStream":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        is_recording = False
        if partial_task:
            partial_task.cancel()

    final_text, lang = await run_whisper_on_buffer(audio_buffer, final=True)
    try:
        await websocket.send_json({"transcript": final_text, "lang": lang, "is_final": True})
        await websocket.close()
    except Exception:
        pass


# ---- Endpoints ----
@app.get("/api/stt-config")
async def stt_config():
    use_google = STT_PROVIDER_ACTIVE == "google" and speech_client is not None
    return {"provider": "google" if use_google else "local", "sampleRateHertz": 16000}


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    text, lang = await run_whisper_on_buffer(audio_bytes, final=True)

    if not text:
        return {"transcript": "", "lang": "en"}

    return {"transcript": text, "lang": lang}


@app.websocket("/api/listen")
async def websocket_listen(websocket: WebSocket):
    await websocket.accept()
    if STT_PROVIDER_ACTIVE == "google" and speech_client:
        await _google_websocket_session(websocket)
    else:
        await _whisper_websocket_session(websocket)

@app.post("/api/parse-command")
async def parse_command(req: ParseCommandRequest):
    transcript = (req.transcript or "").strip()
    if not transcript:
        return JSONResponse(status_code=400, content={"error": "No transcript provided"})

    lang_code = req.lang if req.lang in LANGUAGE_MAP else detect_language_safe(transcript)
    lang_name = LANGUAGE_MAP.get(lang_code, {}).get("name", "English")

    if USE_ENGLISH_PIVOT and lang_code != "en":
        transcript_en = await ollama_translate(transcript, source_code=lang_code, target_code="en")
        print(f"STT ({lang_code}) → EN: {transcript_en[:200]}...")
        prompt = f"""
You are a voice assistant pipeline. The user speaks {lang_name}.

Original user text (verbatim): "{transcript}"
English meaning (for reasoning): "{transcript_en}"

Reply ONLY with a raw JSON object, no markdown, no backticks.

Infer intent using the English line; use the original for names/emails in {lang_name} if clearer.

All JSON string values MUST be in English (they will be translated to {lang_name} for speech and UI):
1. send_email — draft an email
2. add_todo — add a task
3. reply — chat / question

Formats:
{{"action": "send_email", "to": "recipient@email.com or name", "subject": "...", "body": "..."}}
{{"action": "add_todo", "task": "short task in English"}}
{{"action": "reply", "text": "helpful answer in English"}}

Output:"""
    else:
        transcript_en = transcript
        malayalam_note = f"\n{ML_PROMPT_HINT}\n" if lang_code == "ml" else ""
        prompt = f"""
You are a voice assistant. The user speaks in {lang_name}.
Reply ONLY with a raw JSON object, no markdown, no backticks.
{malayalam_note}
Identify the user's intent from these options:
1. send_email — user wants to draft/send an email
2. add_todo — user wants to add a task or reminder
3. reply — general question or conversation

Output format for send_email:
{{"action": "send_email", "to": "recipient", "subject": "subject", "body": "email body"}}

Output format for add_todo:
{{"action": "add_todo", "task": "the extracted task text"}}

Output format for reply (text MUST be in {lang_name}):
{{"action": "reply", "text": "your helpful reply in {lang_name}"}}

User said: "{transcript}"
Output:"""

    try:
        response = await llm_model.generate_content_async(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        raw_text = response.text.strip()
        cleaned = raw_text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        parsed["lang"] = lang_code

        if USE_ENGLISH_PIVOT and lang_code != "en":
            action = parsed.get("action")
            if action == "reply" and parsed.get("text"):
                parsed["text"] = await ollama_translate(
                    parsed["text"], source_code="en", target_code=lang_code
                )
            elif action == "send_email":
                subj = parsed.get("subject") or ""
                body = parsed.get("body") or ""
                coros = [
                    ollama_translate(VOICE_EMAIL_DRAFT_EN, source_code="en", target_code=lang_code),
                ]
                if subj:
                    coros.append(ollama_translate(subj, source_code="en", target_code=lang_code))
                if body:
                    coros.append(ollama_translate(body, source_code="en", target_code=lang_code))
                results = await asyncio.gather(*coros)
                parsed["voice_message"] = results[0]
                i = 1
                if subj:
                    parsed["subject"] = results[i]
                    i += 1
                if body:
                    parsed["body"] = results[i]
            # add_todo: keep "task" in English; add_todo endpoint localizes for list + speech
        elif parsed.get("action") == "send_email":
            parsed["voice_message"] = (
                VOICE_EMAIL_DRAFT_EN
                if lang_code == "en"
                else await ollama_translate(VOICE_EMAIL_DRAFT_EN, source_code="en", target_code=lang_code)
            )

        if parsed.get("action") == "send_email" and not parsed.get("voice_message"):
            parsed["voice_message"] = VOICE_EMAIL_DRAFT_EN

        return parsed

    except Exception as e:
        print("Ollama error:", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to parse voice command", "details": str(e)},
        )


@app.post("/api/translate-text")
async def translate_text_endpoint(req: TranslateTextRequest):
    text = (req.text or "").strip()
    if not text:
        return {"text": ""}
    target = req.target_lang if req.target_lang in LANGUAGE_MAP else "en"
    if target == "en":
        return {"text": text}
    try:
        out = await ollama_translate(text, source_code="en", target_code=target)
        return {"text": out}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

async def _edge_tts_mp3(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    parts: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            parts.append(chunk["data"])
    return b"".join(parts)


async def _gtts_mp3(text: str, gtts_code: str) -> bytes:
    def _run():
        tts = gTTS(text=text, lang=gtts_code, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()

    return await asyncio.to_thread(_run)


@app.get("/api/tts")
async def text_to_speech(text: str, lang: str = "en"):
    """Streams MP3: Microsoft Edge neural voices by default (stronger Malayalam), gTTS as fallback."""
    meta = LANGUAGE_MAP.get(lang, LANGUAGE_MAP["en"])
    gtts_code = meta.get("gtts_code", "en")
    voice = meta.get("edge_voice", "en-US-AvaMultilingualNeural")

    try:
        if TTS_ENGINE == "edge":
            try:
                audio = await _edge_tts_mp3(text, voice)
            except Exception as e:
                print("Edge TTS failed, using gTTS:", e)
                audio = await _gtts_mp3(text, gtts_code)
        else:
            audio = await _gtts_mp3(text, gtts_code)
        return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg")
    except Exception as e:
        print("TTS error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/send-email")
async def send_email(req: SendEmailRequest):
    try:
        msg = EmailMessage()
        msg.set_content(req.body)
        msg['Subject'] = req.subject
        msg['From'] = f"Voice Assistant <{os.getenv('GMAIL_USER')}>"
        msg['To'] = req.to

        # Send the message via our own SMTP server.
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(os.getenv('GMAIL_USER'), os.getenv('GMAIL_PASS'))
        server.send_message(msg)
        server.quit()

        return {"success": True}
    except Exception as e:
        print('Gmail send error:', e)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.post("/api/summarize")
async def summarize(req: SummarizeRequest):
    text = req.text
    if not text:
        return JSONResponse(status_code=400, content={"error": "No text provided"})
        
    prompt = f"""Summarize the following text in 3 
sentences or less. Be concise and clear. 
Return only the summary, nothing else:

"{text}"
"""
    try:
        response = await llm_model.generate_content_async(prompt)
        return {"summary": response.text.strip()}
    except Exception as e:
        print("Summary error:", e)
        return JSONResponse(status_code=500, content={"error": "Failed to summarize"})

@app.post("/api/add-todo")
async def add_todo(req: AddTodoRequest):
    lang_code = req.lang if req.lang in LANGUAGE_MAP else detect_language_safe(req.transcript)
    lang_name = LANGUAGE_MAP.get(lang_code, {}).get("name", "English")
    original = (req.transcript or "").strip()

    try:
        if req.task_english and req.task_english.strip():
            task_en = req.task_english.strip()
        elif USE_ENGLISH_PIVOT and lang_code != "en":
            en_line = await ollama_translate(original, source_code=lang_code, target_code="en")
            prompt = f"""Extract only the task item from this English command. One line, no trailing punctuation.

"{en_line}"
"""
            response = await llm_model.generate_content_async(prompt)
            task_en = response.text.strip()
        else:
            prompt = f"""The user speaks in {lang_name}.
Extract only the task item. Return just the task text, nothing else, no punctuation at the end:

"{original}"
"""
            response = await llm_model.generate_content_async(prompt)
            task_en = response.text.strip()

        if USE_ENGLISH_PIVOT and lang_code != "en":
            task = await ollama_translate(task_en, source_code="en", target_code=lang_code)
        else:
            task = task_en

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[ ] {task}  — added {timestamp}\n"

        with open(TODO_FILE, "a", encoding="utf-8") as f:
            f.write(line)

        with open(TODO_FILE, "r", encoding="utf-8") as f:
            all_tasks = [l.strip() for l in f.readlines() if l.strip()]

        return {"success": True, "task": task, "allTasks": all_tasks}
    except Exception as e:
        print("Todo error:", e)
        return JSONResponse(status_code=500, content={"error": "Failed to add task"})

@app.get("/api/todos")
async def get_todos():
    try:
        if not os.path.exists(TODO_FILE):
            return {"tasks": []}
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            tasks = [l.strip() for l in f.readlines() if l.strip()]
        return {"tasks": tasks}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Could not read list"})

@app.delete("/api/todos")
async def clear_todos():
    try:
        with open(TODO_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return {"success": True, "tasks": []}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Could not clear list"})

# Must be at the very bottom so it doesn't mask API routes
# Serve static files (project root)
app.mount("/images", StaticFiles(directory=os.path.join(PROJECT_DIR, 'images')), name="images")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(PROJECT_DIR, 'index.html'))
    
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return FileResponse(os.path.join(PROJECT_DIR, 'index.html'))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    print(f"Starting server on port {port}")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
