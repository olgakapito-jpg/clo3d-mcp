# A0: статическая metadata binding, ручная проверка после restart

**Статус: подготовлено для совместной проверки; real CLO gate НЕ выполнен.**
Этот probe не новый MCP tool, не часть launcher/runtime и не замена P0.
Ни одного нового native метода для подготовки/тестов вызывать не требуется.
Источник расхождений — `CLO_API_OFFICIAL_AUDIT.md`; прежняя выборочная metadata
в `CLO_API_RUNTIME_EVIDENCE.md` не доказывает полный inventory или native работу.

## Назначение и границы

`plugin/clo3d_mcp_api_probe.py` — самостоятельный stdlib-only скрипт.
Импорт самого файла ничего не запускает. Явный запуск в CLO Script Editor
печатает **один** ASCII JSON document в stdout, затем синхронно возвращается.
Нет background threads, timer/callback, сети, файлов/IPC, native import,
конструирования options/types, чтения instance properties, вызовов getters,
setters, REST, GUI или сценовых изменений. Не импортирует legacy plugin
(`clo3d_mcp_plugin.py`, который способен auto-start) и не меняет действующий MCP.

Разрешён ровно один выбранный registry key: `pattern_api`, `export_api`,
`fabric_api`, `import_api`, `utility_api`, `rest_api`, `gui_api`, `ApiTypes`.
Проверяется **только уже загруженный** exact `ModuleType` в `sys.modules`.
Нет обхода остальных модулей, substring поиска или generic exec/import option.
`not_loaded` означает «не загружен», **не** «binding отсутствует».

Загрузку отсутствующих native modules нужно отдельно согласовать и проверить
по документации/точной сборке после restart. Этот файл не содержит даже opt-in
native import: безопасность import-time effects пока не доказана. Не добавлять
`import *`, не запускать основной launcher ради заполнения списка автоматически.

## Точный ручной запуск

После согласованного CLO/MCP restart и перед совместной проверкой:

1. Открыть **этот файл** `plugin/clo3d_mcp_api_probe.py` в CLO Script Editor.
   Не запускать его внешним Python для runtime evidence: там другие modules.
2. Проверить три literal-настройки наверху:
   `SELECT_MODULE = "pattern_api"`, `SELECT_TYPE = None`, `SELECT_CURSOR = 0`.
   Оставить hard limits без изменений. Запустить файл кнопкой Run ровно один раз.
3. Ожидать один JSON, возврат управления Script Editor и отзывчивый CLO.
   `status="metadata_only"`, `evidence="metadata_only_not_native_test"` означает
   лишь чтение metadata. `not_loaded` — допустимый результат, не failure binding.
4. Если `next_cursor` — число, после просмотра результата явно заменить
   `SELECT_CURSOR` на это число и запустить следующую страницу. Не ставить цикл.
   Для другого модуля/класса вернуть cursor в 0.
5. Для own members конкретного **обнаруженного класса** в выбранном модуле:
   например `SELECT_MODULE = "ApiTypes"`, `SELECT_TYPE = "ExportDxfOption"`,
   `SELECT_CURSOR = 0`. Это пример кандидата из official docs, не утверждение,
   что он реально доступен. Если модуль/тип не найден, остановиться и сверить
   namespace вместе; не угадывать другой module и не создавать экземпляр.

Остановка: скрипт заканчивается сам после одного JSON. **Нет stop-скрипта**,
состояния в builtins, фонового процесса или необходимого cleanup. Закрыть
Script Editor можно после возврата. Если UI не вернулся, не запускать повторно,
не пытаться скрыто kill/restart; сообщить наблюдение и согласовать дальнейшее.
Не запускать одновременно с активным UI job/callback diagnostics: сначала
дождаться спокойного сеанса согласованным способом, не меняя runtime этим probe.

## Контракт вывода

- `identity`: совпавшие allowlisted registry name и `__name__` из module dict.
  Нет `__file__`, `__spec__`, pid, session token или machine paths.
- `scope`: только module dict либо **собственный** class dict; нет inherited
  members/MRO inventory, instance access, enum conversion или enum construction.
- Только public ASCII identifiers до128 знаков. Private names и имена с
  TOKEN/SECRET/PASSWORD/CREDENTIAL/AUTHORIZATION/API_KEY/APIKEY/PRIVATE/SESSION/
  PATH/DIRECTORY/FILENAME опускаются. Это намеренно неполный inventory.
- Python functions: doc и форма параметров из exact code object, без
  annotations/default values/`__signature__`. Keyword defaults не исследуются.
- Exact builtin callable: bounded `__doc__`/`__text_signature__`; отсутствие
  text signature явно маркировано. Перегрузки могут остаться только в doc.
