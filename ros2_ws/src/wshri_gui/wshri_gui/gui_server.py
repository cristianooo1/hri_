#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import functools
import json
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import cv2
import rclpy
from rclpy.node import Node

from . import cv as cv_module
from . import llm


def _resolve_web_dir() -> Path:
    candidate = Path(__file__).resolve().parents[1] / "web"
    if candidate.exists():
        return candidate

    try:
        from ament_index_python.packages import get_package_share_directory

        return Path(get_package_share_directory("wshri_gui")) / "web"
    except Exception:
        pass

    return candidate


class CvRuntime:
    def __init__(self, camera_index: int = 0) -> None:
        self._camera_index = camera_index
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._latest_jpeg = None
        self._latest_raw_jpeg = None
        self._latest_packet = {"frame_id": 0, "num_objects": 0, "objects": []}
        self._status = "idle"
        self._error = ""

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_status(self) -> dict[str, object]:
        with self._lock:
            packet = json.loads(json.dumps(self._latest_packet))
            return {
                "status": self._status,
                "error": self._error,
                "frame_id": packet.get("frame_id", 0),
                "num_objects": packet.get("num_objects", 0),
                "objects": packet.get("objects", []),
            }

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def get_raw_frame(self) -> bytes | None:
        with self._lock:
            return self._latest_raw_jpeg

    def _run(self) -> None:
        cap = None
        try:
            self._set_status("loading", "")
            model = cv_module.load_model()
            stabilizer = cv_module.TrackStabilizer(
                min_stable_frames=cv_module.MIN_STABLE_FRAMES,
                max_missing_frames=cv_module.MAX_MISSING_FRAMES,
                smoothing_alpha=cv_module.SMOOTHING_ALPHA,
            )

            cap = self._open_camera()
            if not cap.isOpened():
                raise RuntimeError("Could not open the webcam for CV processing.")

            frame_id = 0
            self._set_status("running", "")
            last_seen = []

            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self._set_status("error", "Could not read a frame from the webcam.")
                    time.sleep(0.2)
                    continue

                raw_detections = cv_module.process_frame(model, frame)
                stable_tracks = stabilizer.update(raw_detections)
                stable_tracks = cv_module.remove_spatial_duplicates(stable_tracks)
                stable_tracks = cv_module.add_position_tags(stable_tracks, frame.shape)
                scene_summary = cv_module.build_scene_summary(stable_tracks)

                current_seen = sorted([t["label"] for t in stable_tracks])
                if current_seen != last_seen:
                    print(f"\n[SCENE CHANGE] Now seeing: {current_seen}")
                    last_seen = current_seen

                raw_ok, raw_encoded = cv2.imencode(".jpg", frame)
                # annotated = cv_module.draw_grid(frame.copy())
                annotated = frame.copy()
                annotated = cv_module.draw_tracks(annotated, stable_tracks)
                frame_id += 1

                ok, encoded = cv2.imencode(".jpg", annotated)
                if not ok:
                    continue

                packet = cv_module.build_scene_packet(frame_id, scene_summary)
                if frame_id % 30 == 0 and len(stable_tracks) > 0:
                    print(f"[SERVER] Heartbeat: Frame {frame_id} | Stabilized Objects: {[t['label'] for t in stable_tracks]}")
                with self._lock:
                    self._latest_packet = packet
                    self._latest_jpeg = encoded.tobytes()
                    self._latest_raw_jpeg = raw_encoded.tobytes() if raw_ok else None
                    self._status = "running"
                    self._error = ""
        except Exception as exc:
            self._set_status("error", str(exc))
        finally:
            if cap is not None:
                cap.release()

    def _set_status(self, status: str, error: str) -> None:
        with self._lock:
            self._status = status
            self._error = error

    def _open_camera(self):
        backends = []
        if hasattr(cv2, "CAP_V4L2"):
            backends.append(cv2.CAP_V4L2)
        backends.append(cv2.CAP_ANY)

        for backend in backends:
            cap = cv2.VideoCapture(self._camera_index, backend)
            if cap.isOpened():
                return cap
            cap.release()

        return cv2.VideoCapture(self._camera_index)


