import os
import io
import sys
import threading
import asyncio
import tempfile
import json
from pydantic import BaseModel, Field
from pathlib import Path

try:
    from google import genai
    from google.genai import types  
except ImportError:
    genai = None
    types = None                   


def _add_project_venv_to_path():
    python_dir = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for parent in Path(__file__).resolve().parents:
        site_packages = parent / ".venv" / "lib" / python_dir / "site-packages"
        if site_packages.exists():
            site_packages_text = str(site_packages)
            if site_packages_text not in sys.path:
                sys.path.insert(0, site_packages_text)
            return


_add_project_venv_to_path()

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import pygame
except ImportError:
    pygame = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from google import genai
except ImportError:
    genai = None

if load_dotenv is not None:
    load_dotenv()

_whisper_model = None

_recording_buffer = []
_is_recording = False
_recorder_thread = None
_recording_error = None
_recording_sample_rate = 16000
_recording_sample_width = 2

def get_whisper_model():
    global _whisper_model
    if WhisperModel is None:
        raise RuntimeError("faster-whisper is not installed on the GUI host.")
    if _whisper_model is None:
        _whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
    return _whisper_model


API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None

class RobotResponse(BaseModel):
    user_intent: str
    action: str = Field(description="Must be: ask_confirmation, fetch_item, or dialogue")
    target_item: str | None = Field(description="The item requested, or null if none")
    internal_reasoning: str
    message_to_user: str


def generate_response(user_input: str, yolo_detections: list):
    if client is None:
        return {"error": "Missing API Key", "message_to_user": "System Error: Missing API Key."}

    inventory = ", ".join(yolo_detections) if yolo_detections else "nothing"

    # Notice we removed the [OUTPUT] instructions because the Pydantic schema handles it
    system_instruction = f"""
    You are a helpful robot assistant. 
    [ENVIRONMENT] Current items on counter: {inventory}
    
    [RULES]
    1. Mandatory Confirmation: If a user asks for an item (either directly or by describing it), you must first explicitly state the specific item from the [ENVIRONMENT] that matches their request, and then ask 'Are you sure?' before fetching.
    2. Inventory: Only fetch items in the [ENVIRONMENT]. If missing, suggest what is available.
    3. Semantic: Match attributes to items.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type='application/json',
                response_schema=RobotResponse, # <--- This guarantees perfect JSON with no backticks
                temperature=0.2 # Lower temperature is usually better for strict logic tasks
            )
        )
        
        # response.text is now guaranteed to be a clean JSON string
        return json.loads(response.text)
    
    except Exception as e:
        print(f"[\033[91mERROR\033[0m] Gemini API failed: {repr(e)}")
        return {"error": str(e), "message_to_user": "I encountered a system error."}

async def generate_and_play(text: str, voice: str = "en-US-JennyNeural"):
    if not text:
        return
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed on the GUI host.")
    if pygame is None:
        raise RuntimeError("pygame is not installed on the GUI host.")

    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data = chunk.get("data")
            if data:
                audio_data += data

    if not audio_data:
        raise RuntimeError("TTS returned no audio data.")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as audio_file:
        audio_file.write(audio_data)
        audio_path = audio_file.name

    try:
        pygame.mixer.init()
        pygame.mixer.music.load(audio_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    finally:
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except pygame.error:
            pass
        try:
            os.unlink(audio_path)
        except OSError:
            pass

def start_recording():
    global _is_recording, _recording_buffer, _recorder_thread, _recording_error
    if sr is None:
        raise RuntimeError("SpeechRecognition is not installed on the GUI host.")
    if _is_recording:
        return

    _is_recording = True
    _recording_buffer = []
    _recording_error = None

    def record_task():
        global _recording_error
        r = sr.Recognizer()

        r.energy_threshold = 150 
        r.dynamic_energy_threshold = False

        try:
            with sr.Microphone(device_index=7) as source:
                # r.adjust_for_ambient_noise(source, duration=0.5)
                print("--- MIC ACTIVE ---")
                while _is_recording:
                    try:
                        audio = r.listen(source, phrase_time_limit=5, timeout=1)
                        _recording_buffer.append(
                            audio.get_raw_data(
                                convert_rate=_recording_sample_rate,
                                convert_width=_recording_sample_width,
                            )
                        )
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as exc:
                        _recording_error = f"Microphone capture failed: {exc}"
                        break
        except Exception as exc:
            _recording_error = f"Microphone unavailable: {exc}"

    _recorder_thread = threading.Thread(target=record_task, daemon=True)
    _recorder_thread.start()

def stop_and_transcribe():
    global _is_recording, _recording_buffer, _recorder_thread, _recording_error
    if sr is None:
        raise RuntimeError("SpeechRecognition is not installed on the GUI host.")
    _is_recording = False

    if _recorder_thread:
        _recorder_thread.join()
        print("################ MIC CLOSED ####################")

    if _recording_error:
        raise RuntimeError(_recording_error)

    if not _recording_buffer:
        print("Warning: No audio was captured.")
        return ""

    full_audio_bytes = b"".join(_recording_buffer)
    audio_data = sr.AudioData(
        full_audio_bytes,
        _recording_sample_rate,
        _recording_sample_width,
    )
    print("--> Loading Whisper model (this may take a minute if downloading)...")
    model = get_whisper_model()

    print("--> Transcribing audio on CPU...")
    segments, _ = model.transcribe(
        io.BytesIO(audio_data.get_wav_data()),
        beam_size=5,
        language="en",     # 1. Force English to stop foreign character hallucinations
        vad_filter=True,
        initial_prompt="robot, arm, pick, place, apple, banana, orange, broccoli, carrot."
    )

    result_text = " ".join([s.text for s in segments]).strip()
    print(f"--> Transcribed: '{result_text}'")

    _recording_buffer = []
    _recorder_thread = None

    return result_text


if WhisperModel is not None:
    print("Pre-loading Whisper model into memory...")
    get_whisper_model()