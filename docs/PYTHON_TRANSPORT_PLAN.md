# Python-транспорт CLO MCP — поэтапный план

Статус: переработка блокирующей файловой обвязки согласована пользователем.
P0 принят по реальным испытаниям CLO с согласованным уточнением длительности ниже.
P1 принят: локальные тесты, реальный pipe/API/reconnect/STOP и отзывчивость UI
с закрытым Script Editor подтверждены.
P2 принят: реальный диагностический цикл и отзывчивость UI с закрытым
Script Editor подтверждены. P3 принят: реальные MCP/API, UI, повторный start,
stop/restart и завершение MCP при обычном закрытии CLO проверены. P4 не начат.
Инструкции: `docs/P0_CALLBACK_CHECK.md`, `docs/P1_PIPE_CHECK.md`, `docs/P2_QUEUE_CHECK.md`,
`docs/P3_MCP_CHECK.md`.

## 1. Согласованная цель

Открыть CLO, запустить один `.py`, получить внешний MCP-процесс, привязанный
к этому сеансу CLO, и подключить к нему ассистента.

- Windows, CLO 2026.1, один экземпляр приложения.
- Только транспорт и диагностические команды; без Pattern Engine.
- Python внутри CLO и во внешнем процессе, без собственного C++.
- Межпроцессный обмен через Named Pipe, без файлов команд, ответов и heartbeat.
- MCP через Streamable HTTP на loopback, предлагаемый адрес `http://127.0.0.1:8765/mcp`.
- Основная очередь в MCP, один выполняемый вызов CLO API.
- Тестовую сцену можно изменять без checkpoint и дополнительных подтверждений.
- Исходники и `.venv` находятся на диске; запрет файлов касается IPC.
- Произвольный `exec`, UI-автоматизация, мультисеансность и удалённый доступ не входят в MVP.

## 2. Что найдено в текущем проекте

База: `olgakapito-jpg/clo3d-mcp`, `main`, исходный коммит `7c627a4`.

- `plugin/clo3d_mcp_plugin.py`: обработчики CLO API и диспетчер команд пригодны
  для повторного использования. Внизу файла — файловый listener и Win32-таймер.
- Таймер отключён по умолчанию: автор описывает проблемы на CLO 2024.1.
  Созданный timer_id сам по себе не доказывает выполнение callbacks.
- `start()` создаёт каталог обмена до проверки таймера; даже отказ от старта
  сейчас затрагивает диск. При ошибке SetTimer возможен блокирующий fallback.
- `src/clo3d_mcp/connection.py`: общие request/response-файлы, singleton,
  отсутствие очереди; повторяется любой CLO3DConnectionError, включая ошибку
  команды и тайм-аут. Этот механизм не переносим в новый транспорт.
- `server.py`: готовые MCP-инструменты; `__init__.py` запускает stdio.
- `extensions.py`: механизм пользовательских инструментов; для транспортного
  MVP его не включаем, чтобы не расширять набор исполняемых команд.
- `tests/`: файловый mock и проверки контрактов/обработчиков; реальный callback,
  Named Pipe и жизнь процесса они не проверяют.
- README обещает работающий listener, хотя main отключает его. Ссылки на
  `ala-clo-exec` и `clo3d_mcp_dev.py` не являются готовым launcher в этом checkout.
- Локальный baseline: **88 тестов прошли** через
  `uv run --frozen --with pytest pytest -q`.
- `uv.lock` фиксирует MCP SDK **1.26.0**. Установленный FastMCP поддерживает
  `streamable-http`, host, port и настройки transport security. Обновление до v2 не нужно.

## 3. Целевая архитектура

MCP-клиент -> HTTP -> MCP-процесс / FIFO -> Named Pipe -> исполнитель CLO -> CLO API.

Запускаемый из CLO launcher:
1. Проверяет внешний `.venv/Scripts/python.exe` и доступность модулей CLO.
2. Инициализирует исполнитель и его UI callback.
3. Запускает внешний MCP с параметрами текущего сеанса.
4. Асинхронно дожидается handshake и сообщает о готовности.

