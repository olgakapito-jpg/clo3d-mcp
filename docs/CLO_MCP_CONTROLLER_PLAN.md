# Переносимая форма и управление перезапуском MCP

Статус 2026-11-09: предложение, **не реализация macOS или remote restart**.
Текущий согласованный runtime остаётся Windows / один CLO / Named Pipe.

## Общая форма Windows / macOS

Предпочтительный кандидат — штатный `gui_api` целевой CLO 2026.1.336:
`IsGuiAvailable`, `CreateToolWindow`, `AddLabel`, `AddButton`, `ShowWindow`,
`SetWidgetText`, `SetWidgetEnabled`, `SetWindowCloseCallback`.
Не нужны Qt/PySide, собственный event loop или UI automation. По официальным
docs окно живёт после возврата скрипта, callbacks выполняются на главном потоке.
Это documented contract, не проверенный binding конкретной Windows/macOS сборки.

Сначала bounded probe наличия gui_api и отдельный GUI acceptance: создание
своего окна, callback/thread check после закрытия редактора, закрытие и повторный
показ. Не использовать `CloseAllWindows`: он может закрыть чужие script windows.
Хранить свои handles/callbacks и singleton, не переиспользовать invalid handles.
Нужен проверенный scheduler для асинхронного обновления статуса: button callback
сам по себе не даёт таймер. До его проверки можно явное «Обновить», но не loop.

Перенос формы не переносит серверную связку. Сейчас Windows-specific части:
Win32 UI timer, Named Pipe/ACL/peer PID, inherited CLO process handle, запуск
`.venv/Scripts/python.exe`. На macOS нужны согласованный отдельный transport
adapter, UI scheduling и pinned lifetime/ownership; `.venv/bin/python` — только
один из пунктов. Нельзя обещать macOS после замены двух кнопок. Новый transport
требует отдельного решения пользователя и real macOS acceptance, не fallback.

## Как ассистент перезапускает сервер без кликов по форме

Форма — view/controller client, не объект UI automation. Должен существовать
устойчивый controller/supervisor, который НЕ завершается при рестарте worker MCP.
Он владеет child Popen/identity; UI и ассистент вызывают один lifecycle controller.
Запрос restart самому worker MCP не годится как единственный способ: канал
исчезает при stop, а после падения worker запросить start уже негде.

Вариант для отдельного согласования: внешний controller с узким локальным
управляющим MCP endpoint, worker — текущий CLO API endpoint. Controller хранит
состояние в памяти; без command/discovery/heartbeat файлов, без arbitrary exec,
без kill по порту/имени, без автоматического replay. Форму связывать с ним только
через согласованный неблокирующий IPC; CLO UI callback не выполняет HTTP/wait.

Минимальный будущий контракт: status и один restart с expected generation/session,
проверкой idle/no unknown/no waiting, ограниченным сроком, request identity и
неповторяемостью. Авторизация локального пользователя, Host/Origin protections,
запрет wildcard CORS. Не называть loopback аутентификацией. Секреты — только в
памяти/защищённом inherited channel, не в репозитории, URL, stdout или отчётах.
Concurrent restart получает busy, не второй процесс; stale session — отказ.

Последовательность: reconcile idle → запрос restart → stop exact child →
подтверждение exit/cleanup → start один child → handshake/ready → новая generation.
При busy/unknown никакого force restart или scene cleanup. Deadline не означает
отмену API. При сбое — явный uncertain/failed state, без бесконечных retries.
Ассистент переподключается к новому worker и не возобновляет старый план.

Restart внешнего worker не hot-reload исполнителя/retained callbacks внутри CLO.
Обновление embedded runtime всё ещё может требовать полного перезапуска CLO.
Контроллер может восстановить worker, но не закрытый или зависший CLO.

## Порядок реализации после согласования

1. GUI binding/one-window acceptance Windows, затем реальная macOS проверка.
2. Перенос view на gui_api отдельно от transport; сохранить Win32 до приёмки.
3. Контракты controller/worker lifecycle, безопасность и IPC. Отдельное одобрение
   архитектуры/портов/платформенных adapters, потом реализация и fault tests.
4. Restart acceptance: idle success, stale/busy/unknown refusal, occupied port,
   child crash, concurrent requests, controller survives worker exit, no replay.
5. macOS transport/runtime P0-equivalent gate на реальном Mac до зависимых работ.

Источники: [GUI API](https://developer.clo3d.com/gui_api.html),
[tutorial](https://developer.clo3d.com/gui_api_tutorial.html),
[reference](https://developer.clo3d.com/gui_api_reference.html).
Прочитаны read-only, downloaded examples не исполнялись.
