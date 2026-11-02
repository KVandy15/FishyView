"""FishyView window: dewarp, menus, and hover playback controls."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import sys
import tempfile
import threading
import time
import wave
from ctypes import wintypes
from pathlib import Path

import av
import numpy as np
import pygame
import moderngl

from fishyview.camera import FOV_START, LABELS, basis, start_pose, turn, zoom
from fishyview.layout import (
    BAR_H,
    ITEM_H,
    MENU_H,
    dropdown,
    dropdown_item,
    hit,
    menu_bar,
    place_popup,
    transport,
)

APP = "FishyView"
KEY_SPEED = 520.0
KEY_SPEED_FAST = 1250.0


def raise_window(hwnd: int) -> None:
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    user.ShowWindow(hwnd, 9)
    foreground = user.GetForegroundWindow()
    foreground_thread = user.GetWindowThreadProcessId(foreground, None)
    this_thread = kernel.GetCurrentThreadId()
    user.AttachThreadInput(foreground_thread, this_thread, True)
    user.SetForegroundWindow(hwnd)
    user.BringWindowToTop(hwnd)
    user.AttachThreadInput(foreground_thread, this_thread, False)


def alert(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, APP, 0x40)


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    ctypes.windll.user32.MessageBoxW(0, message, APP, 0x10)
    raise SystemExit(1)


def fmt(seconds: float) -> str:
    if not np.isfinite(seconds) or seconds < 0:
        seconds = 0
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def recent_file() -> Path:
    root = Path(os.environ.get("APPDATA", str(Path.home())))
    return root / APP / "recent.json"


def load_recent() -> list[str]:
    try:
        data = json.loads(recent_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)][:8]


def save_recent(paths: list[str]) -> None:
    dest = recent_file()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(paths[:8], indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Could not save the recent list: {exc}", flush=True)


def settings_file() -> Path:
    return recent_file().parent / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def orientation_for(path: Path) -> str:
    saved = load_settings().get("orientation", {})
    mode = saved.get(str(path)) if isinstance(saved, dict) else None
    return mode if mode in LABELS else "down"


def save_orientation(path: Path, mode: str) -> None:
    data = load_settings()
    saved = data.get("orientation")
    if not isinstance(saved, dict):
        saved = {}
    saved[str(path)] = mode
    data["orientation"] = saved
    dest = settings_file()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Could not save the mount: {exc}", flush=True)


def choose_video(owner: int) -> str | None:
    class OpenFileName(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    buffer = ctypes.create_unicode_buffer(32768)
    pattern = ctypes.create_unicode_buffer("Video\0*.mp4;*.mkv;*.mov;*.avi;*.webm\0All files\0*.*\0")
    dialog = OpenFileName()
    dialog.lStructSize = ctypes.sizeof(OpenFileName)
    dialog.hwndOwner = owner
    dialog.lpstrFilter = ctypes.cast(pattern, wintypes.LPCWSTR)
    dialog.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    dialog.nMaxFile = 32768
    dialog.Flags = 0x80000 | 0x1000 | 0x800
    dialog.lpstrTitle = "Open video"
    dialog.lpstrDefExt = "mp4"
    comdlg = ctypes.windll.comdlg32
    comdlg.GetOpenFileNameW.argtypes = [ctypes.POINTER(OpenFileName)]
    comdlg.GetOpenFileNameW.restype = wintypes.BOOL
    if not comdlg.GetOpenFileNameW(ctypes.byref(dialog)):
        code = comdlg.CommDlgExtendedError()
        if code:
            alert(f"The file dialog failed ({code}).")
        return None
    return buffer.value or None


class Decoder(threading.Thread):
    def __init__(self, path: Path):
        super().__init__(daemon=True)
        self.path = path
        self.frames: queue.Queue[tuple[int, float, np.ndarray]] = queue.Queue(maxsize=3)
        self.commands: queue.Queue[tuple] = queue.Queue()
        self.lock = threading.Lock()
        self.generation = 0
        self.duration = 0.0
        self.alive = True
        self.eof = False
        self.error: Exception | None = None

    def request_seek(self, seconds: float) -> None:
        with self.lock:
            self.generation += 1
            generation = self.generation
            self.eof = False
        self._drain()
        self.commands.put(("seek", max(0.0, seconds), generation))

    def stop(self) -> None:
        self.alive = False
        self.commands.put(("stop",))
        self._drain()

    def _drain(self) -> None:
        while True:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                return

    def run(self) -> None:
        try:
            self._decode()
        except Exception as exc:
            self.error = exc

    def _decode(self) -> None:
        container = av.open(str(self.path))
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if container.duration:
            self.duration = container.duration / av.time_base
        elif stream.duration:
            self.duration = float(stream.duration * stream.time_base)
        packets = container.decode(stream)
        skip_until = None
        with self.lock:
            generation = self.generation
        try:
            while self.alive:
                try:
                    command = self.commands.get_nowait()
                except queue.Empty:
                    command = None
                if command and command[0] == "stop":
                    break
                if command and command[0] == "seek":
                    _, seconds, generation = command
                    skip_until = seconds
                    container.seek(int(seconds / stream.time_base), stream=stream, backward=True, any_frame=False)
                    packets = container.decode(stream)
                    continue
                try:
                    frame = next(packets)
                except StopIteration:
                    self.eof = True
                    time.sleep(0.03)
                    continue
                timestamp = float(frame.time) if frame.time is not None else 0.0
                if skip_until is not None and timestamp < skip_until - 0.04:
                    continue
                skip_until = None
                array = frame.to_ndarray(format="rgb24")
                if not array.flags["C_CONTIGUOUS"]:
                    array = np.ascontiguousarray(array)
                with self.lock:
                    if generation != self.generation:
                        continue
                while self.alive:
                    with self.lock:
                        if generation != self.generation:
                            break
                    try:
                        self.frames.put((generation, timestamp, array), timeout=0.05)
                        break
                    except queue.Full:
                        continue
        finally:
            container.close()


def extract_audio(path: Path) -> str | None:
    container = av.open(str(path))
    stream = next((item for item in container.streams if item.type == "audio"), None)
    if stream is None:
        container.close()
        return None
    resampler = av.audio.resampler.AudioResampler(format="s16", layout="stereo", rate=48000)
    pcm = bytearray()

    def take(result) -> None:
        if result is None:
            return
        frames = result if isinstance(result, list) else [result]
        for item in frames:
            array = item.to_ndarray()
            if array.ndim == 2 and array.shape[0] == 2:
                array = np.ascontiguousarray(array.T)
            pcm.extend(np.ascontiguousarray(array).tobytes())

    for frame in container.decode(stream):
        take(resampler.resample(frame))
    take(resampler.resample(None))
    container.close()
    if not pcm:
        return None
    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    handle.close()
    with wave.open(handle.name, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(pcm)
    return handle.name


FISHEYE_VS = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FISHEYE_FS = """
#version 330
uniform sampler2D u_tex;
uniform mat3 u_cam;
uniform float u_fov;
uniform float u_lens;
uniform float u_aspect;
in vec2 v_uv;
out vec4 frag;
void main() {
    vec2 ndc = v_uv * 2.0 - 1.0;
    float half_tan = tan(u_fov * 0.5);
    vec3 cam = normalize(vec3(ndc.x * u_aspect * half_tan, ndc.y * half_tan, 1.0));
    vec3 dir = u_cam * cam;
    if (dir.z <= 0.0) { frag = vec4(0.0, 0.0, 0.0, 1.0); return; }
    float theta = atan(length(dir.xy), dir.z);
    if (theta > u_lens) { frag = vec4(0.0, 0.0, 0.0, 1.0); return; }
    float radius = (theta / u_lens) * 0.5;
    float phi = atan(dir.y, dir.x);
    vec2 uv = vec2(0.5) + radius * vec2(cos(phi), sin(phi));
    frag = texture(u_tex, vec2(uv.x, 1.0 - uv.y));
}
"""

UI_VS = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
uniform vec2 u_res;
out vec2 v_uv;
void main() {
    vec2 ndc = vec2(in_pos.x / u_res.x * 2.0 - 1.0, 1.0 - in_pos.y / u_res.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
    v_uv = in_uv;
}
"""