def _build_handler(web_dir: Path, cv_runtime: CvRuntime):
    class GuiRequestHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            route = urlparse(self.path).path

            if route == "/api/detections":
                self._send_json(HTTPStatus.OK, cv_runtime.get_status())
                return

            if route == "/api/cv_frame":
                self._send_cv_frame()
                return

            if route == "/api/camera_frame":
                self._send_camera_frame()
                return

            if route == "/api/cv_stream":
                self._stream_cv_feed()
                return

            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
            route = urlparse(self.path).path

            if route == "/api/listen/start":
                try:
                    llm.start_recording()
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, {"status": "recording_started"})
                return

            if route == "/api/listen/stop":
                try:
                    user_text = llm.stop_and_transcribe()
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return

                if not user_text:
                    self._send_json(HTTPStatus.OK, {"reply": "No audio detected."})
                    return

                # --- NEW: Get real-time YOLO detections ---
                cv_status = cv_runtime.get_status()
                yolo_objects = cv_status.get("objects", [])
                inventory_list = [obj["label"] for obj in yolo_objects]

                try:
                    # Pass BOTH the text and the inventory to the LLM
                    # (Assumes llm.generate_response returns a parsed dictionary)
                    llm_response_dict = llm.generate_response(user_text, inventory_list)
                    
                    # Extract the spoken message for TTS
                    message_to_user = llm_response_dict.get("message_to_user", "I am having trouble processing that.")
                    
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return

                audio_error = ""
                try:
                    # ONLY pass the conversational text to the TTS, not the whole JSON
                    asyncio.run(llm.generate_and_play(message_to_user))
                except Exception as exc:
                    audio_error = str(exc)

                self._send_json(
                    HTTPStatus.OK,
                    {
                        "user_said": user_text,
                        "reply": message_to_user, # Send spoken text to GUI log
                        "llm_action": llm_response_dict.get("action"), # Tell GUI what state we are in
                        "target_item": llm_response_dict.get("target_item"), # Tell GUI what item we want
                        "audio_error": audio_error,
                    },
                )
                return

            if route == "/api/llm":
                try:
                    user_text = llm.stop_and_transcribe()
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return

                if not user_text:
                    self._send_json(HTTPStatus.OK, {"reply": "No audio detected."})
                    return

                # --- NEW: Get real-time YOLO detections ---
                cv_status = cv_runtime.get_status()
                yolo_objects = cv_status.get("objects", [])
                inventory_list = [obj["label"] for obj in yolo_objects]

                try:
                    # Pass BOTH the text and the inventory to the LLM
                    # (Assumes llm.generate_response returns a parsed dictionary)
                    llm_response_dict = llm.generate_response(user_text, inventory_list)
                    
                    # Extract the spoken message for TTS
                    message_to_user = llm_response_dict.get("message_to_user", "I am having trouble processing that.")
                    
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                    return

                audio_error = ""
                try:
                    # ONLY pass the conversational text to the TTS, not the whole JSON
                    asyncio.run(llm.generate_and_play(message_to_user))
                except Exception as exc:
                    audio_error = str(exc)

                self._send_json(
                    HTTPStatus.OK,
                    {
                        "user_said": user_text,
                        "reply": message_to_user, # Send spoken text to GUI log
                        "llm_action": llm_response_dict.get("action"), # Tell GUI what state we are in
                        "target_item": llm_response_dict.get("target_item"), # Tell GUI what item we want
                        "audio_error": audio_error,
                    },
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

        def _stream_cv_feed(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            try:
                while True:
                    frame = cv_runtime.get_frame()
                    if frame is None:
                        time.sleep(0.1)
                        continue

                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("utf-8"))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.08)
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_cv_frame(self) -> None:
            frame = cv_runtime.get_frame()
            if frame is None:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "No CV frame available yet")
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)

        def _send_camera_frame(self) -> None:
            frame = cv_runtime.get_raw_frame()
            if frame is None:
                self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, "No camera frame available yet")
                return

            self.send_response(HTTPStatus.OK)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return functools.partial(GuiRequestHandler, directory=str(web_dir))


class GuiServer(Node):
    def __init__(self, port: int, camera_index: int) -> None:
        super().__init__("wshri_gui_server")
        self._port = port
        self._camera_index = camera_index
        self._server = None
        self._thread = None
        self._cv_runtime = CvRuntime(camera_index)

    def start(self) -> None:
        web_dir = _resolve_web_dir()
        self._cv_runtime.start()
        handler = _build_handler(web_dir, self._cv_runtime)
        self._server = ThreadingHTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self.get_logger().info(f"GUI server running at http://localhost:{self._port}")
        self.get_logger().info(f"Serving {web_dir}")
        self.get_logger().info(f"CV camera index: {self._camera_index}")

    def stop(self) -> None:
        self._cv_runtime.stop()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def main() -> None:
    parser = argparse.ArgumentParser(description="WSHRI GUI static server")
    parser.add_argument("--port", type=int, default=3000, help="HTTP port")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index")
    args = parser.parse_args()

    rclpy.init()
    node = GuiServer(args.port, args.camera_index)
    node.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
