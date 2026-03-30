#!/usr/bin/env python3
from __future__ import annotations

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

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

try:
    from google import genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None


def _resolve_web_dir() -> Path:
    try:
        from ament_index_python.packages import get_package_share_directory

        share_dir = Path(get_package_share_directory("wshri_gui"))
        candidate = share_dir / "web"
        if candidate.exists():
            return candidate
    except Exception:
        pass

    return Path(__file__).resolve().parents[1] / "web"


class GeminiClient:
    def __init__(self) -> None:
        if load_dotenv is not None:
            load_dotenv()

        self._api_key = os.getenv("GEMINI_API_KEY")
        self._model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self._system_prompt = os.getenv(
            "GEMINI_SYSTEM_PROMPT",
            (
                "You are the assistant for a robot visualization dashboard. "
                "Answer briefly, stay grounded in the observed scene, and if "
                "the user requests an object that is not visible, explain that "
                "constraint and propose the closest valid next step."
            ),
        )

    def is_ready(self) -> tuple[bool, str]:
        if genai is None:
            return False, "The google-genai package is not installed on the GUI host."
        if not self._api_key:
            return False, "GEMINI_API_KEY is not set. Add it to your environment or .env file."
        return True, ""

    def generate(self, prompt: str) -> str:
        ready, message = self.is_ready()
        if not ready:
            raise RuntimeError(message)

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=f"{self._system_prompt}\n\nUser: {prompt}",
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()


def _build_handler(web_dir: Path, gemini_client: GeminiClient):
    class GuiRequestHandler(SimpleHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
            if self.path != "/api/llm":
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)

            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Request body must be valid JSON."},
                )
                return

            prompt = str(payload.get("prompt", "")).strip()
            if not prompt:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "Prompt is required."},
                )
                return

            try:
                reply = gemini_client.generate(prompt)
            except Exception as exc:
                self._send_json(
                    HTTPStatus.BAD_GATEWAY,
                    {"error": str(exc)},
                )
                return

            self._send_json(HTTPStatus.OK, {"reply": reply})

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
        self._gemini_client = GeminiClient()

    def start(self) -> None:
        web_dir = _resolve_web_dir()
        handler = _build_handler(web_dir, self._gemini_client)
        self._server = ThreadingHTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        llm_ready, llm_message = self._gemini_client.is_ready()
        self.get_logger().info(f"GUI server running at http://localhost:{self._port}")
        self.get_logger().info(f"Serving {web_dir}")
        if llm_ready:
            self.get_logger().info("Gemini endpoint ready at /api/llm")
        else:
            self.get_logger().warning(f"Gemini endpoint disabled: {llm_message}")

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
