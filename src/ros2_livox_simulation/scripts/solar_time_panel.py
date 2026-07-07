#!/usr/bin/python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from urllib.parse import parse_qs, urlparse

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32


TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*$")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def normalize_time_text(raw_text: str) -> str:
    match = TIME_RE.match(raw_text or "")
    if not match:
        raise ValueError("expected HH:MM in 24-hour format")

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    if hour > 23 or minute > 59:
        raise ValueError("time is out of range")
    return f"{hour:02d}:{minute:02d}"


def text_to_minutes(time_text: str) -> int:
    normalized = normalize_time_text(time_text)
    hour_text, minute_text = normalized.split(":")
    return int(hour_text) * 60 + int(minute_text)


def minutes_to_text(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def minutes_to_hours(total_minutes: int) -> float:
    return float(total_minutes % (24 * 60)) / 60.0


def phase_text(total_minutes: int) -> str:
    hour_value = minutes_to_hours(total_minutes)
    if 6.0 <= hour_value < 8.0:
        return "Sunrise"
    if 8.0 <= hour_value < 17.0:
        return "Daytime"
    if 17.0 <= hour_value < 19.5:
        return "Sunset"
    return "Night"


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() not in ("", "0", "false", "no", "off")


class SolarTimePanel(Node):
    def __init__(self, topic_name: str, initial_time: str) -> None:
        super().__init__("solar_time_panel")
        self.topic_name = topic_name
        self.current_minutes = text_to_minutes(initial_time)
        self.last_published_minutes: int | None = self.current_minutes
        self.publisher = self.create_publisher(Float32, topic_name, 10)
        self._lock = Lock()

    def state_payload(self) -> dict[str, object]:
        with self._lock:
            return self._state_payload_unlocked()

    def _state_payload_unlocked(self) -> dict[str, object]:
        total_minutes = self.current_minutes % (24 * 60)
        return {
            "minutes": total_minutes,
            "time_text": minutes_to_text(total_minutes),
            "hours": minutes_to_hours(total_minutes),
            "phase": phase_text(total_minutes),
            "topic": self.topic_name,
        }

    def set_current_minutes(self, total_minutes: int, force: bool = False) -> dict[str, object]:
        total_minutes %= 24 * 60
        with self._lock:
            self.current_minutes = total_minutes
            if not force and total_minutes == self.last_published_minutes:
                return self._state_payload_unlocked()

            msg = Float32()
            msg.data = minutes_to_hours(total_minutes)
            self.publisher.publish(msg)
            self.last_published_minutes = total_minutes
            return self._state_payload_unlocked()


class SolarTimeHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, request_handler_class, panel: SolarTimePanel):
        super().__init__(server_address, request_handler_class)
        self.panel = panel


