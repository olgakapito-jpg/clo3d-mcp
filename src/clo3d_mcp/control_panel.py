"""Modeless CLO-native panel controller; no Win32, network or event loop.

Buttons only call the existing launcher/stop path and refresh labels. gui_api
callbacks run on the CLO main thread; handles/callables are retained until CLO
exits. This module must not be hot-reloaded inside CLO.
"""

import re


class PanelController:
    def __init__(self, service_registry, start_server, thread_id=None):
        self.service_registry = service_registry
        self.start_server = start_server
        self.thread_id = thread_id
        self.owner_thread = thread_id() if thread_id is not None else None
        self.action_busy = False
        self.error = None

    def _check_thread(self):
        if self.thread_id is not None and self.thread_id() != self.owner_thread:
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
        can_start = terminal and clean and not busy
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
            text += "\nПоколение: %d" % current.generation
        if terminal and not clean:
            text += "\nОчистка не завершена — нажмите Стоп."
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


class GuiPanel:
    """CLO gui_api dock panel (tool window fallback); no Win32 and no timer.

    gui_api has no documented periodic callback, so status refreshes on create,
    after each action and on the explicit "Обновить" button.
    """

    TITLE = "CLO MCP"
    SIDE = "right"
    NAME = "clo_mcp_controller"

    def __init__(self, gui, controller):
        self.gui = gui
        self.controller = controller
        self.window = 0
        self.status = 0
        self.buttons = {}
        self.closed = False
        self.kind = None
        self.last_show = None

    def _text(self):
        text, can_start, can_stop = self.controller.status()
        return text.replace("\n", " | "), can_start, can_stop

    def create(self, force_tool=False):
        if not self.gui.IsGuiAvailable():
            raise RuntimeError("CLO GUI is unavailable (headless or non-main thread)")
        window = 0 if force_tool else self.gui.CreateDockPanel(self.TITLE, self.SIDE, self.NAME)
        self.kind = "dock" if window else "tool"
        if not window:
            window = self.gui.CreateToolWindow(self.TITLE, 460, 240)
        if not window:
            raise RuntimeError("Could not create a CLO panel window")
        self.window = window
        self.status = self.gui.AddLabel(window, "")
        self.buttons = {
            "start": self.gui.AddButton(window, "Старт", self.on_start),
            "stop": self.gui.AddButton(window, "Стоп", self.on_stop),
            "refresh": self.gui.AddButton(window, "Обновить", self.on_refresh),
        }
        self.gui.AddLabel(window, "Закрытие окна не останавливает сервер.")
        if not self.status or not all(self.buttons.values()):
            raise RuntimeError("CLO refused panel widgets; restart CLO")
        self.gui.SetWindowCloseCallback(window, self.on_close)
        self.closed = False
        self.refresh()
        return self

    def show(self):
        if self.window == 0 or self.closed:
            self.create()
        self.last_show = self.gui.ShowWindow(self.window)
        if self.last_show:
            return
        # A dock handle can exist while ShowWindow fails; force one tool window.
        self.create(force_tool=True)
        self.last_show = self.gui.ShowWindow(self.window)
        if not self.last_show:
            raise RuntimeError("CLO refused to show the panel")

    def report(self):
        widgets = len([handle for handle in self.buttons.values() if handle])
        return "kind=%s window=%s widgets=%s shown=%s" % (
            self.kind, self.window, widgets, self.last_show)

    def refresh(self):
        if self.window == 0 or self.closed:
            return
        text, can_start, can_stop = self._text()
        self.gui.SetWidgetText(self.status, text)
        self.gui.SetWidgetEnabled(self.buttons["start"], can_start)
        self.gui.SetWidgetEnabled(self.buttons["stop"], can_stop)

    def _act(self, action):
        try:
            self.controller.act(action)
        finally:
            self.refresh()

    def on_start(self):
        self._act("start")

    def on_stop(self):
        self._act("stop")

    def on_refresh(self):
        self.refresh()

    def on_close(self):
        self.closed = True
        self.window = 0