- Classes: identity/doc из raw own dictionary, **не** constructor signature.
  Используются фиксированные структурные descriptors самого `type`, чтобы
  не выполнять `__dict__` property или `__getattribute__` чужой metaclass.
  В class identity `null` означает missing/unsafe metadata, а не подтверждённый
  пустой namespace. Совместимость CPython/pybind установленной embedded сборки
  всё ещё pending: внешние fake-тесты её не устанавливают.
- Properties/classmethod/staticmethod и неизвестные pybind/native wrappers:
  `not_followed`/`unavailable_without_dynamic_access`. `callable()` проверяет
  только наличие call slot, не вызывает объект. Отсутствие metadata не доказывает
  отсутствие native метода. Не применять `dir(instance)`/`inspect.signature`
  или `getattr` как fallback.
- Значения констант: только uppercase public exact bool/None/finite float/
  int до64 бит. Строки, containers, enum objects и прочие значения скрыты;
  нет `repr`, `str`, рекурсивного обхода или исполнения пользовательского кода.
- Doc/text signature: до512 characters, известные path/URL/credential строки
  заменяются `[redacted]`; lone surrogates выводятся JSON ASCII escapes.
  Любой свободный docstring может содержать неизвестный секрет: автоматическая
  фильтрация не DLP-гарантия. Перед передачей просмотреть вывод и дополнительно
  скрыть личные/секретные данные. Не присылать paths/tokens и не коммитить отчёт.

Hard limits на один запуск: 12 public entries, первые4096 raw dictionary
positions (private/отфильтрованные тоже считаются), doc512 chars, name128 chars,
32 fixed Python parameters (+ varargs/kwargs), **24576 serialized ASCII bytes**
на весь JSON без завершающего newline. Никаких автоматических следующих страниц.
Candidate serialization также ограничена fixed page/doc/signature limits.
Это bound количества metadata work, **не гарантия wall-clock времени** native
binding/Script Editor. Размеры исходных doc не копируются целиком.

`cursor` — raw dict position, не номер public symbol. `next_cursor` действителен
только при неизменном dictionary/runtime: нет snapshot/atomic inventory guarantee.
`truncated=true`/`stop_reason=namespace_scan_limit` без next cursor — явная граница,
не «получено всё»; расширение лимитов требует отдельного review. Byte/page limit
сохраняет продолжение. Один module/page — не batch всех восьми bindings.

## Ошибки, выбор следующего действия и acceptance

`invalid_selection`: нет чтения native metadata; исправить literals по контракту.
`unsupported_module_type`/`unsupported_module_registry`/`module_identity_ambiguous`:
не делать dynamic fallback, совместно разобраться в namespace.
`type_missing_or_ambiguous_within_scan_limit`: тип не подтверждён, не конструировать.
`metadata_error`/`report_byte_limit`: вывод bounded без exception text; остановиться
и проверить реализацию/окружение. Автоматических retry/import/cleanup нет.

Критерии failure: зависание/заметная длительная блокировка UI, native вызов,
dialog, изменение сцены, запись IPC/отчёта на диск, неограниченный вывод,
private paths/tokens в неотредактированном отчёте, traceback с private данными
или неверная маркировка missing как absent. Не объявлять PASS по mock-тестам.

Valid example: module pattern_api/page0 → reviewed JSON → вручную next cursor.
Invalid/no-call example: module `os`, type `Thing()` или cursor `True` →
`invalid_selection`. Composition: official qualified symbol → this static
module/class page → отдельный контракт/tool/tests → позже согласованный native
read/effect acceptance. Неправильный выбор: для получения реального fabric count
не использовать этот probe; callable presence не выполняет `GetFabricCount`.

После реального запуска зафиксировать отдельно точный CLO build (вручную из UI,
без вызова API), выбранные module/type/cursor, redacted JSON и вывод о metadata.
Gate закрывается только для реально просмотренных страниц/сборки; native calls,
constructibility/options fields/defaults, API units/effects и полнота runtime
инвентаризации остаются **pending** до отдельных проверок.

Локальные fake проверки:
`uv run --frozen --with pytest pytest -q tests/test_api_probe.py`.
Полная suite: `uv run --frozen --with pytest pytest -q`.
Тестируются evil descriptors/metaclass/module hooks, отсутствие constructions/
native invocations, oversize docs/names, суррогаты, pagination/byte/scan limits,
redaction и явные missing/ambiguous statuses. Это не real-CLO acceptance.

Подготовка 2026-11-09: focused **41 passed**; совместный прогон с
`tests/test_verify_domains.py` — **89 passed**. Последняя полная suite в shared
checkout: **481 passed, 1 skipped, 1 failed**. Оставшееся падение вне этого probe:
`test_official_api_catalog.py::test_gui_notes_and_docs_anomalies_not_silently_corrected`
ожидал `wstring`, official raw return docs содержали `wide string`. Чужие файлы
не исправлялись. `git diff --check` для трёх файлов probe — без замечаний.
Real CLO/Windows pipe/MCP вызовы для этой задачи не выполнялись.
