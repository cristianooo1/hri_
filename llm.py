import os
from dotenv import load_dotenv
from google import genai

def main():
    load_dotenv()
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR NO API KEY DETECTED")
        return

    client = genai.Client(api_key=api_key)

    prompt = "You are a robot assistant. You must provide help to the user. On the table the camera sees 2 bananas, but the user insists on wanting the apple. What do you do in this situation?"

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
        )
        
        print("\n Gemini Response:")
        print(response.text)
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()