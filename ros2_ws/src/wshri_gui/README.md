# WSHRI GUI

This package serves a static dashboard UI that mirrors the planned robot visualization.

## Build and run (ROS 2)

```bash
colcon build --packages-select wshri_gui
source install/setup.bash
ros2 run wshri_gui gui_server --port 3000
```

Open `http://localhost:3000` in your browser.

## Gemini integration

The GUI server exposes a local `POST /api/llm` endpoint used by the chat panel in the dashboard.

Set your Gemini key before launching the server:

```bash
export GEMINI_API_KEY=your_key_here
```

Or place it in a local `.env` file next to where you launch the server:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

If `GEMINI_API_KEY` or the `google-genai` package is missing, the dashboard still loads, but chat requests will return an error message in the UI.
