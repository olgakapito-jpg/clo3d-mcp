"""Modeless, dependency-free Windows panel; no network, CLO calls or event loop.

Only explicit button clicks invoke the existing launcher/stop path. Native
callbacks and the window class remain retained until CLO exits, including when
the panel is hidden. This module must not be hot-reloaded inside CLO.
"""

import re


class PanelController:
    def __init__(self, service_registry, start_server, thread_id):
        self.service_registry = service_registry
        self.start_server = start_server
        self.thread_id = thread_id
        self.owner_thread = thread_id()
        self.action_busy = False
        self.error = None

    def _check_thread(self):
        if self.thread_id() != self.owner_thread:
            raise RuntimeError("Panel must run on the registering CLO UI thread")

    def status(self):
        self._check_thread()
        registry = self.service_registry()
        if registry is not None and registry.get("version") != 1:
            return "Неизвестная версия runtime. Перезапустите CLO.", False, False
        registry = registry or {}
        current = registry.get("current")
        state = current.state if current is not None else "stopped"
        busy = self.action_busy or (current is not None and current.busy)
        clean = current is None or (
            current.timer_id is None and current.pipe is None and not current.busy)
        terminal = state in ("stopped", "failed")
        can_start = terminal and clean and not busy and len(registry.get("retained", [])) < 16
        can_stop = current is not None and not busy and (
            not terminal or not clean) and state not in ("requesting_stop", "draining_stop", "stopping")
        labels = {
            "new": "Подготовка", "starting": "Запуск", "connecting": "Подключение",
            "active": "Готов" if current.service_ready else "Ожидание готовности",
            "reconnecting": "Переподключение", "requesting_stop": "Остановка…",
            "draining_stop": "Остановка…", "stopping": "Очистка…",
            "stopped": "Остановлен", "failed": "Ошибка",
        } if current is not None else {"stopped": "Остановлен"}
        text = "Состояние: " + labels.get(state, "Неизвестно")
        if current is not None:
            text += "\nЗапуск: %d / 16" % current.generation
        if terminal and not clean:
            text += "\nОчистка не завершена — нажмите Стоп."
        if terminal and clean and len(registry.get("retained", [])) >= 16:
            text += "\nДостигнут лимит запусков — перезапустите CLO."
        error = self.error or (current.error if current is not None else None)
        if error:
            # Never expose exceptions containing private paths, peer payloads or tokens.
            code = error if isinstance(error, str) and re.fullmatch(r"[A-Za-z_]{1,80}", error) else "runtime_error"
            text += "\nОшибка: " + code
        return text, can_start, can_stop

    def act(self, action):
        self._check_thread()
        if action not in ("start", "stop"):
            raise ValueError("Unknown panel action")
        _, can_start, can_stop = self.status()
        if not (can_start if action == "start" else can_stop):
            return
        self.action_busy = True
        self.error = None
        try:
            if action == "start":
                self.start_server()
            else:
                self.service_registry()["current"].stop()
        except BaseException as exc:
            self.error = type(exc).__name__
        finally:
            self.action_busy = False


