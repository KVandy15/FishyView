# FishyView

Windows player for a raw circular fisheye video. Open the file, pick how the camera is mounted, and look around. It was made for UniFi G6 Pro 360 exports. Any square fisheye of about 180° can be tried the same way.

The picture stays the original file. The player only changes how that frame is drawn.

## How this was made

This was vibe-coded with an AI assistant in Cursor, in one sitting, on the order of a few minutes of direction rather than a careful hand-written project. I said what the window should do, tried it on a real clip, and asked for fixes. I did not write the code line by line, and it has not had a long review. Treat it as a small tool that works for the cases below, not as a finished product from a camera company.

## Download

The v0.1 Windows build is on the [releases page](https://github.com/KVandy15/FishyView/releases). Unzip the whole folder and run `FishyView.exe`. The program needs the files next to it. Running the exe from inside the zip will fail.

Windows may warn that the app is unrecognized. It is unsigned. That warning is expected.

You can also drop a video onto `FishyView.exe`.

## Looking around

Drag left and right to turn. Drag up and down to look up and down. The wheel zooms. Hold an arrow key to keep moving. Shift moves faster.

Space plays and pauses. Ctrl+Left and Ctrl+Right jump five seconds. Ctrl+O opens a file. The bar along the bottom shows when you move the pointer, then hides while playback continues.

## Camera mount

**View**, or the right-click menu, sets how the camera is installed. The choice is remembered for that file.

| Mount | What the center of the picture is |
| --- | --- |
| Looking down | The ground. Dragging up looks out toward the horizon. |
| Looking out | Straight ahead. The top of the fisheye is up. |
| Looking up | The sky. Dragging up looks further up. |

Looking out assumes the camera is mounted upright. A wall camera rolled onto its side is not handled.

## Build

Python 3.11 or newer.

```powershell
pip install -e .
python -m unittest tests.test_camera
python run.py C:\path\to\clip.mp4
```

The Windows app is built with PyInstaller:

```powershell
.\build.ps1
```

The result is `dist\FishyView\FishyView.exe`.

## License

[MIT](LICENSE).
