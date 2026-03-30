# llm.py

import os
import io
import threading
import asyncio
import edge_tts
import pygame
import speech_recognition as sr
from faster_whisper import WhisperModel
from dotenv import load_dotenv
from google import genai

load_dotenv()

_whisper_model = None

_recording_buffer = []
_is_recording = False
_recorder_thread = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model

def generate_response(user_input: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: NO API KEY DETECTED")
        return "System Error: Missing API Key."

    client = genai.Client(api_key=api_key)

    full_prompt = (
        "You are a robot assistant. Context: There are 2 bananas on the table. "
        f"User says: {user_input}. Respond in one short, helpful sentence."
    )

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=full_prompt,
        )
        return response.text.strip()
    except Exception as e:
        return f"Gemini Error: {e}"

async def generate_and_play(text: str, voice: str = "en-US-JennyNeural"):
    if not text:
        return

    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""
    
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data = chunk.get("data")
            if data:
                audio_data += data
            
    audio_stream = io.BytesIO(audio_data)
    
    pygame.mixer.init()
    pygame.mixer.music.load(audio_stream)
    pygame.mixer.music.play()
    
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
        
    pygame.mixer.quit()

def start_recording():
    global _is_recording, _recording_buffer, _recorder_thread
    if _is_recording:
        return
    
    _is_recording = True
    _recording_buffer = [] 
    
    def record_task():
        r = sr.Recognizer()
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            print("--- MIC ACTIVE ---")
            while _is_recording:
                try:
                    audio = r.listen(source, phrase_time_limit=1, timeout=1)
                    _recording_buffer.append(audio.get_wav_data())
                except (sr.WaitTimeoutError, sr.UnknownValueError):
                    continue

    _recorder_thread = threading.Thread(target=record_task, daemon=True)
    _recorder_thread.start()

def stop_and_transcribe():
    global _is_recording, _recording_buffer
    _is_recording = False
    
    if _recorder_thread:
        _recorder_thread.join()
        print("################ MIC CLOSED ####################")
    
    if not _recording_buffer:
        print("Warning: No audio was captured.")
        return ""

    full_audio_bytes = b"".join(_recording_buffer)
    
    model = get_whisper_model()
    
    segments, _ = model.transcribe(io.BytesIO(full_audio_bytes), beam_size=5)
    
    result_text = " ".join([s.text for s in segments]).strip()
    
    _recording_buffer = []
    
    return result_text