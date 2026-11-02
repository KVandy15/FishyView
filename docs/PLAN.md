# FishyView

Personal Windows player for raw circular fisheye video, including UniFi G6 exports. MIT licensed. No accounts, no network, no analytics, no installer service.

## Stack

Python 3.13, pygame, ModernGL, PyAV, PyInstaller (`dist/FishyView/FishyView.exe`).

## Behavior

Drag left and right to turn. Drag up and down to look up and down. The wheel zooms. Hold an arrow key to keep moving. Shift moves faster.

View → Looking down, Looking out, or Looking up matches the mount. Down is the center of the lens on the ground. Out is the center straight ahead, with the top of the frame as up. Up is the center on the sky. The choice is stored per file.

A menu bar (File, Playback, View, Help) and a right-click menu open files and the same playback commands. Transport controls show when the pointer moves, and hide again while the video is playing.

## Checks

Unit tests cover the look math and the menu hit targets. The built exe has to open a window on a local file.
