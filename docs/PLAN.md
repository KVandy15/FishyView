# FishyView

Personal Windows player for raw downward-looking circular fisheye video, including UniFi G6 exports. Not a commercial product: no accounts, no network, no analytics, no installer service.

## Stack

Python 3.13, pygame, ModernGL, PyAV, PyInstaller (`dist/FishyView/FishyView.exe`).

## Behavior

The lens points down. Drag left and right to turn around the center. Drag up and down to move from the center of the picture out to the edge. The wheel zooms. Hold an arrow key to keep moving. Shift moves faster.

A menu bar (File, Playback, View, Help) and a right-click menu open files and the same playback commands. Transport controls show when the pointer moves, and hide again while the video is playing.

## Checks

Unit tests cover the look math and the menu hit targets. The built exe has to open a window on a local file.
