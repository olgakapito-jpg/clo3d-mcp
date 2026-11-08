# P3: MCP HTTP и запуск из CLO

Статус: **P3 принят для проверенной среды CLO**: реальные MCP-вызовы,
одна mutation, отзывчивый UI, повторный start, stop/restart и завершение
сервера при обычном закрытии CLO подтверждены. P4 не начат.
P0/P1/P2 приняты, повторять их не нужно.

## Полученные реальные результаты P3

Пользователь сообщил STARTED generation=1, owner_thread=16720. Строка READY
в консоли не появилась, но MCP подключился. Из текущей сессии OpenCode реально
вызваны get_session_info: ready=True, executor_verified=True, connected=True,
clo_pid=18840, server_pid=20980, error=None; executor ping: pong=True;
GetPatternCount: 0. Затем **ровно один** create_test_rectangle вернул
created=True, pattern_count=1; отдельное последующее чтение подтвердило 1.
transport_status: ready=True, quarantined=False, waiting=0, error=None.

Это подтверждает реальный HTTP/pipe/executor/API roundtrip и одну mutation,
пользователь отдельно подтвердил появление квадрата и отзывчивость UI с закрытым
Script Editor. Визуальный размер 100×100 отдельно не измерен.
Причина отсутствия вывода READY
не установлена; по server readiness ACK исполнителем обработан.

Повторный запуск в первом CLO подтверждён: ALREADY_STARTED generation=1,
state=active, ticks=1768, owner_thread=callback_thread=16720, connections=1,
disconnects=0, handshakes=1, jobs=5, api_calls=3, pattern_count=1,
reentrant_ticks=0, error=None, service_ready=True. Повторное get_session_info
подтвердило прежние session_id, CLO PID18840 и server PID20980: дубликата
сервера от повторного запуска нет. cleanup_pending=True при активном сервисе
означает открытые ресурсы и само по себе не ошибка; после stop ожидается False.
Отдельный STARTED generation1 owner9604 относился ко второму экземпляру CLO,
что пользователь явно уточнил; это не проверка repeat-start одного сеанса.

Штатная остановка первого поколения подтверждена реальным CLO: STOP_REQUESTED
на tick2194 → FINISHED на tick2199, state=stopped, stop_reason=manual,
child_exit_code=0, оба cleanup_pending=False, error=None, service_ready=False.
Owner/callback thread=16720, connections1, disconnects0, handshakes1, jobs5,
api_calls3, count1, reentrant0. Последующий STOP_STATUS полностью совпал с
FINISHED: после остановки счётчики не менялись.

Запуск после stop подтверждён: STARTED generation=2, owner_thread16720;
из текущего OpenCode get_session_info вернул новый session_id
`b5e1df8906e3ee823dd7816af82f67b5`, прежний CLO PID18840, новый server PID21236,
ready/executor_verified/connected=True, error=None. Реальный ping успешен,
чтение числа деталей вернуло 4 (сцена могла редактироваться пользователем;
новых mutation ассистент не отправлял).

Пользователь затем обычно закрыл CLO без stop-скрипта. Проверка Windows после
его сообщения: процессы CLO PID18840 и MCP PID21236 отсутствуют; TCP listener
на порту8765 отсутствует. Оставшегося дочернего MCP нет. Точный интервал выхода
и exit code этого child при закрытии CLO не измерялись. **Gate P3 закрыт**;
принудительное падение настоящего CLO и длительная нагрузка этим не проверены.

## Подготовлено

- Официальный `mcp.server.fastmcp.FastMCP`, SDK 1.26.0 из текущего lock-файла.
- Один внешний процесс, HTTP только `http://127.0.0.1:8765/mcp`;
  FIFO32 + один active, Named Pipe с ACL текущего пользователя и HMAC/PID handshake.
- Сервер отслеживает унаследованный handle конкретного процесса CLO, не только PID.
- Готовность: проверочный executor ping, запущенный HTTP, SERVICE_READY и ACK.
- Только пять инструментов: `ping`, `get_pattern_count`, `transport_status`,
  `get_session_info`, `create_test_rectangle`. Последний добавляет один квадрат
   100×100 мм в начале координат 2D. Реальное создание через новый путь проверено;
   геометрический размер отдельно не измерен.
- `opencode.json` подключает `clo` только в этом проекте. Глобальные настройки не менялись.
  `protocol: legacy` означает классический MCP initialize, не старый файловый IPC.

## Инструкция запуска

1. Открыть свежий сеанс CLO: модули и native callbacks от старых диагностик
   нельзя безопасно обновлять на месте. Одна тестовая, несохраняемая сцена.
2. Открыть в CLO Script Editor файл `plugin/clo3d_mcp_start.py` из этого проекта
   и запустить один раз. Launcher использует `.venv/Scripts/python.exe` проекта,
   не встроенный Python CLO. Не запускать legacy `clo3d_mcp_plugin.py`.
3. Закрыть Script Editor и дать UI работать несколько секунд. Ожидается
   `[CLO MCP] STARTED (not yet connected)`, затем
   `[CLO MCP] READY http://127.0.0.1:8765/mcp` с `service_ready=True`,
   одинаковыми owner/callback thread IDs и `error=None`.
   Если CLO не передаёт `__file__`, launcher напечатает NOT_STARTED;
   тогда задать `ROOT` полным путём к своему checkout вместо `None`.
4. Сообщить ассистенту о запуске и прислать строку READY либо ошибку.
   Не останавливать сервер сразу: для проверки нужен доступ из текущего проекта.

