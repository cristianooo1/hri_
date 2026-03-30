#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import functools
import json
import os
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import rclpy
from rclpy.node import Node

from . import llm

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

try:
    from google import genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None


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

def _build_handler(web_dir: Path):
    class GuiRequestHandler(SimpleHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
            
            # 1. PUSH-TO-TALK: START THE RECORDING
            if self.path == "/api/listen/start":
                llm.start_recording()
                self._send_json(HTTPStatus.OK, {"status": "recording_started"})
                return
            
            # 2. PUSH-TO-TALK: STOP & PROCESS 
            elif self.path == "/api/listen/stop":
                # Get text from Whisper
                user_text = llm.stop_and_transcribe()
                
                if not user_text:
                    self._send_json(HTTPStatus.OK, {"reply": "No audio detected."})
                    return
                
                ai_reply = llm.generate_response(user_text)
                asyncio.run(llm.generate_and_play(ai_reply))

                self._send_json(HTTPStatus.OK, {
                    "user_said": user_text,
                    "reply": ai_reply
                })
                return
            
            # 3. TEXT-ONLY INTERACTION 
            elif self.path == "/api/llm":
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                    prompt = str(payload.get("prompt", "")).strip()
                    
                    if not prompt:
                        self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Prompt required."})
                        return

                    reply = llm.generate_response(prompt)
                    
                    self._send_json(HTTPStatus.OK, {"reply": reply})
                except Exception as exc:
                    self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                return

            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

        def _send_json(self, status: HTTPStatus, payload: dict[str, str]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return functools.partial(GuiRequestHandler, directory=str(web_dir))


class GuiServer(Node):
    def __init__(self, port: int) -> None:
        super().__init__("wshri_gui_server")
        self._port = port
        self._server = None
        self._thread = None

    def start(self) -> None:
        web_dir = _resolve_web_dir()
        handler = _build_handler(web_dir)
        self._server = ThreadingHTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        self.get_logger().info(f"GUI server running at http://localhost:{self._port}")
        self.get_logger().info(f"Serving {web_dir}")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def main() -> None:
    parser = argparse.ArgumentParser(description="WSHRI GUI static server")
    parser.add_argument("--port", type=int, default=3000, help="HTTP port")
    args = parser.parse_args()

    rclpy.init()
    node = GuiServer(args.port)
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