Внешний MCP создаёт Named Pipe server; внутренний CLO-исполнитель подключается
как клиент. Это техническое предложение: очередь и ожидание подключения живут
снаружи, а внутри CLO нет блокирующего accept. CLO отправляет READY, MCP выдаёт
одно задание. После результата исполнитель снова готов.

Внутри CLO — неблокирующий автомат состояний, а не цикл `while True`.
Windows I/O через ctypes/OVERLAPPED; обработчик только проверяет готовые события.
Вызовы CLO API идут из проверенного UI callback. Не предполагаем, что Python
background threads после возврата Script Editor будут обслуживаться.

## 4. Предлагаемая структура изменений

- `plugin/clo3d_mcp_start.py` — точка запуска из CLO.
- `plugin/clo3d_mcp_probe.py` — независимая диагностика среды и callback.
- `src/clo3d_mcp/protocol.py` — framing, проверка сообщений, ошибки протокола.
- `src/clo3d_mcp/transport/winpipe.py` — общий Win32 I/O без MCP-зависимостей.
- `src/clo3d_mcp/clo_runtime.py` — состояние исполнителя и UI-dispatch.
- `src/clo3d_mcp/jobs.py` — FIFO и состояния заданий во внешнем процессе.
- `src/clo3d_mcp/session.py` — идентичность сеанса и контроль жизни CLO.
- `src/clo3d_mcp/transport_server.py` — минимальный MCP HTTP entrypoint.
- Новые тесты для протокола, pipe, очереди, runtime и полного HTTP-цикла.

Названия можно уточнять при реализации. Общие модули, импортируемые в CLO,
не импортируют MCP, uvicorn и другие внешние зависимости. Launcher явно добавляет
локальный `src` в путь импорта; pip внутри CLO не требуется.

Существующие обработчики сохраняем. Не копируем весь server.py в новый модуль:
минимальный endpoint публикует только выбранные диагностические инструменты.
Старый stdio/file-режим временно остаётся отдельным legacy-путём для baseline,
но не используется и не включается автоматически новым launcher.

## 5. Этапы и критерии приёмки

### P0. Проверить жизнеспособность Python внутри CLO

Сделать probe без импорта старого listener и без создания файлов IPC:
- вывести sys.version, PID, Windows thread ID, доступность ctypes и CLO API;
- установить пробный UI callback и держать сильные ссылки на его объекты;
- убедиться, что callbacks идут после возврата скрипта;
- проверить совпадение потока и выполнить `GetPatternCount`;
- сделать явную остановку, повторный запуск и защиту от reentrancy;
- исключить блокирующий fallback и необработанные исключения в callback.

Первоначальный критерий (уточнение по согласованию ниже): 10 минут работы с отзывчивым UI, закрытие Script Editor,
несколько API-чтений из callback и 10 повторных стартов/остановок без зависаний.
Особенно проверить прекращение callbacks после остановки и безопасное удержание
их памяти при отложенных Windows-сообщениях.

**Стоп-условие:** если устойчивого Python UI callback нет, остановить дальнейшую
реализацию и согласовать следующий подход. Ни C++, ни UI-автоматизацию не вводить молча.

История подготовки P0 (2026-11-08; до реальных испытаний):
- Независимые `plugin/clo3d_mcp_probe.py` и `plugin/clo3d_mcp_probe_stop.py`.
- Проверка native UI thread, запрет reentrancy, удержание не более 16 поколений
  callbacks до закрытия CLO, bounded diagnostics; изначально автостоп через 10 минут.
- `uv run --frozen --with pytest pytest -q tests/test_probe.py`: **23 passed**.
  Включён настоящий Win32 SetTimer/DispatchMessage/KillTimer в отдельном процессе;
  остальные проверки используют fake backend/clock. Реальный CLO не запускался.
- `uv run --frozen --with pytest pytest -q`: **111 passed**.
- Следующий gate: ручная проверка в CLO по `docs/P0_CALLBACK_CHECK.md`.
  P0 пока **не принят**, Named Pipe/очередь/MCP HTTP ещё не реализованы.

