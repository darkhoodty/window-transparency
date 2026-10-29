
import threading
import time

import win32con
import win32gui
from pynput.keyboard import GlobalHotKeys


# =========================
# Configuration
# =========================

TRANSPARENCY = 210       # 1-254: Lower values mean more transparent
FADE_DURATION = 0.5      # Animation duration in seconds
FADE_STEPS = 30          # Higher values produce smoother animation


# =========================
# Internal State
# =========================

window_states = {}
fade_tokens = {}
state_lock = threading.RLock()


def get_active_window():
    """Return the currently active window handle."""
    hwnd = win32gui.GetForegroundWindow()

    if not hwnd or not win32gui.IsWindow(hwnd):
        return None

    return hwnd


def save_window_state(hwnd):
    """Save the original extended style and transparency settings."""
    if hwnd in window_states:
        return

    style = win32gui.GetWindowLong(
        hwnd, win32con.GWL_EXSTYLE
    )

    is_layered = bool(style & win32con.WS_EX_LAYERED)
    alpha = None
    color_key = None
    flags = 0

    if is_layered:
        try:
            result = win32gui.GetLayeredWindowAttributes(hwnd)

            if result:
                color_key, alpha, flags = result
        except Exception:
            pass

    window_states[hwnd] = {
        "style": style,
        "is_layered": is_layered,
        "alpha": alpha,
        "color_key": color_key,
        "flags": flags,
        "current_alpha": 255,
        "transparent": False,
    }


def set_window_alpha(hwnd, alpha):
    """Apply the specified alpha value to a window."""
    if not win32gui.IsWindow(hwnd):
        return

    save_window_state(hwnd)
    alpha = max(1, min(255, int(alpha)))

    style = win32gui.GetWindowLong(
        hwnd, win32con.GWL_EXSTYLE
    )

    if not style & win32con.WS_EX_LAYERED:
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            style | win32con.WS_EX_LAYERED
        )

    win32gui.SetLayeredWindowAttributes(
        hwnd, 0, alpha, win32con.LWA_ALPHA
    )

    window_states[hwnd]["current_alpha"] = alpha


def restore_window(hwnd):
    """Restore the window's original transparency settings and style."""
    if hwnd not in window_states:
        return

    if not win32gui.IsWindow(hwnd):
        window_states.pop(hwnd, None)
        fade_tokens.pop(hwnd, None)
        return

    state = window_states[hwnd]

    if state["is_layered"]:
        flags = state["flags"]

        if flags:
            win32gui.SetLayeredWindowAttributes(
                hwnd,
                state["color_key"] or 0,
                state["alpha"] if state["alpha"] is not None else 255,
                flags
            )
        else:
            win32gui.SetLayeredWindowAttributes(
                hwnd, 0, 255, win32con.LWA_ALPHA
            )
    else:
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            state["style"]
        )

    window_states.pop(hwnd, None)
    fade_tokens.pop(hwnd, None)


def fade_window(hwnd, start_alpha, end_alpha, token):
    """Gradually transition a window between two alpha values."""
    steps = max(1, FADE_STEPS)
    interval = FADE_DURATION / steps
    start_time = time.perf_counter()

    for step in range(1, steps + 1):
        with state_lock:
            if fade_tokens.get(hwnd) != token:
                return

        if not win32gui.IsWindow(hwnd):
            with state_lock:
                window_states.pop(hwnd, None)
                fade_tokens.pop(hwnd, None)
            return

        progress = step / steps
        alpha = start_alpha + (end_alpha - start_alpha) * progress

        try:
            set_window_alpha(hwnd, alpha)
        except Exception as error:
            print(f"[Error] Failed to change transparency: {error}")
            return

        target_time = start_time + interval * step
        remaining = target_time - time.perf_counter()

        if remaining > 0:
            time.sleep(remaining)

    with state_lock:
        if fade_tokens.get(hwnd) != token:
            return

        if end_alpha == 255:
            restore_window(hwnd)
        else:
            window_states[hwnd]["transparent"] = True
            window_states[hwnd]["current_alpha"] = int(end_alpha)


def toggle_transparency():
    """Toggle transparency for the currently active window."""
    hwnd = get_active_window()

    if hwnd is None:
        return

    with state_lock:
        save_window_state(hwnd)

        state = window_states[hwnd]
        token = fade_tokens.get(hwnd, 0) + 1
        fade_tokens[hwnd] = token

        current_alpha = state["current_alpha"]

        if state["transparent"]:
            start_alpha = current_alpha
            end_alpha = 255
            state["transparent"] = False
        else:
            start_alpha = current_alpha
            end_alpha = max(1, min(254, TRANSPARENCY))
            state["transparent"] = True

        threading.Thread(
            target=fade_window,
            args=(hwnd, start_alpha, end_alpha, token),
            daemon=True
        ).start()


def main():
    print("Window Transparency is running.")
    print(f"Transparency level: {TRANSPARENCY}/255")
    print("Press Scroll Lock to toggle transparency.")
    print("Press Ctrl+C to exit.")

    hotkeys = GlobalHotKeys({
        "<scroll_lock>": toggle_transparency,
    })

    hotkeys.start()
    hotkeys.join()


if __name__ == "__main__":
    main()
