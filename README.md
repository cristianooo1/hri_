Project setup:

1. install uv

go to https://github.com/astral-sh/uv and follow the instructions to install uv

1. clone the project and install dependencies

go to your workspace (the folder where you want to clone the project)

run:
```
git clone git@github.com:cristianooo1/hri_.git
cd hri_
uv sync
cd ros2_ws
colcon build --symlink-install --packages-select wshri_gui
source install/setup.bash
cd ..
```


in the root folder create a **.env** to add the gemini api key:
```
GEMINI_API_KEY = "your_gemini_api_key"
```



```
source /opt/ros/jazzy/setup.bash 
source ros2_ws/install/setup.bash
uv run ros2 run wshri_gui gui_server
```


1. get_whisper_model()
- function that checks if _whisper_model has been loaded yet. If not, it loads it once. Every subsequent time you call it, it returns the model already sitting in memory.

2. generate_response(user_input)
- function that takes the text string (what the user said) and wraps it in a "System Prompt" that gives the robot its personality and context
- Output: Returns a clean, single-sentence string from the AI.

3. generate_and_play(text, voice)
- function that uses edge_tts to communicate with Microsoft's servers to turn text into high-quality audio data.

4. start_recording()
- function that flips a switch (_is_recording = True) and launches a Background Thread.
- The thread sits in the background, grabbing 1-second "chunks" of audio from the microphone and shoving them into a list called _recording_buffer.

5. stop_and_transcribe()
- function that flips the switch to False, which tells the background thread to stop.
- Joins the thread (waits for it to finish its last 1-second chunk).
- Stitches all those small audio chunks into one large byte stream.
- Feeds that stream into the Whisper Model to turn the audio into actual text.
- Clears the buffer so the next recording starts fresh.