Реальные испытания P0 и уточнение проверки:
- Пользователь подтвердил работу с закрытым Script Editor, редактирование лекал
  и отсутствие зависаний. Callback и API идут на одном native UI thread.
- Успешны ручная остановка, неизменные счётчики после повторного stop и десять
  коротких циклов (поколения 3–5, 7–13), везде без ошибок/незавершённой очистки.
- Длинный прогон поколения 6: 2374 callbacks, 120 API-чтений, максимум API 16 мс,
  ручная остановка. Это не менее примерно 597 секунд; точное время старый probe
  не сохранял, полные 600 секунд/автостоп этим логом не доказаны.
- По явной просьбе пользователя оставшаяся проверка автостопа сокращена до
  **60 секунд**, без повторения длинного прогона. Новый probe сохраняет
  `stop_reason` и `elapsed_seconds`, включая отчёт после повторного stop.
  Это отдельная проверка автостопа, не доказательство 600 секунд работы.
- Оставшейся проверкой был реальный CLO-отчёт минутного автостопа (результат ниже).
- После изменения: focused `tests/test_probe.py` — **26 passed**, полная suite —
  **114 passed**, включая настоящий Win32 timer в отдельном Python-процессе.
  Эти команды выполнены до получения реального результата минутного автостопа.

**Итог P0: принят для перехода к P1.** В новом сеансе CLO пользователь получил:
- `limit_seconds=60.0`, `elapsed_seconds=60.016`,
  `stop_reason=one_minute_limit`, `state=stopped`;
- 240 callbacks, 12 API-чтений, `pattern_count=5`;
- одинаковые owner/callback native thread IDs, `error=None`,
  `timer_cleanup_pending=False`, reentrant/ignored ticks равны нулю.
Префикс `STOP reason=manual` относится к последующему запросу отчёта;
сохранённая причина подтверждает предшествующий автоматический stop.
С учётом ранее проверенных десяти циклов, закрытия редактора, работы с лекалами,
отсутствия зависаний и согласованного минутного автостопа gate P0 закрыт.
Полные 600 секунд непрерывной работы отдельно не доказаны; это не выдаётся за
выполненную проверку. Вывод относится к проверенной сборке/среде CLO, а не ко
всем версиям приложения или всем API. Следующая реальная приёмка — P1 pipe/API.

### P1. Протокол и Named Pipe без MCP

- Кадр: uint32 little-endian длина + JSON UTF-8; начальный лимит 1 MiB.
- Handshake: версия протокола, session_id, PID, capabilities.
- Сообщения READY, JOB, RESULT, ERROR, STOP; идентификаторы job_id/session_id.
- Проверки структуры JSON, частичных чтений/записей и несовместимой версии.
- Только локальный pipe с ACL текущего пользователя; проверка peer PID,
  session_id и случайного секрета сеанса, переданного дочернему процессу
  через окружение. Секрет не логируется и не пишется в проект.
- Неблокирующее подключение и I/O внутри CLO; лимиты работы на один callback.
- Явное завершение I/O, удержание буферов до завершения CancelIoEx,
  закрытие handles и переподключение.

Приёмка: внешний тестовый клиент получает ping и число деталей из реального CLO;
разрыв и новое соединение не требуют перезапуска приложения; файлов IPC нет.

Реализация P1 (2026-11-08):
- `protocol.py`, `transport/winpipe.py`, `transport/channel.py`: строгие кадры,
  capabilities, bounded buffers/poll, локальная DACL, overlapped I/O и staged cleanup.
- `pipe_session.py`: HMAC/PID handshake, только ping/чтение числа деталей,
  ограниченный набор seen job IDs, без повторов после reconnect.
