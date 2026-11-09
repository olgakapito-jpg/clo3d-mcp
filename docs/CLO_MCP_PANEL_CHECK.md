# Окно управления MCP внутри CLO

`plugin/clo3d_mcp_panel.py` показывает немодальное окно **CLO MCP** с кнопками
**Старт**, **Стоп** и текущим состоянием. Используется штатный Win32/ctypes,
без Qt/PySide, установки зависимостей или собственного цикла сообщений.
Открытие окна не запускает сервер; закрытие крестиком только скрывает окно.
Повторный запуск скрипта показывает тот же экземпляр.

## Запуск

1. В CLO 2026.1.336 открыть Script Editor и `plugin/clo3d_mcp_panel.py`.
2. Если CLO не задаёт `__file__`, локально задать `ROOT` равным абсолютному пути
   к проекту. Это та же настройка, что у обычного launcher; не коммитить этот путь.
3. Нажать Run и закрыть Script Editor. Окно должно остаться доступным.
4. Нажать **Старт**, дождаться **Готов**. При уже запущенном MCP окно подхватит
   in-memory runtime registry, кнопка повторного запуска будет отключена.

Перезапуск: **Стоп** → **Остановлен** (очистка завершена) → **Старт** → **Готов**.
Кнопки отключаются во время переходов/выполняемого native вызова. Отдельной
автоматической кнопки Restart нет: новый запуск не ставится в очередь заранее.

Окно управляет только child текущего CLO через существующий launcher/stop,
не ищет процессы по имени/порту, не выполняет HTTP или scene operations.
Отображение состояния читает память раз в 500 мс, только пока окно видно.
Долгий native CLO вызов по-прежнему может задержать интерфейс: кнопка Стоп не
обещает прерывания API. Перезапуск сервера не восстанавливает старые задания.
Ограничение runtime — 16 удерживаемых поколений за жизнь CLO — не изменено.
Изменения runtime source требуют свежего CLO, Stop/Start не hot-reload модулей.

## Короткая реальная приёмка — частичная, оставшиеся критерии pending

Длительность около минуты, без изменений сцены и без повторения P0–P3/load tests:

- После возврата Run и закрытия редактора окно остаётся немодальным, CLO отзывчив.
- Старт приводит к **Готов**; read-only MCP inventory/session check подтверждает
  ready и пустую очередь. Если сервер уже активен, не запускать второй.
- Крестик скрывает окно, MCP остаётся ready; повторный Run возвращает то же окно.
- При отсутствии active/waiting jobs нажать Стоп: ожидаются **Остановлен**,
  runtime FINISHED с exit_code=0, error=None, cleanup_pending=False.
- Нажать Старт: **Готов**, новый session_id/поколение; новый read-only MCP session
  check. Старые MCP HTTP sessions после перезапуска требуют переподключения.
- Финально Стоп либо оставить сервер запущенным по выбору пользователя.

Стоп-условия: зависание UI, ошибка, неверный поток, окно пропало после закрытия
редактора, чужой child затронут, остановка не завершилась. Не нажимать Старт
повторно после ошибки в надежде на retry; сохранить только error code/status.
Запасной способ остановки: `plugin/clo3d_mcp_stop.py` в том же CLO.

Локальные fake-controller и isolated real-Win32 window tests не доказывают
совместимость окна с host message dispatch CLO. Фактический частичный результат
приведён ниже; весь checklist пока не закрыт.

## Локальные результаты — 2026-11-09

- `uv run --frozen --with pytest pytest -q tests/test_control_panel.py tests/test_pipe_runtime.py -rs`:
  **47 passed**. Включён isolated real-Win32 window/button/hide/reopen test,
  без CLO, HTTP и реального старта сервера.
- `uv run --frozen --with pytest pytest -q -rs`: **698 passed, 1 skipped**,
  43.56 с. Skip — недоступно создание real symlink в asset helper, не тест панели.
- `scripts/check_acceptance_preparation.py --all-source`: **190 files, PASS**.
- `git diff --check`: PASS, только LF → CRLF warnings.

Transport/runtime state machine и dependencies не изменены. Новые файлы:
`src/clo3d_mcp/control_panel.py`, `plugin/clo3d_mcp_panel.py`,
`tests/test_control_panel.py`; README дополнен инструкцией. Commit/push нет.

## Частичный real результат — 2026-11-09

Позднее панель сохранена commit `edb7fad`, без push. Пользователь подтвердил
запуск панели, остановку MCP и новый запуск через ту же панель. После обновления
внешнего MCP (`842c1e8`) новые read-only discovery и scene-inspection прошли:
inventory14, readiness/idle guards valid, два списка count0, mutations0.
Подробности — `DOMAIN_BATCH_CHECK.md`. Вид панели намеренно остался прежним.

Это подтверждает пользовательский путь запуска/Stop → Start и доступность MCP
после него, но не весь UI/lifecycle checklist. Hide/reopen, отзывчивость после
закрытия редактора, точные FINISHED/exit0/cleanup flags и сравнение новой session
identity в этом прогоне отдельно не зафиксированы. Эти критерии остаются pending;
не выдавать isolated Win32 tests за их real-CLO подтверждение.
