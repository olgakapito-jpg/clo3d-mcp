# P4: регрессия, нагрузка и длительная работа

Статус: локальная часть выполняется; **реальный gate P4 не пройден**.
P0–P3 приняты; их повторение не требуется. Набор бизнес-API не расширяется.

Уточнение после реальной нагрузки: load1000 проверяет транспорт на лёгких
ping/count, а не производительность изменения выкроек, сцены или аватара.
Пользователь запросил дальнейшую проверку именно изменяющих команд ассистента.
Она требует отдельного поэтапного переноса/проверки API: legacy-обработчики
не включены в новый pipe executor, кроме диагностического квадрата. Массовое
подключение сторонних «100+ инструментов» не согласовано; ссылка на проект
для сравнения пока не получена. Перед продолжением пользователь попросил
зафиксировать текущую транспортную реализацию коммитами.

## Автоматизированные проверки без CLO

- `service_load`: 1000 executor jobs, concurrency10, настоящий HTTP/SDK,
  отдельный service-процесс, реальный Windows pipe, fake CLO API/timer.
  500 ping + 500 count, никаких mutation. Проверяются jobs1001 с начальным
  verification ping, bounded dedup, cached128, waiters0, waiting0, clean stop.
  Hard deadline запросов75с, isolated worker100с. Это не скорость настоящего CLO:
  его timer250мс, fake timer в нагрузочном тесте быстрее.
- Test-only bootstrap с Python audit hook запрещает файловые записи, создание,
  rename/remove до импортов server/SDK и на протяжении 1000 запросов/stop.
  Источники/venv читаются, NUL device разрешён; запрет завершает только тестовый
  child с exit91. Native writes сторонних DLL audit hook не доказывает.
- HTTP overflow: active1 + waiting32, queue_full, отключение исполнителя,
  release всех callers с unknown/unavailable, quarantine, без replay.
- `malformed_frames`: реальные байты oversized length, invalid UTF-8 и JSON list
  через Windows pipe отклоняются, pending I/O освобождается.
- Уже существующие P1–P3: framing/partial/midframe, authentication, stalled writer,
  deadlines/cancellation/late result, busy status, занятый порт и parent lifetime.
- `.github/workflows/windows-tests.yml`: Windows CPython3.11, frozen full suite,
  timeout10 минут, read-only repository permission. Workflow создан локально;
  GitHub runner **не запускался** (нет commit/push).

## Реальный CLO: подготовка

Один CLO, расходная сцена, `.venv` подготовлена. Запустить внутри CLO
`plugin/clo3d_mcp_start.py`, закрыть Script Editor. Ассистент проверяет
`get_session_info`: ready=True, connected=True, error=None.
Ниже запускается **внешний** Python из PowerShell, не Script Editor.
`scripts/verify_transport.py` не изменяет сцену, не пишет отчёты/IPC-файлы,
не устанавливает зависимости и не завершает процессы. Нет автоматических retries.

## Нагрузка: 1000 read-only запросов

```powershell
uv run --frozen python scripts/verify_transport.py load
```

Фиксировано 1000 запросов, batches10 (меньше capacity32), общий timeout900с,
per-call timeout65с. Обычно на реальном timer250мс это несколько минут,
не те секунды, что в fake scheduler. Каждые100 запросов — PROGRESS;
финал PASS содержит latency p95/max и число завершённых. Во время прогона
можно редактировать тестовую сцену и проверить отзывчивость; counts могут меняться.
Не открывать длительное модальное окно в этой части. Успех: completed1000,
PASS, без unknown/errors; UI остаётся пригодным к работе.

## Длительная работа: 30 минут

```powershell
uv run --frozen python scripts/verify_transport.py soak
```

Один read/ping примерно каждые5с, до360 запросов, длительность1800с после
initialization; общий timeout1900с. Нет catch-up bursts после задержек.
Каждую минуту — PROGRESS, затем PASS с elapsed/latency. Это отдельный новый
P4 gate, не повтор P0. Не сокращать длительность молча и не выдавать короткий
прогон за30 минут.

Во время soak:

1. Работать с лекалами и подтвердить отзывчивость при закрытом Script Editor.
2. Открыть обычное модальное окно CLO на **5–10 секунд**, затем закрыть/Cancel.
   Не автоматизировать клики. Отметить время и вид окна. Callback может
   задержаться или обслуживаться; оба наблюдения записываем честно.