Начальное ожидание ограничено: внешний startup deadline 30 секунд, внутренний
защитный предел 90 секунд. Если READY нет за 30 секунд, не запускать скрипт
многократно; прислать отчёт и остановить через stop ниже. Долгий CLO API может
блокировать UI; транспорт не умеет его прервать.

## Сквозная приёмка после READY

Действия согласуются по ходу проверки, без автоматизации UI:

1. Проверить `opencode mcp list`: `clo connected`. При необходимости подключить
   `clo` через интерфейс MCP OpenCode/OpenChamber. Настройка перечитывается без
   перезапуска OpenCode; запускать OAuth-вход для этого локального сервера не нужно.
2. Из текущего клиента вызвать status/info, executor ping и число деталей.
   `ping` проходит через CLO, status/info доступны во внешнем процессе даже
   при занятом CLO. Сравнить `clo_pid`, `server_pid` и идентичность сеанса.
3. Вызвать `create_test_rectangle` **ровно один раз**, затем прочитать число
   деталей: оно должно вырасти на одну; пользователь проверяет квадрат в CLO.
   При ошибке/тайм-ауте не повторять изменяющую команду автоматически.
4. Повторно запустить start в том же CLO: ALREADY_STARTED, прежнее поколение
   и PID внешнего процесса; второй сервер не появляется. Подтвердить отзывчивость
   UI с закрытым Script Editor.
5. Выполнить stop, получить FINISHED и повторный STOP_STATUS (ниже).
6. Запустить ещё раз, дождаться READY, затем нормально закрыть CLO.
   В течение примерно 6 секунд endpoint должен исчезнуть и принадлежащий этому
   сеансу MCP завершиться. Контролируемый тест смерти родителя уже автоматизирован;
   реальное закрытие CLO пока остаётся ручной приёмкой. Убивать CLO для этого не нужно.

## Остановка и отчёт

Запустить внутри CLO `plugin/clo3d_mcp_stop.py`. Ожидается STOP_REQUESTED,
затем в течение нескольких секунд FINISHED: `state=stopped`,
`child_exit_code=0`, `service_ready=False`, оба cleanup_pending=False,
`error=None`. Ещё один запуск stop должен показать неизменные счётчики.
Остановка затрагивает только дочерний Popen данного сеанса, не процессы по порту/имени.
Если сервер не завершает остановку за 3 секунды, применяется specific-child
fallback; `server_shutdown_timeout` — ошибка приёмки, а не успешный штатный stop.

При любом зависании UI, несовпадении потока, лишней детали, дубликате сервера,
ошибке cleanup или неизвестном исходе остановить испытание и прислать краткий
READY/FINISHED/STOP_STATUS. Не публиковать окружение или секреты. Занятый порт
даёт `http_bind_failed`; чужой процесс не завершаем и порт не перехватываем.

## Ошибки и границы безопасности

- Ошибки инструментов имеют MCP `isError=True` и structuredContent
  `{ok: false, error: ...}`: queue_full, queue_timeout, executor_unavailable,
  command_error, outcome_unknown. Неизвестный исход не означает, что сцена не менялась.
- Отмена MCP до dispatch удаляет задание; после dispatch отменяет лишь ожидание.
  Простое закрытие HTTP-соединения не является гарантированной отменой исполнения.
- Неизвестная отправленная команда не повторяется; результат отслеживается до
  завершения. После разрыва с unresolved dispatch сеанс карантинируется.
- Host проверяется строго, браузерные Origins отклоняются. HTTP не имеет отдельной
  аутентификации: доверяем локальным процессам компьютера. Loopback не защищает
  от вредоносного локального процесса. Не открывать порт в сеть и не ставить proxy.
- Нет файлов IPC, логов, heartbeat/discovery; stdout/stderr ребёнка — DEVNULL,
  безопасная диагностика через runtime и фиксированные exit codes.
- Удерживаются не более 16 поколений callback до перезапуска CLO. Память callbacks
  не освобождается преждевременно. Нет обещаний exactly-once через падение процесса.

## Выполненные автотесты

- Новый transport/executor/runtime/protocol regression: **117 passed**.
- После hardening focused: **59 passed, 1 failed**. Новый тест fallback ошибочно
  ожидал наблюдение завершения ребёнка за два callback; добавлен отдельный tick
  для poll завершения, штатный stop отделён от ошибочного timeout fallback.
- Финальный `uv run --frozen --with pytest pytest -q`: **249 passed**, без skips.
  Из них **13 реальных изолированных Windows pipe/process сценариев**, включая
  HTTP → отдельный service → pipe → fake API, ручной STOP и смерть pinned parent.
- Настоящие HTTP/официальный SDK: initialize/list/tools, concurrent FIFO, status
  при active job, mutation с fake API, MCP cancellation до/после dispatch,
  unavailable/isError, Host/Origin и занятый порт. Readiness ACK deadline и runtime
  failures проверены детерминированно.
- `opencode mcp list` прочитал проектный `clo`, но вернул ECONNREFUSED: на момент
   той предварительной проверки CLO launcher ещё не был запущен. Позже реальное
   подключение и вызовы успешно проверены, см. результаты выше.

Автотесты сами по себе не доказывают совместимость с реальным CLO; реальные
результаты приёмки записаны выше отдельно. Следующий этап — P4:
длительная нагрузка, модальные окна, fault matrix и документация. Они пока
не выполнены и приёмкой P3 не заявляются.