class WindowsPanel:
    """Own Win32 controls, not UI automation of CLO. No GetMessage/exec loop."""

    START = 101
    STOP = 102
    TIMER = 1

    def __init__(self, controller):
        import ctypes
        from ctypes import wintypes as wt
        import sys

        if sys.platform != "win32":
            raise RuntimeError("The control panel requires Windows")
        self.controller = controller
        self.ctypes = ctypes
        self.wt = wt
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.wndproc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        class WindowClass(ctypes.Structure):
            _fields_ = [("style", wt.UINT), ("lpfnWndProc", self.wndproc_type),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                        ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                        ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

        self.window_class_type = WindowClass
        self._signature(self.kernel.GetModuleHandleW, [wt.LPCWSTR], wt.HMODULE)
        self._signature(self.user.RegisterClassW, [ctypes.POINTER(WindowClass)], wt.ATOM)
        self._signature(self.user.CreateWindowExW,
                        [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU,
                         wt.HINSTANCE, ctypes.c_void_p], wt.HWND)
        self._signature(self.user.DefWindowProcW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], ctypes.c_ssize_t)
        self._signature(self.user.ShowWindow, [wt.HWND, ctypes.c_int], wt.BOOL)
        self._signature(self.user.SetForegroundWindow, [wt.HWND], wt.BOOL)
        self._signature(self.user.SetWindowTextW, [wt.HWND, wt.LPCWSTR], wt.BOOL)
        self._signature(self.user.EnableWindow, [wt.HWND, wt.BOOL], wt.BOOL)
        self._signature(self.user.SetTimer, [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p], ctypes.c_size_t)
        self._signature(self.user.KillTimer, [wt.HWND, ctypes.c_size_t], wt.BOOL)
        self._signature(self.user.SendMessageW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], ctypes.c_ssize_t)
        self._signature(self.gdi.GetStockObject, [ctypes.c_int], wt.HANDLE)
        self.instance = self.kernel.GetModuleHandleW(None)
        if not self.instance:
            raise ctypes.WinError(ctypes.get_last_error())
        self.callback = self.wndproc_type(self._dispatch)
        self.hwnd = None
        self.controls = {}
        self.visible = False
        self.timer_id = None
        self.created = False

    @staticmethod
    def _signature(function, args, result):
        function.argtypes = args
        function.restype = result

    def create(self):
        self.controller._check_thread()
        definition = self.window_class_type()
        definition.lpfnWndProc = self.callback
        definition.hInstance = self.instance
        definition.hbrBackground = 16  # COLOR_BTNFACE + 1, system-owned brush
        definition.lpszClassName = "CLO3DMCPControlPanelV1"
        self.definition = definition
        if not self.user.RegisterClassW(self.ctypes.byref(definition)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        # Modeless top-level panel; the CLO host supplies message dispatch.
        self.hwnd = self._window(0x00000080, definition.lpszClassName, "CLO MCP", 0x00CA0000,
                                 -2147483648, -2147483648, 440, 265, None, 0)
        self.controls["endpoint"] = self._window(0, "STATIC", "http://127.0.0.1:8765/mcp",
                                                 0x50000000, 18, 16, 390, 22, self.hwnd, 0)
        self.controls["status"] = self._window(0, "STATIC", "", 0x50000000,
                                               18, 47, 390, 95, self.hwnd, 0)
        for name, label, ident, x in (("start", "Старт", self.START, 18), ("stop", "Стоп", self.STOP, 158)):
            self.controls[name] = self._window(0, "BUTTON", label, 0x50010000,
                                                x, 151, 125, 33, self.hwnd, ident)
        self.controls["hint"] = self._window(0, "STATIC", "Закрытие окна не останавливает сервер.",
                                             0x50000000, 18, 197, 390, 22, self.hwnd, 0)
        font = self.gdi.GetStockObject(17)  # DEFAULT_GUI_FONT
        for hwnd in self.controls.values():
            self.user.SendMessageW(hwnd, 0x0030, font or 0, 1)  # WM_SETFONT
        self.created = True

    def _window(self, ex_style, cls, title, style, x, y, width, height, parent, ident):
        hwnd = self.user.CreateWindowExW(ex_style, cls, title, style, x, y, width,
                                          height, parent, ident, self.instance, None)
        if not hwnd:
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return hwnd

    def show(self):
        self.controller._check_thread()
        if not self.created:
            raise RuntimeError("Panel creation failed; restart CLO")
        if self.timer_id is None:
            self.timer_id = self.user.SetTimer(self.hwnd, self.TIMER, 500, None)
            if not self.timer_id:
                self.timer_id = None
                raise self.ctypes.WinError(self.ctypes.get_last_error())
        self.visible = True
        self.refresh()
        self.user.ShowWindow(self.hwnd, 5)
        self.user.SetForegroundWindow(self.hwnd)

    def hide(self):
        self.controller._check_thread()
        self.visible = False
        if self.timer_id is not None and self.user.KillTimer(self.hwnd, self.timer_id):
            self.timer_id = None
        self.user.ShowWindow(self.hwnd, 0)

    def refresh(self):
        text, can_start, can_stop = self.controller.status()
        self.user.SetWindowTextW(self.controls["status"], text.replace("\n", "\r\n"))
        self.user.EnableWindow(self.controls["start"], can_start)
        self.user.EnableWindow(self.controls["stop"], can_stop)

    def _dispatch(self, hwnd, message, wparam, lparam):
        try:
            self.controller._check_thread()
            if message == 0x0010:  # WM_CLOSE: retain window/class/callback, hide only
                self.hide()
                return 0
            if message == 0x0113 and wparam == self.TIMER:  # WM_TIMER
                if self.visible:
                    self.refresh()  # reads bounded in-memory state, no HTTP/API/process polling
                return 0
            if message == 0x0111 and self.created and wparam >> 16 == 0:  # WM_COMMAND / BN_CLICKED
                ident = wparam & 0xFFFF
                action = {self.START: "start", self.STOP: "stop"}.get(ident)
                if action and lparam == self.controls[action]:
                    self.controller.act(action)
                    self.refresh()
                    return 0
            return self.user.DefWindowProcW(hwnd, message, wparam, lparam)
        except BaseException as exc:
            # No exception can unwind across a native WNDPROC boundary.
            self.controller.error = type(exc).__name__
            return 0