- `pipe_runtime.py`, `pipe_diagnostic.py`, `child_python.py` и два launcher/stop
  скрипта: два раунда, намеренный разрыв, reconnect, STOP и завершение дочернего
  процесса. Разрешённый venv запускается через свой base CPython с venv-hint:
  реальный PID владельца pipe совпадает с PID управляемого Popen, без ослабления
  проверки из-за Windows venv redirector.
- Исправлены две обнаруженные реальными Windows-тестами ошибки: PID redirector
  и ожидание только WinError 5 при коллизии listener (Windows возвращает и 231).
- Focused `tests/test_protocol.py tests/test_pipe_session.py tests/test_pipe_runtime.py
  tests/test_child_python.py tests/test_winpipe.py`: **70 passed**.
- Полная suite `uv run --frozen --with pytest pytest -q`: **184 passed**.
  Девять isolated Windows pipe/process сценариев действительно выполнены, не
  skipped: connect race, read/write, Unicode/fragmentation, reconnect/collision,
  stalled writer, pending connect/read cancellation и стабильное число handles,
  обрыв кадра, venv PID/prefix, отказ неверного HMAC и полный external roundtrip.
  Остальные новые проверки — чистые контракты и fake scheduler/API fault injection.
- Получен реальный CLO P1, поколение 1: 22 ticks, совпадающие owner/callback
  threads, connections=2, disconnects=1, handshakes=2, jobs=4, api_calls=2,
  pattern_count=0, reentrant_ticks=0. FINISHED и последующий STOP_STATUS одинаковы:
  stopped, peer_stop, exit_code=0, cleanup_pending=False, error=None.
  Пользователь отдельно явно подтвердил отзывчивость UI с закрытым Script Editor.
  **Gate P1 закрыт** для проверенной среды CLO. Повторный прогон не требуется.
  Инструкция и результат: `docs/P1_PIPE_CHECK.md`.
  FIFO и MCP HTTP этим диагностическим циклом не реализованы.

### P2. Очередь и семантика ошибок

- Ограниченная FIFO: первоначально 32 ожидающих задания; при переполнении ошибка.
- Состояния queued, dispatched, running, succeeded, failed, cancelled, unknown.
- Все API-вызовы последовательны, включая чтение.
- Отдельные сроки ожидания в очереди и ответа после отправки, monotonic clock.
- Отмена до отправки; прерывание выполняющегося CLO API не обещаем.
- Тайм-аут клиента не даёт отправить следующее задание поверх работающего.
- Нет автоматического повторного выполнения отправленной команды.
- Кэш известных результатов ограничен памятью текущего сеанса. После падения
  результат может быть unknown; exactly-once не гарантируем.
- Исчезновение callback/долгий API-вызов не приравниваем к завершению CLO.
- Новый сеанс не получает задания старого; неизвестный исход требует явной сверки.

Приёмка: параллельные обращения выполняются FIFO, отменённое ожидание не меняет
сцену, поздний ответ правильно сопоставляется, ошибка не вызывает повтор команды.

Реализация P2:
- `jobs.py`: 32 waiting + один active, монотонные раздельные deadlines,
  queued cancel, unknown со слотом до результата/READY, quarantine после разрыва
  unresolved dispatch, bounded history 128, server-generated IDs без replay.
- `async_jobs.py`: async callers с shield общего ожидания, ограничение waiters,
  корректная отмена до/после dispatch и завершение при shutdown. Истечение срока
  сразу публикует исход, до eviction cache; поздний RESULT обновляет lookup.
- `queue_session.py`: тот же аутентифицированный wire-протокол и peer PID,
  без ложного приравнивания READY к результату. State running поддержан только
  при явном execution receipt; нынешний протокол оставляет dispatched до ответа.
- `queue_diagnostic.py`, launcher/stop P2: ограниченный реальный CLO-тест,
  конкурентные callers, queue_full, queued deadline/cancel, dispatch deadline
  с поздним результатом и проверкой FIFO. Нет sleeps в CLO callback, HTTP или
  новых файлов IPC. Повторно используется принятый runtime с явным P2-профилем;
  запуск P1/P2 поверх другого активного диагностического сеанса запрещён.
