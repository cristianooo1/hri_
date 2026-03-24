#!/usr/bin/env python3
import argparse
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import rclpy
from rclpy.node import Node


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


class GuiServer(Node):
    def __init__(self, port: int) -> None:
        super().__init__("wshri_gui_server")
        self._port = port
        self._server = None
        self._thread = None

    def start(self) -> None:
        web_dir = _resolve_web_dir()
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(web_dir))
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
