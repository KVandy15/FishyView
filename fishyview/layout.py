"""Hit targets for the menu bar, dropdowns, and the hover transport."""

from __future__ import annotations

MENU_H = 30
ITEM_H = 30
BAR_H = 78


def hit(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh


def menu_bar(widths: list[tuple[str, int]]) -> list[tuple[str, tuple[float, float, float, float]]]:
    x = 4.0
    items = []
    for name, text_w in widths:
        rect = (x, 0.0, float(text_w + 22), float(MENU_H))
        items.append((name, rect))
        x += rect[2]
    return items


def dropdown(anchor: tuple[float, float, float, float], count: int, width: float) -> tuple[float, float, float, float]:
    return (anchor[0], anchor[1] + anchor[3], width, ITEM_H * count)


def dropdown_item(menu_rect: tuple[float, float, float, float], index: int) -> tuple[float, float, float, float]:
    return (menu_rect[0], menu_rect[1] + ITEM_H * index, menu_rect[2], ITEM_H)


def place_popup(x: float, y: float, width: float, count: int, window: tuple[float, float]) -> tuple[float, float, float, float]:
    height = ITEM_H * count
    if y + height > window[1]:
        y = max(0.0, y - height)
    if x + width > window[0]:
        x = max(0.0, window[0] - width)
    return (x, y, width, height)


def transport(width: float, height: float) -> dict[str, tuple[float, float, float, float]]:
    top = height - BAR_H
    return {
        "bar": (0.0, top, width, float(BAR_H)),
        "play": (18.0, top + 16.0, 44.0, 44.0),
        "seek": (18.0, height - 28.0, max(40.0, width - 36.0), 18.0),
    }
