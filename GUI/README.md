# WSHRI GUI

This package serves a static dashboard UI that mirrors the planned robot visualization.

## Build and run (ROS 2)

```bash
colcon build --packages-select wshri_gui
source install/setup.bash
ros2 run wshri_gui gui_server --port 3000
```

## Run without ROS2
```bash
python3 gui_server.py
```
Open `http://localhost:3000` in your browser.