def render_page(panel: SolarTimePanel) -> str:
    state = panel.state_payload()
    initial_state = json.dumps(state, ensure_ascii=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Map Sim Solar Time</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{
      margin: 0;
      background: #0f1116;
      color: #e6e8ee;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      padding: 28px 24px 36px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 24px;
      font-weight: 700;
    }}
    p {{
      margin: 0;
      color: #aab2c3;
      line-height: 1.5;
    }}
    .band {{
      margin-top: 22px;
      padding: 18px 20px;
      background: #171b24;
      border: 1px solid #242a36;
      border-radius: 8px;
    }}
    .status {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric {{
      padding: 14px 16px;
      background: #11151d;
      border: 1px solid #212733;
      border-radius: 8px;
    }}
    .metric span {{
      display: block;
      color: #93a0b8;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      font-size: 20px;
      font-weight: 700;
    }}
    .slider-wrap {{
      margin-top: 18px;
    }}
    input[type="range"] {{
      width: 100%;
      margin: 8px 0 10px;
    }}
    .ticks {{
      display: flex;
      justify-content: space-between;
      color: #8190a8;
      font-size: 12px;
    }}
    .row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-top: 18px;
    }}
    input[type="text"] {{
      width: 92px;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid #2d3545;
      background: #0d1118;
      color: #eef2ff;
      font-size: 16px;
      text-align: center;
    }}
    button {{
      padding: 10px 14px;
      border: 1px solid #334058;
      border-radius: 8px;
      background: #1b2330;
      color: #eef2ff;
      font-size: 14px;
      cursor: pointer;
    }}
    button:hover {{
      background: #233046;
    }}
    .presets {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 18px;
    }}
    .topic {{
      margin-top: 18px;
      color: #93a0b8;
      font-size: 13px;
    }}
    .hint {{
      margin-top: 12px;
      color: #7e8aa1;
      font-size: 13px;
    }}
    .error {{
      color: #ff8d8d;
      min-height: 20px;
      margin-top: 10px;
      font-size: 13px;
    }}
    @media (max-width: 640px) {{
      main {{
        padding: 20px 16px 28px;
      }}
      .status {{
        grid-template-columns: 1fr;
      }}
      .row {{
        align-items: stretch;
      }}
      input[type="text"], button {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Solar Time Control</h1>
    <p>Realtime equator sun control. World frame is +X east, -X west, +Y north, +Z up.</p>

    <section class="band">
      <div class="status">
        <div class="metric">
          <span>Time</span>
          <strong id="timeText">--:--</strong>
        </div>
        <div class="metric">
          <span>Phase</span>
          <strong id="phaseText">--</strong>
        </div>
        <div class="metric">
          <span>Hours</span>
          <strong id="hourText">--</strong>
        </div>
      </div>

      <div class="slider-wrap">
        <input id="timeSlider" type="range" min="0" max="1439" step="1" value="0">
        <div class="ticks">
          <span>00:00</span>
          <span>06:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>23:59</span>
        </div>
      </div>

      <div class="row">
        <input id="timeInput" type="text" value="12:00" inputmode="numeric" spellcheck="false">
        <button id="applyButton" type="button">Apply Time</button>
        <button id="publishButton" type="button">Publish Current</button>
      </div>

      <div class="presets">
        <button type="button" data-preset="00:00">00:00</button>
        <button type="button" data-preset="06:00">06:00</button>
        <button type="button" data-preset="12:00">12:00</button>
        <button type="button" data-preset="18:00">18:00</button>
        <button type="button" data-preset="21:00">21:00</button>
      </div>

      <div class="topic" id="topicText"></div>
      <div class="hint">Slider changes publish continuously with a short debounce.</div>
      <div class="error" id="errorText"></div>
    </section>
  </main>

  <script>
    const initialState = {initial_state};
    const slider = document.getElementById("timeSlider");
    const timeInput = document.getElementById("timeInput");
    const timeText = document.getElementById("timeText");
    const phaseText = document.getElementById("phaseText");
    const hourText = document.getElementById("hourText");
    const topicText = document.getElementById("topicText");
    const errorText = document.getElementById("errorText");
    let debounceTimer = null;

    function renderState(state) {{
      slider.value = state.minutes;
      timeInput.value = state.time_text;
      timeText.textContent = state.time_text;
      phaseText.textContent = state.phase;
      hourText.textContent = state.hours.toFixed(2);
      topicText.textContent = `Publishing topic: ${{state.topic}}`;
    }}

    function showError(message) {{
      errorText.textContent = message || "";
    }}

    async function postTime(minutes, force = false) {{
      showError("");
      const response = await fetch("/api/time", {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify({{minutes, force}})
      }});
      const payload = await response.json();
      if (!response.ok) {{
        throw new Error(payload.error || "request failed");
      }}
      renderState(payload);
    }}

    function scheduleSliderPublish() {{
      const minutes = Number(slider.value);
      renderState({{
        minutes,
        time_text: minutesToText(minutes),
        hours: minutes / 60.0,
        phase: phaseForMinutes(minutes),
        topic: initialState.topic
      }});
      if (debounceTimer) {{
        clearTimeout(debounceTimer);
      }}
      debounceTimer = setTimeout(async () => {{
        try {{
          await postTime(minutes, false);
        }} catch (error) {{
          showError(error.message);
        }}
      }}, 80);
    }}

    function minutesToText(minutes) {{
      minutes = ((minutes % 1440) + 1440) % 1440;
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      return `${{String(hours).padStart(2, "0")}}:${{String(mins).padStart(2, "0")}}`;
    }}

    function phaseForMinutes(minutes) {{
      const hourValue = (((minutes % 1440) + 1440) % 1440) / 60.0;
      if (hourValue >= 6.0 && hourValue < 8.0) return "Sunrise";
      if (hourValue >= 8.0 && hourValue < 17.0) return "Daytime";
      if (hourValue >= 17.0 && hourValue < 19.5) return "Sunset";
      return "Night";
    }}

    async function applyText(force = false) {{
      try {{
        const value = timeInput.value.trim();
        const match = value.match(/^(\\d{{1,2}})(?::(\\d{{2}}))?$/);
        if (!match) {{
          throw new Error("expected HH:MM in 24-hour format");
        }}
        const hour = Number(match[1]);
        const minute = Number(match[2] || "0");
        if (hour > 23 || minute > 59) {{
          throw new Error("time is out of range");
        }}
        await postTime(hour * 60 + minute, force);
      }} catch (error) {{
        showError(error.message);
      }}
    }}

    slider.addEventListener("input", scheduleSliderPublish);
    document.getElementById("applyButton").addEventListener("click", () => applyText(false));
    document.getElementById("publishButton").addEventListener("click", () => applyText(true));
    timeInput.addEventListener("keydown", (event) => {{
      if (event.key === "Enter") {{
        event.preventDefault();
        applyText(false);
      }}
    }});

    document.querySelectorAll("[data-preset]").forEach((button) => {{
      button.addEventListener("click", async () => {{
        timeInput.value = button.dataset.preset;
        await applyText(false);
      }});
    }});

    renderState(initialState);
  </script>
</body>
</html>
"""


class SolarTimeRequestHandler(BaseHTTPRequestHandler):
    server: SolarTimeHTTPServer

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, html_text: str) -> None:
        body = html_text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write_html(render_page(self.server.panel))
            return
        if parsed.path == "/api/state":
            self._write_json(HTTPStatus.OK, self.server.panel.state_payload())
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/time":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            content_type = self.headers.get("Content-Type", "")
            if "application/json" in content_type:
                payload = json.loads(raw_body or "{}")
            else:
                payload = {key: value[-1] for key, value in parse_qs(raw_body).items()}

            if "minutes" in payload:
                total_minutes = int(payload["minutes"])
            elif "time_text" in payload:
                total_minutes = text_to_minutes(str(payload["time_text"]))
            else:
                raise ValueError("minutes or time_text is required")

            force_raw = payload.get("force", False)
            force = bool(force_raw) if isinstance(force_raw, bool) else is_truthy(str(force_raw))
            state = self.server.panel.set_current_minutes(total_minutes, force=force)
            self._write_json(HTTPStatus.OK, state)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid json body"})


def maybe_open_browser(url: str) -> None:
    if not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
        return
    if not is_truthy(os.getenv("MAP_SIM_SOLAR_TIME_PANEL_OPEN_BROWSER", "1")):
        return

    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen(
            [opener, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def build_server(panel: SolarTimePanel, host: str, preferred_port: int) -> SolarTimeHTTPServer:
    try:
        return SolarTimeHTTPServer((host, preferred_port), SolarTimeRequestHandler, panel)
    except OSError:
        return SolarTimeHTTPServer((host, 0), SolarTimeRequestHandler, panel)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial-time", default="12:00")
    parser.add_argument("--topic", default="/map_sim/solar_time_hours")
    parser.add_argument("--host", default=os.getenv("MAP_SIM_SOLAR_TIME_PANEL_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MAP_SIM_SOLAR_TIME_PANEL_PORT", str(DEFAULT_PORT))),
    )
    cli_args = rclpy.utilities.remove_ros_args(args=sys.argv)[1:]
    args, unknown_args = parser.parse_known_args(cli_args)
    if unknown_args:
        raise ValueError(f"unrecognized arguments: {' '.join(unknown_args)}")

    initial_time = normalize_time_text(args.initial_time)

    stop_event = Event()
    httpd: SolarTimeHTTPServer | None = None
    try:
        rclpy.init(args=None)
        panel = SolarTimePanel(args.topic, initial_time)
        httpd = build_server(panel, args.host, args.port)
        server_host, server_port = httpd.server_address
        url = f"http://{server_host}:{server_port}/"
        print(f"[INFO] solar time control ready: {url}", flush=True)
        print(f"[INFO] publishing topic: {args.topic}", flush=True)
        maybe_open_browser(url)

        def handle_signal(_signum, _frame) -> None:
            if stop_event.is_set():
                return
            stop_event.set()
            if httpd is not None:
                httpd.shutdown()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        httpd.serve_forever(poll_interval=0.2)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"[ERR] solar time panel failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if httpd is not None:
            httpd.server_close()
        if "panel" in locals():
            panel.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