3. Отдельно из OpenCode вызвать transport_status, пока окно открыто:
   внешний HTTP должен отвечать. Не обещаем исполнение CLO API при modal UI.
4. После закрытия — read/ping продолжаются в том же сеансе, нет replay/дубликатов.

Проверку окна согласовать с ассистентом заранее, чтобы status пришёл именно
во время открытого окна. Не держать его более30с: dispatch deadline30с может
законно дать outcome_unknown, это не означает смерть CLO.

## Стоп и критерии отказа

Внешний клиент: Ctrl+C или остановка его конкретной команды. Уже отправленное
чтение может завершиться после отмены. Сервер остаётся работающим.
В CLO: `plugin/clo3d_mcp_stop.py`; дождаться FINISHED с exit0, cleanupFalse,
errorNone. Не убивать процессы по имени/порту. Если UI завис, не устраивать
дополнительную нагрузку; записать обстоятельства и согласовать диагностику.

Отказ: FAIL/timeout, непрогрессирующая очередь после закрытия окна, новый
session ID без перезапуска, дубликаты, рост cache выше128, зависший UI,
остаточный child после остановки. Прислать только START/последний PROGRESS/
PASS или FAIL и FINISHED, не полный environment/секреты.

## Принудительный выход

Падение контролируемого родителя уже проверено actual Windows test, обычное
закрытие настоящего CLO — в P3. Принудительное завершение **настоящего CLO**
в P4 пока не проводилось: отдельное согласование точного PID, закрытие других
экземпляров/документов по выбору пользователя, и только specific-process action.
Не делать это автоматически в ходе нагрузки или вместо медленного callback.

## Реестр результатов

Пользователь подтвердил отзывчивость CLO с закрытым Script Editor во время
реального load1000. После этого попросил обойтись без отдельного 30-минутного
soak. Команда soak не запускалась; 30 минут стабильности не заявляются.
Длительная idle/редкая нагрузка остаётся непроверенным ограничением, а не
основанием повторять уже успешный load1000.

Реальная нагрузка1000 выполнена в CLO: session
`f64fda7462c83cc5f31076e2f2daf8cd`, CLO PID2844, MCP PID19176.
`PASS`, completed1000, elapsed750.66с (~12мин31с), latency_p95=7500мс,
max=7562мс при concurrency10. Это end-to-end latency с ожиданием FIFO,
не длительность отдельного CLO API. В ходе прогона count изменился0→5;
нагрузочный клиент отправлял только ping/count, mutation не отправлялись.
Кэш достиг128 и не рос. После прогона отдельный transport_status подтвердил
тот же сеанс, ready=True, waiting=0, waiters=0, active_id=None,
quarantined=False, cached128, error=None. Отзывчивость UI во время этого
прогона пока ожидает отдельного подтверждения пользователя.
Soak30мин/modal/forced-exit настоящего CLO ещё не выполнены.

Локальные и реальные результаты фиксируются ниже по факту; пока реальная
soak30мин/modal/forced-exit не выполнены, P4 не объявлять принятым.

Локально выполнено:
- Focused `tests/test_verify_transport.py tests/test_transport_server.py
  tests/test_winpipe.py`: **32 passed**.
- Полная suite `uv run --frozen --with pytest pytest -q`: **259 passed**, без
  skips; **15 actual Windows pipe/process сценариев**, включая нагрузку1000
  и повреждённые кадры. Предыдущий промежуточный full был257 passed; затем
  добавлены два теста границ read-only acceptance client (load/soak с fake clock).
- `uv run --frozen python scripts/verify_transport.py --help` успешно выполнен.
  Сама команда load/soak против настоящего CLO ещё не запускалась.
- При разработке audit guard нагрузка сначала завершалась exit91: stack trace
  показал stdlib platform/subprocess открытие Windows NUL. Разрешено только
  точное имя `os.devnull` (не файловые пути), запрет файловых записей сохранён;
  последующий actual load прошёл. Проверки audit guard отдельно тестируются.
- GitHub CI и реальные CLO проверки P4 пока не выполнены. После последнего
  полного прогона менялись только результаты в документации.