- Автотесты P2 и transport regression: **115 passed**, включая новый обмен
  async FIFO через настоящий Windows pipe с отдельным executor-процессом и
  полный P2 launcher roundtrip с fake CLO API/таймером 250 мс.
- Полная suite `uv run --frozen --with pytest pytest -q`: **229 passed**, без
  пропусков. Всего 11 изолированных Windows pipe/process сценариев; проверки
  очереди/тайм-аутов используют fake clock, а не ожидание wall-clock в CLO.
- Получен реальный CLO P2, поколение 1: 21 ticks, owner=callback thread=10888,
  connections=1, disconnects=0, handshakes=1, jobs=5, api_calls=2, pattern_count=0,
  reentrant_ticks=0. FINISHED и последующий STOP_STATUS одинаковы: stopped,
  peer_stop, child_exit_code=0, оба cleanup_pending=False, error=None.
  Внешняя диагностика завершила проверки FIFO/cancel/deadlines/late result/
  queue_full успешно. Пользователь отдельно явно подтвердил отзывчивость UI
  с закрытым Script Editor. **Gate P2 закрыт** для проверенной среды CLO;
  повторный прогон не требуется. Инструкция: `docs/P2_QUEUE_CHECK.md`.
  P0/P1 повторять не нужно. HTTP и долговременный lifecycle остаются для P3.

### P3. MCP HTTP и запуск одним скриптом

- Минимальные инструменты: ping, get_session_info, get_pattern_count, transport_status.
- Один диагностический инструмент создания тестового прямоугольника для
  проверки изменяющей команды; не переносить остальные бизнес-инструменты.
- Асинхронные MCP-обработчики ожидают задания без блокировки HTTP event loop.
- Слушаем только 127.0.0.1, сохраняем проверки Host/Origin MCP SDK.
- Launcher использует явный внешний Python; не sys.executable встроенной среды.
- Готовность объявляем только после проверки pipe/исполнителя и HTTP endpoint.
- Занятый порт не перехватываем; ошибку запуска показываем без вечного ожидания.
- Повторный старт проверяет идентичность своего сеанса, не плодит процессы
  и не завершает чужой сервис на том же порту.
- Внешний MCP отслеживает handle именно процесса CLO; смерть CLO завершает MCP.
- Падение MCP не закрывает CLO. Повторный запуск launcher восстанавливает связку.
- Явная остановка мост/сервер без остановки CLO. Не оставлять дочерний процесс
  с stdout/stderr=PIPE без читающей стороны; диагностика без файлов и секретов.

Приёмка: один запуск `.py` даёт endpoint, выбранный MCP-клиент вызывает инструменты;
закрытие/падение CLO убирает сервер; повторный старт не создаёт дубликат.

Реализация P3 (2026-11-08):
- Пользователь подтвердил `http://127.0.0.1:8765/mcp` и подключение к текущему
  проекту OpenCode/OpenChamber. `opencode.json` содержит только проектный `clo`;
  глобальные настройки не менялись.
- `transport_server.py`: официальный FastMCP 1.26.0, async инструменты, сохранены
  Host/Origin protections, bounded FIFO, readiness ping + HTTP + SERVICE_READY/ACK.
- `plugin/clo3d_mcp_start.py` / `clo3d_mcp_stop.py`, service-профиль runtime,
  pinned inherited CLO process handle, ручной STOP, повторный start без дубликатов,
  безопасные фиксированные exit codes, отдельная ошибка занятого порта.
- Negotiated whitelist из трёх executor-команд, включая один диагностический
  квадрат; service dedup использует bounded high-water, не диагностический лимит64.
  Ошибки MCP имеют `isError=True`, отмена не повторяет отправленные команды.
- Финальная полная suite: **249 passed**, без skips; 13 настоящих изолированных
  Windows pipe/process сценариев. HTTP/SDK, cancellation, busy status, security,
  readiness и lifecycle проверены локально с fake CLO API/таймером.