UI_FS = """
#version 330
uniform sampler2D u_tex;
uniform vec4 u_color;
uniform int u_textured;
in vec2 v_uv;
out vec4 frag;
void main() {
    vec4 color = u_color;
    if (u_textured == 1) color *= texture(u_tex, v_uv);
    frag = color;
}
"""


class FishyView:
    def __init__(self, path: Path | None):
        self.path = path
        self.decoder: Decoder | None = None
        self.mount = orientation_for(path) if path is not None else "down"
        self.pan, self.tilt = start_pose(self.mount)
        self.fov = FOV_START
        self.clock = 0.0
        self.playing = path is not None
        self.held = None
        self.shown = None
        self.texture = None
        self.audio_path: str | None = None
        self.audio_ready = path is None
        self._music = False
        self.recent = load_recent()
        self.menu_open: str | None = None
        self.menu_items: list[tuple[str | None, object]] = []
        self.menu_rect = (0.0, 0.0, 0.0, 0.0)
        self.hover: int | None = None
        self.controls_until = time.perf_counter() + 3.0
        self.last_mouse = (0, 0)
        self._dragging = None
        self._last = (0, 0)
        self.running = True
        self.hwnd = 0
        if path is not None:
            self.decoder = Decoder(path)
            self.decoder.start()
            threading.Thread(target=self._load_audio, args=(path,), daemon=True).start()
            self._remember(path)

    def run(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (OSError, AttributeError):
            pass
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP)
        os.environ["SDL_VIDEO_WINDOW_POS"] = "120,80"
        pygame.init()
        try:
            pygame.mixer.init(frequency=48000, size=-16, channels=2, buffer=1024)
        except pygame.error as exc:
            print(f"Audio unavailable: {exc}", flush=True)
        screen = pygame.display.Info()
        width = max(1100, int(screen.current_w * 0.72))
        height = max(680, int(screen.current_h * 0.72))
        pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE)
        pygame.display.set_icon(self._icon())
        self.hwnd = pygame.display.get_wm_info()["window"]
        raise_window(self.hwnd)
        ctx = moderngl.create_context()
        self._gl(ctx)
        previous = time.perf_counter()
        while self.running:
            now = time.perf_counter()
            elapsed = min(0.1, now - previous)
            previous = now
            if not self._events():
                break
            self._held_keys(elapsed)
            if self.playing and self.decoder is not None:
                self.clock += elapsed
            self._sync_audio()
            self._pull_frame(ctx)
            if self.decoder is not None and self.decoder.error:
                alert(f"Could not decode the video.\n{self.decoder.error}")
                self.decoder.error = None
                self.playing = False
            self._draw(ctx)
            pygame.display.flip()
            self._caption()
        if self.decoder is not None:
            self.decoder.stop()
        self._close_audio()
        pygame.quit()

    def _icon(self) -> pygame.Surface:
        size = 64
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        surface.fill((28, 34, 44, 255))
        center = size // 2
        pygame.draw.circle(surface, (232, 236, 240), (center, center), int(size * 0.34))
        pygame.draw.circle(surface, (18, 28, 38), (center, center), int(size * 0.27))
        pygame.draw.circle(surface, (120, 190, 220), (center, center), int(size * 0.08))
        return surface

    def _gl(self, ctx: moderngl.Context) -> None:
        self.ctx = ctx
        self.fisheye = ctx.program(vertex_shader=FISHEYE_VS, fragment_shader=FISHEYE_FS)
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4").tobytes())
        self.fisheye_vao = ctx.vertex_array(self.fisheye, [(quad, "2f", "in_pos")])
        self.ui = ctx.program(vertex_shader=UI_VS, fragment_shader=UI_FS)
        self.ui_vbo = ctx.buffer(reserve=8192)
        self.ui_vao = ctx.vertex_array(self.ui, [(self.ui_vbo, "2f 2f", "in_pos", "in_uv")])
        self.font = pygame.font.SysFont("Segoe UI", 16)
        self.menu_font = pygame.font.SysFont("Segoe UI", 15)
        self.texts: dict[str, tuple[moderngl.Texture, tuple[int, int]]] = {}

    def _events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                self._key(event)
            elif event.type == pygame.MOUSEWHEEL and self.menu_open is None:
                self.fov = zoom(self.fov, event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._press(event.button, event.pos)
            elif event.type == pygame.MOUSEMOTION:
                self._motion(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._dragging = None
            elif event.type == pygame.VIDEORESIZE:
                self.ctx.viewport = (0, 0, event.w, event.h)
        return True

    def _key(self, event: pygame.event.Event) -> None:
        ctrl = bool(event.mod & pygame.KMOD_CTRL)
        if event.key == pygame.K_ESCAPE and self.menu_open:
            self.menu_open = None
        elif event.key == pygame.K_SPACE:
            self._set_playing(not self.playing)
        elif event.key == pygame.K_o and ctrl:
            self._browse()
        elif event.key == pygame.K_LEFT and ctrl:
            self._seek(self.clock - 5)
        elif event.key == pygame.K_RIGHT and ctrl:
            self._seek(self.clock + 5)
        elif event.key == pygame.K_HOME:
            self._reset_view()

    def _held_keys(self, elapsed: float) -> None:
        if self.menu_open or pygame.key.get_mods() & pygame.KMOD_CTRL:
            return
        keys = pygame.key.get_pressed()
        speed = KEY_SPEED_FAST if pygame.key.get_mods() & pygame.KMOD_SHIFT else KEY_SPEED
        dx = dy = 0.0
        if keys[pygame.K_LEFT]:
            dx -= speed * elapsed
        if keys[pygame.K_RIGHT]:
            dx += speed * elapsed
        if keys[pygame.K_UP]:
            dy -= speed * elapsed
        if keys[pygame.K_DOWN]:
            dy += speed * elapsed
        if dx or dy:
            self.pan, self.tilt = turn(self.mount, self.pan, self.tilt, dx, dy)

    def _press(self, button: int, pos: tuple[int, int]) -> None:
        x, y = pos
        self.last_mouse = pos
        self.controls_until = time.perf_counter() + 2.4
        if button == 3:
            self.menu_open = None
            self._open_context(x, y)
            return
        if self.menu_open:
            self._click_open_menu(x, y)
            return
        if button != 1:
            return
        title = self._title_at(x, y)
        if title:
            self._open_named_menu(title)
            return
        width, height = pygame.display.get_window_size()
        boxes = transport(width, height)
        if self._controls_visible(boxes) and hit(boxes["play"], x, y):
            self._set_playing(not self.playing)
            return
        if self._controls_visible(boxes) and hit(boxes["seek"], x, y):
            self._dragging = "seek"
            self._seek_at(x, boxes["seek"])
            return
        if y < MENU_H:
            return
        self._dragging = "look"
        self._last = pos

    def _motion(self, pos: tuple[int, int]) -> None:
        self.last_mouse = pos
        self.controls_until = time.perf_counter() + 2.4
        if self.menu_open and hit(self.menu_rect, pos[0], pos[1]):
            self.hover = int((pos[1] - self.menu_rect[1]) // ITEM_H)
        else:
            self.hover = None
        if self._dragging == "look":
            dx = pos[0] - self._last[0]
            dy = pos[1] - self._last[1]
            self._last = pos
            self.pan, self.tilt = turn(self.mount, self.pan, self.tilt, dx, dy)
        elif self._dragging == "seek":
            width, height = pygame.display.get_window_size()
            self._seek_at(pos[0], transport(width, height)["seek"])

    def _click_open_menu(self, x: float, y: float) -> None:
        if hit(self.menu_rect, x, y):
            index = int((y - self.menu_rect[1]) // ITEM_H)
            action = None
            if 0 <= index < len(self.menu_items):
                action = self.menu_items[index][1]
            self.menu_open = None
            if action:
                self._command(action)
            return
        previous = self.menu_open
        self.menu_open = None
        title = self._title_at(x, y)
        if title and title != previous:
            self._open_named_menu(title)

    def _title_at(self, x: float, y: float) -> str | None:
        for name, rect in self._titles():
            if hit(rect, x, y):
                return name
        return None

    def _titles(self) -> list[tuple[str, tuple[float, float, float, float]]]:
        names = ["File", "Playback", "View", "Help"]
        widths = [(name, self.menu_font.size(name)[0]) for name in names]
        return menu_bar(widths)

    def _items_for(self, name: str) -> list[tuple[str | None, object]]:
        if name == "File":
            rows: list[tuple[str | None, object]] = [("Open…", "open")]
            present = [item for item in self.recent if Path(item).is_file()]
            if present:
                rows.append((None, None))
                for item in present:
                    label = Path(item).name
                    if len(label) > 42:
                        label = label[:39] + "…"
                    rows.append((label, ("recent", item)))
            rows.append((None, None))
            rows.append(("Exit", "exit"))
            return rows
        if name == "Playback":
            label = "Pause" if self.playing else "Play"
            return [(label, "toggle"), ("Back 5 seconds", "back"), ("Forward 5 seconds", "forward")]
        if name == "View":
            return [("Reset view", "reset"), ("Zoom in", "zin"), ("Zoom out", "zout"), (None, None), *self._mount_rows()]
        return [("How to look around", "help")]

    def _open_named_menu(self, name: str) -> None:
        self.menu_items = self._items_for(name)
        anchor = next(rect for title, rect in self._titles() if title == name)
        width = self._menu_width(self.menu_items)
        self.menu_rect = dropdown(anchor, len(self.menu_items), width)
        self.menu_open = name
        self.hover = None

    def _open_context(self, x: float, y: float) -> None:
        self.menu_items = [
            ("Pause" if self.playing else "Play", "toggle"),
            ("Open…", "open"),
            ("Reset view", "reset"),
            (None, None),
            *self._mount_rows(),
        ]
        width = self._menu_width(self.menu_items)
        window = pygame.display.get_window_size()
        self.menu_rect = place_popup(x, y, width, len(self.menu_items), window)
        self.menu_open = "context"
        self.hover = None

    def _menu_width(self, items: list[tuple[str | None, object]]) -> float:
        widest = 180
        for label, _action in items:
            if label:
                widest = max(widest, self.menu_font.size(label)[0] + 36)
        return float(widest)

    def _command(self, action: object) -> None:
        if action == "open":
            self._browse()
        elif action == "exit":
            self.running = False
        elif action == "toggle":
            self._set_playing(not self.playing)
        elif action == "back":
            self._seek(self.clock - 5)
        elif action == "forward":
            self._seek(self.clock + 5)
        elif action == "reset":
            self._reset_view()
        elif action == "zin":
            self.fov = zoom(self.fov, 1)
        elif action == "zout":
            self.fov = zoom(self.fov, -1)
        elif action == "help":
            alert(
                "Drag to look around. Left and right turn. Up and down look up and down.\n"
                "Hold an arrow key to keep moving. Shift is faster.\n"
                "The wheel zooms. Space plays and pauses. Ctrl+O opens a video.\n\n"
                "View sets how the camera is mounted.\n"
                "Looking down: the center of the picture is the ground.\n"
                "Looking out: the center is straight ahead, and the top of the picture is up.\n"
                "Looking up: the center is the sky.\n"
                "That choice is remembered for each file."
            )
        elif isinstance(action, tuple) and action[0] == "mount":
            self._set_mount(str(action[1]))
        elif isinstance(action, tuple) and action[0] == "recent":
            self.open_path(Path(action[1]))

    def _browse(self) -> None:
        selected = choose_video(self.hwnd)
        if selected:
            self.open_path(Path(selected))

    def open_path(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            alert(f"That file is not there anymore.\n{path}")
            return
        if self.decoder is not None:
            self.decoder.stop()
        self._close_audio()
        self.path = path
        self.decoder = Decoder(path)
        self.decoder.start()
        self.clock = 0.0
        self.playing = True
        self.held = None
        self.shown = None
        self.audio_ready = False
        self._music = False
        threading.Thread(target=self._load_audio, args=(path,), daemon=True).start()
        self.mount = orientation_for(path)
        self.pan, self.tilt = start_pose(self.mount)
        self._remember(path)

    def _remember(self, path: Path) -> None:
        text = str(path)
        self.recent = [text] + [item for item in self.recent if item != text]
        self.recent = self.recent[:8]
        save_recent(self.recent)

    def _mount_rows(self) -> list[tuple[str, tuple[str, str]]]:
        rows = []
        for mode, label in LABELS.items():
            prefix = "✓  " if self.mount == mode else ""
            rows.append((prefix + label, ("mount", mode)))
        return rows

    def _set_mount(self, mode: str) -> None:
        if mode not in LABELS:
            return
        self.mount = mode
        self.pan, self.tilt = start_pose(mode)
        if self.path is not None:
            save_orientation(self.path, mode)

    def _reset_view(self) -> None:
        self.pan, self.tilt = start_pose(self.mount)
        self.fov = FOV_START

    def _seek_at(self, x: float, rect: tuple[float, float, float, float]) -> None:
        if self.decoder is None or self.decoder.duration <= 0:
            return
        fraction = min(1.0, max(0.0, (x - rect[0]) / max(1.0, rect[2])))
        self._seek(fraction * self.decoder.duration)

    def _seek(self, seconds: float) -> None:
        if self.decoder is None:
            return
        duration = self.decoder.duration or seconds
        self.clock = float(min(max(0.0, seconds), max(0.0, duration - 0.05)))
        self.held = None
        self.shown = None
        self.decoder.request_seek(self.clock)
        if self._music and self.audio_path:
            try:
                pygame.mixer.music.play(start=self.clock)
                if not self.playing:
                    pygame.mixer.music.pause()
            except pygame.error:
                pass

    def _set_playing(self, playing: bool) -> None:
        if self.decoder is None:
            return
        if playing and self.decoder.eof and self.clock >= max(0.0, self.decoder.duration - 0.15):
            self._seek(0)
        self.playing = playing
        if not self._music or not self.audio_path:
            return
        try:
            if playing:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.unpause()
                else:
                    pygame.mixer.music.play(start=self.clock)
            else:
                pygame.mixer.music.pause()
        except pygame.error:
            pass

    def _load_audio(self, path: Path) -> None:
        produced = None
        try:
            produced = extract_audio(path)
        except Exception as exc:
            print(f"Audio unavailable: {exc}", flush=True)
        if self.path != path:
            if produced:
                Path(produced).unlink(missing_ok=True)
            return
        self.audio_path = produced
        self.audio_ready = True

    def _sync_audio(self) -> None:
        if not self.audio_ready or not self.audio_path or self._music:
            return
        try:
            pygame.mixer.music.load(self.audio_path)
            if self.playing:
                pygame.mixer.music.play(start=self.clock)
            self._music = True
        except pygame.error as exc:
            print(f"Audio unavailable: {exc}", flush=True)
            self.audio_path = None
            self._music = True

    def _close_audio(self) -> None:
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass
        if self.audio_path:
            Path(self.audio_path).unlink(missing_ok=True)
        self.audio_path = None
        self._music = False

    def _pull_frame(self, ctx: moderngl.Context) -> None:
        if self.decoder is None:
            return
        chosen = None
        while True:
            item = self.held
            if item is None:
                try:
                    item = self.decoder.frames.get_nowait()
                except queue.Empty:
                    break
            generation, timestamp, _array = item
            with self.decoder.lock:
                current = self.decoder.generation
            if generation != current:
                self.held = None
                continue
            if self.shown is None or timestamp <= self.clock + 0.03:
                chosen = item
                self.held = None
                continue
            self.held = item
            break
        if chosen is None:
            if (
                self.playing
                and self.shown is not None
                and self.decoder.frames.empty()
                and self.held is None
                and self.clock > self.shown[1] + 0.2
            ):
                self.clock = self.shown[1]
            if self.decoder.eof and self.shown and self.clock > self.decoder.duration:
                self.playing = False
                self.clock = self.decoder.duration
            return
        _generation, _timestamp, array = chosen
        height, width = array.shape[:2]
        if self.texture is None or self.texture.size != (width, height):
            if self.texture is not None:
                self.texture.release()
            self.texture = ctx.texture((width, height), 3)
            self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.texture.repeat_x = False
            self.texture.repeat_y = False
        self.texture.write(array)
        self.shown = chosen

    def _controls_visible(self, boxes: dict[str, tuple[float, float, float, float]]) -> bool:
        if self.decoder is None:
            return False
        if not self.playing or self._dragging == "seek":
            return True
        if time.perf_counter() < self.controls_until:
            return True
        return hit(boxes["bar"], self.last_mouse[0], self.last_mouse[1])

    def _draw(self, ctx: moderngl.Context) -> None:
        width, height = pygame.display.get_window_size()
        ctx.viewport = (0, 0, width, height)
        ctx.clear(0.06, 0.06, 0.06)
        ctx.disable(moderngl.BLEND)
        if self.texture is not None:
            self.texture.use(0)
            self.fisheye["u_tex"].value = 0
            self.fisheye["u_cam"].value = basis(self.mount, self.pan, self.tilt)
            self.fisheye["u_fov"].value = self.fov
            self.fisheye["u_lens"].value = np.pi / 2
            self.fisheye["u_aspect"].value = width / max(1, height)
            self.fisheye_vao.render(moderngl.TRIANGLE_STRIP)
        elif self.path is None:
            self._centered(width, height, "Open a video from the File menu")
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self._draw_menu(width)
        boxes = transport(width, height)
        if self._controls_visible(boxes):
            self._draw_transport(width, height, boxes)
        if self.menu_open:
            self._draw_dropdown()

    def _draw_menu(self, width: int) -> None:
        self._fill(0, 0, width, MENU_H, (22, 22, 22, 245))
        self._fill(0, MENU_H - 1, width, 1, (70, 70, 70, 255))
        for name, rect in self._titles():
            hot = self.menu_open == name or hit(rect, self.last_mouse[0], self.last_mouse[1])
            if hot:
                self._fill(rect[0], rect[1], rect[2], rect[3], (48, 48, 48, 255))
            self._text(name, rect[0] + 11, 6, self.menu_font)

    def _draw_dropdown(self) -> None:
        rect = self.menu_rect
        self._fill(rect[0], rect[1], rect[2], rect[3], (28, 28, 28, 250))
        self._fill(rect[0], rect[1], rect[2], 1, (80, 80, 80, 255))
        for index, (label, _action) in enumerate(self.menu_items):
            item = dropdown_item(rect, index)
            if label is None:
                self._fill(item[0] + 8, item[1] + ITEM_H / 2, item[2] - 16, 1, (80, 80, 80, 255))
                continue
            if index == self.hover:
                self._fill(*item, (56, 56, 56, 255))
            self._text(label, item[0] + 14, item[1] + 6, self.menu_font)

    def _draw_transport(self, width: int, height: int, boxes: dict) -> None:
        bar = boxes["bar"]
        self._fill(0, bar[1], width, BAR_H, (0, 0, 0, 170))
        play = boxes["play"]
        over = hit(play, self.last_mouse[0], self.last_mouse[1])
        self._fill(play[0], play[1], play[2], play[3], (255, 255, 255, 40 if over else 18))
        if self.playing:
            self._fill(play[0] + 13, play[1] + 12, 6, 20, (240, 240, 240, 255))
            self._fill(play[0] + 25, play[1] + 12, 6, 20, (240, 240, 240, 255))
        else:
            self._shape([
                (play[0] + 16, play[1] + 12),
                (play[0] + 16, play[1] + 32),
                (play[0] + 34, play[1] + 22),
            ], (240, 240, 240, 255))
        duration = self.decoder.duration if self.decoder else 0
        label = f"{fmt(self.clock)} / {fmt(duration)}"
        self._text(label, play[0] + play[2] + 14, play[1] + 12, self.font)
        mount = LABELS[self.mount]
        mount_w = self.font.size(mount)[0]
        self._text(mount, width - mount_w - 22, play[1] + 12, self.font)
        seek = boxes["seek"]
        fraction = 0.0 if duration <= 0 else min(1.0, max(0.0, self.clock / duration))
        self._fill(seek[0], seek[1] + 6, seek[2], 4, (255, 255, 255, 60))
        self._fill(seek[0], seek[1] + 6, seek[2] * fraction, 4, (255, 255, 255, 230))

    def _centered(self, width: int, height: int, message: str) -> None:
        ctx_blend = True
        self.ctx.enable(moderngl.BLEND)
        size = self.font.size(message)
        self._text(message, (width - size[0]) / 2, (height - size[1]) / 2, self.font)
        if not ctx_blend:
            self.ctx.disable(moderngl.BLEND)

    def _text(self, message: str, x: float, y: float, font: pygame.font.Font) -> None:
        key = f"{font.get_height()}:{message}"
        cached = self.texts.get(key)
        if cached is None:
            surface = font.render(message, True, (236, 236, 236))
            data = pygame.image.tobytes(surface, "RGBA", True)
            texture = self.ctx.texture(surface.get_size(), 4, data)
            texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            cached = (texture, surface.get_size())
            self.texts[key] = cached
        texture, (tw, th) = cached
        texture.use(0)
        self._raw_quad(x, y, tw, th, (1, 1, 1, 1), textured=True)

    def _fill(self, x, y, w, h, color) -> None:
        red, green, blue, alpha = color
        self._raw_quad(x, y, w, h, (red / 255, green / 255, blue / 255, alpha / 255), textured=False)

    def _shape(self, points: list[tuple[float, float]], color) -> None:
        red, green, blue, alpha = color
        data = []
        for x, y in points:
            data.extend((x, y, 0, 0))
        self._flush(data, (red / 255, green / 255, blue / 255, alpha / 255), False, len(points))

    def _raw_quad(self, x, y, w, h, color, textured: bool) -> None:
        if w <= 0 or h <= 0:
            return
        x2, y2 = x + w, y + h
        if textured:
            data = [x, y, 0, 1, x2, y, 1, 1, x2, y2, 1, 0, x, y, 0, 1, x2, y2, 1, 0, x, y2, 0, 0]
        else:
            data = [x, y, 0, 0, x2, y, 0, 0, x2, y2, 0, 0, x, y, 0, 0, x2, y2, 0, 0, x, y2, 0, 0]
        self._flush(data, color, textured, 6)

    def _flush(self, data, color, textured: bool, count: int) -> None:
        width, height = pygame.display.get_window_size()
        self.ui_vbo.write(np.array(data, dtype="f4").tobytes())
        self.ui["u_res"].value = (float(width), float(height))
        self.ui["u_textured"].value = 1 if textured else 0
        self.ui["u_color"].value = color
        self.ui_vao.render(moderngl.TRIANGLES, vertices=count)

    def _caption(self) -> None:
        if self.path is None or self.decoder is None:
            pygame.display.set_caption(APP)
            return
        pygame.display.set_caption(f"{APP} — {self.path.name}    {fmt(self.clock)} / {fmt(self.decoder.duration)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FishyView")
    parser.add_argument("video", nargs="?")
    args = parser.parse_args()
    path = Path(args.video).expanduser() if args.video else None
    if path is not None and not path.is_file():
        fail(f"No such file:\n{path}")
    try:
        FishyView(path.resolve() if path else None).run()
    except pygame.error as exc:
        fail(f"Could not open a window.\n{exc}")
    except moderngl.Error as exc:
        fail(f"Could not start the picture.\n{exc}")


if __name__ == "__main__":
    main()
