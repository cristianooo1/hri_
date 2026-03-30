import os
import io
import asyncio
import edge_tts
import pygame
import speech_recognition as sr
from faster_whisper import WhisperModel
from dotenv import load_dotenv
from google import genai

import pyttsx3

def generate_response():
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR NO API KEY DETECTED")
        return

    client = genai.Client(api_key=api_key)

    prompt = "You are a robot assistant. You must provide help to the user. On the table the camera sees 2 bananas, but the user insists on wanting the apple. What do you do in this situation? Provide a simple answer that consists of only 1 sentence."

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
        )
        
        print("\n Gemini Response:")
        print(response.text)
        return response.text
        
    except Exception as e:
        print(f"ERROR: {e}")
        return
    
async def generate_and_play(text: str, voice: str = "en-US-JennyNeural"):
    
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


def listen_and_transcribe():
    print("Loading AI speech model... (This takes a few seconds)")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    print("Model loaded successfully!")

    r = sr.Recognizer()

    with sr.Microphone() as source:
        print("\nCalibrating microphone for background noise...")
        r.adjust_for_ambient_noise(source, duration=2)
        
        print("\n LISTENING... (Speak into the microphone)")
        # The script will pause here and listen. 
        # It automatically stops recording when you stop talking
        audio = r.listen(source)
        
        print("Processing your speech...")

    wav_bytes = audio.get_wav_data()
    audio_buffer = io.BytesIO(wav_bytes)
    audio_buffer.name = "audio.wav" 

    segments, info = model.transcribe(audio_buffer, beam_size=5)

    transcription = ""
    for segment in segments:
        transcription += segment.text + " "

    return transcription.strip()


def main():
    # response = generate_response()

    # response = "I am your robot assistant, I am ready to help you."
    # asyncio.run(generate_and_play(response))

    # engine = pyttsx3.init()
    # engine.say("I am processing your request.")
    # engine.runAndWait()

    user_input = listen_and_transcribe()
    
    print("\n" + "="*40)
    print(f"USER SAID: {user_input}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()