- Реальные вызовы из текущего OpenCode: readiness/info/status, ping, count0,
  одна mutation created=True/count1, отдельное чтение1. Пользователь подтвердил
  квадрат и отзывчивость UI с закрытым редактором. Повторный start:
  ALREADY_STARTED gen1, тот же CLO/server PID, owner=callback16720, error=None.
- Stop gen1: FINISHED tick2199, manual, exit0, оба cleanupFalse, errorNone;
  повторный STOP_STATUS неизменен. Restart gen2: новый сеанс и server PID21236,
  CLO PID18840 прежний, readyTrue, ping/count успешны. После обычного закрытия
  CLO пользователем оба процесса и listener8765 отсутствуют (проверено Windows).
- **Gate P3 закрыт для проверенной среды.** Строка READY в консоли не наблюдалась,
  но readiness/ACK подтверждены сервером. Размер квадрата отдельно не измерен;
  падение настоящего CLO/длительная нагрузка остаются для P4. Инструкция и
  фактические результаты: `docs/P3_MCP_CHECK.md`.

### P4. Регрессия, испытания и документация

Начат по запросу пользователя после принятия P3. Локальная часть:
- `service_load`: 1000 read-only запросов, concurrency10, настоящий SDK/HTTP,
  отдельный процесс/Windows pipe, fake API, cached128 и bounded dedup.
  Python audit guard запрещает файловые записи в тестовом child (кроме NUL).
- Дополнены actual malformed-pipe и HTTP overflow/disconnect/release тесты.
- Добавлен Windows CI workflow (на GitHub ещё не запускался), README нового
  пути; upstream README сохранён в `docs/LEGACY_README.md` с attribution.
- `scripts/verify_transport.py`: внешний read-only клиент с bounded load1000
  и soak1800с, deadlines, stdout-only summaries, без автоматических retries.
- Инструкция: `docs/P4_TRANSPORT_CHECK.md`. Реальный gate P4 пока открыт:
  нагрузка/30 минут/modal UI/принудительное завершение CLO ещё не выполнены.
- Последние focused: **32 passed**; full: **259 passed**, без skips,
  15 настоящих Windows pipe/process сценариев. GitHub CI ещё не запускался.
- Реальный read-only load1000 принят: 750.66с, concurrency10, bounded cache128,
  чистая очередь/статус после, пользователь подтвердил отзывчивость UI с закрытым
  редактором. По просьбе пользователя отдельный soak30мин исключён и не запускался.
  Это не проверка нагрузки от изменения выкроек/сцены/аватара: следующая работа
  должна охватить именно изменяющие MCP-команды с проверкой эффекта, после
  согласования конкретного пакета API. Modal/forced-exit P4 не выполнены.

- Сохранить baseline старых контрактных тестов и добавить Windows CI для pipe.
- Проверить 1000 коротких запросов, очередь под конкурентной нагрузкой,
  повреждённые сообщения, занятый порт, отключение клиента и перезапуск MCP.
- На CLO проверить задержки при работе UI, модальное окно, изменение сцены,
  30 минут работы, остановку и принудительное завершение процесса.
- Проверить отсутствие request/response/heartbeat-файлов в новом пути.
- Исправить README: новый запуск, настройка клиента, различие нового и legacy-режима.
- Указать ограничения Python callback и невозможность гарантировать отзывчивость
  UI во время долгого блокирующего вызова CLO API.

## 6. Порядок согласования и работы

1. Пользователь проверяет этот план и подтверждает старт.
2. Сначала реализуется только P0; пользователь запускает probe в CLO и сообщает результат.
3. После успешного P0 — P1/P2 с автоматическими тестами и проверкой на CLO.
4. Затем P3/P4 и сквозная проверка из выбранного клиента.

Не требуется устанавливать C++ Build Tools, SDK или Qt ради этого плана.
Внешнее `.venv` уже создано; зависимости установлены из текущего lock-файла.

Клиент и порт для P3 согласованы: текущий OpenCode/OpenChamber, 127.0.0.1:8765.
P0–P3 приняты; выполняется P4, без повторения уже закрытых проверок.
