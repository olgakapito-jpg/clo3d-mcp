# A0: статическая metadata binding, ручная проверка после restart

**Статус: real ApiTypes batch завершён: 73 класса, 103 страницы; сопоставлены
имена членов с official snapshot.** Constructors/defaults/native execution и
остальные module gates не приняты. Результат и границы evidence — в конце файла.
Этот probe не новый MCP tool, не часть launcher/runtime и не замена P0.
Ни одного нового native метода для подготовки/тестов вызывать не требуется.
Источник расхождений — `CLO_API_OFFICIAL_AUDIT.md`; прежняя выборочная metadata
в `CLO_API_RUNTIME_EVIDENCE.md` не доказывает полный inventory или native работу.

## Назначение и границы

### Текущий режим: один автоматический bounded запуск

По запросу пользователя теперь по умолчанию `RUN_BATCH=True`. Не нужно менять
SELECT_TYPE/cursor: entrypoint один раз явно импортирует ApiTypes, обходит module
pages, затем own class dictionary каждого найденного top-level класса. Вложенные
классы рекурсивно не обходятся. Наследованные members/instance properties не
читаются, constructors/getters/setters/exports не вызываются. Сам импорт source
file ничего не запускает. Другие native modules не импортируются.

**Запуск:** заново открыть `plugin/clo3d_mcp_api_probe.py` с диска в Script Editor
CLO, нажать Run один раз. Ожидается один компактный ASCII JSON
`schema="clo_api_static_batch_v1"`, содержащий pages и summary counters.
При `complete=true`, status=metadata_only, stop_reason=completed завершён только
отфильтрованный static traversal, не native acceptance. При partial/metadata_error
complete=false и stop_reason явно указывают границу/ошибку. Передать последний
JSON после просмотра на private/secret данные. Вывод на диск не записывается.

Лимиты одного Run:256 страниц,128 top-level class names,4096 emitted entries,
512KiB всего ASCII JSON (compact encoding),5с cooperative budget. На страницу
остаются12 entries/4096 raw namespace positions/doc512 chars и прежняя фильтрация.
Дедлайн проверяется между страницами и после их чтения: он не может прервать
import или отдельный structural native accessor. UI может кратко занять
синхронная обработка; гарантия жёстких5с отсутствует. Нет threads/timers/sleeps,
event pumping, IPC или auto-retry. Память/вывод ограничены даже при partial.

Порядок: module pages0→next_cursor → найденные top-level classes по порядку →
own-member pages каждого класса. Проверяются progressing cursors и structural
identity stamps (id ключей/значений первых4096 dictionary positions) до/после
страницы; изменение останавливает batch без принятия нестабильной страницы.
Это диагностика изменений, не гарантия атомарного snapshot. numeric enum values
не преобразуются, descriptors остаются not_followed. next_selection — только
место остановки, не разрешение автоматически повторить/продолжить запуск.

**Остановка:** скрипт заканчивается сам после JSON/лимита; cleanup/stop-скрипта
нет. При import_failed, metadata_error, partial, диалоге, зависании или неверной
identity — остановиться и прислать результат, не повторять автоматически. Если
UI не возвращается, повторный Run не нажимать; interrupt/дальнейшие действия
согласовать по наблюдению. Не выполнять batch одновременно с другим UI job.

Следующие разделы о SELECT_* описывают сохранённый ручной режим
`RUN_BATCH=False` и историю приёмки до автоматизации. Его single-page schema
остаётся `clo_api_static_probe_v1`; real batch результат записан в конце файла.

Локальная проверка автоматизации2026-11-09: focused `tests/test_api_probe.py`
**55 passed**; full `uv run --frozen --with pytest pytest -q -rs` —
**722 passed,1 skipped**,45.80с. Skip прежний real symlink unavailable.
Проверены paging модуля/класса, no constructor/property access, one import,
page/type/entry/byte/time limits, namespace mutation, exception privacy,
invalid cursor, scan limit и no fallback. Audit192 PASS, diff-check PASS.
Это fake/локальные проверки, не подтверждение batch в реальной CLO.

`plugin/clo3d_mcp_api_probe.py` — самостоятельный stdlib-only скрипт.
Импорт самого файла ничего не запускает. Явный запуск в CLO Script Editor
печатает **один** ASCII JSON document в stdout, затем синхронно возвращается.
Нет background threads, timer/callback, сети, файлов/IPC,
конструирования options/types, чтения instance properties, вызовов getters,
setters, REST, GUI или сценовых изменений. Не импортирует legacy plugin
(`clo3d_mcp_plugin.py`, который способен auto-start) и не меняет действующий MCP.

Разрешён ровно один выбранный registry key: `pattern_api`, `export_api`,
`fabric_api`, `import_api`, `utility_api`, `rest_api`, `gui_api`, `ApiTypes`.
Проверяется **только уже загруженный** exact `ModuleType` в `sys.modules`.
Нет обхода остальных модулей, substring поиска или generic exec/import option.
`not_loaded` означает «не загружен», **не** «binding отсутствует».

По явному запросу пользователя entrypoint теперь выполняет один буквальный
`import ApiTypes` перед пробой, только при SELECT_MODULE="ApiTypes", в том же Run.
Это согласованный import, не fallback после not_loaded. Ошибка даёт один JSON
`status="import_failed"`, без exception text, дальнейшего probe или retry.
Другие native modules не импортируются. `collect_metadata`/`render_metadata`
по-прежнему только читают loaded modules; импорт файла не запускает entrypoint.
Не добавлять `import *`, reload, pip или sys.path adjustments.

## Точный ручной запуск

После согласованного CLO/MCP restart и перед совместной проверкой:

1. Открыть **этот файл** `plugin/clo3d_mcp_api_probe.py` в CLO Script Editor.
   Не запускать его внешним Python для runtime evidence: там другие modules.
2. Проверить три literal-настройки наверху:
   Текущий следующий gate: `SELECT_MODULE = "ApiTypes"`,
   `SELECT_TYPE = "ExportDxfOption"`, `SELECT_CURSOR = 0` — уже в файле.
   Для module-only страницы SELECT_TYPE=None; текущий выбор — own class members.
   Оставить hard limits без изменений. Запустить файл кнопкой Run ровно один раз.
3. Ожидать один JSON, возврат управления Script Editor и отзывчивый CLO.
   `status="metadata_only"`, `evidence="metadata_only_not_native_test"` означает
   лишь чтение metadata. `not_loaded` — допустимый результат, не failure binding.
4. Если `next_cursor` — число, после просмотра результата явно заменить
   `SELECT_CURSOR` на это число и запустить следующую страницу. Не ставить цикл.
    Для другого модуля/класса вернуть cursor в 0. При потере namespace начать с0,
    не переносить старый cursor в новый dictionary.
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

## Первая real metadata страница B01 — 2026-11-09

Пользователь прислал JSON явного запуска probe внутри целевой CLO2026.1.336.
Выбор: `pattern_api`, `selected_type=null`, `cursor=0`. Schema
`clo_api_static_probe_v1`, identity registry/declared name совпали, scope
`module_dictionary_only`, status `metadata_only`, evidence
`metadata_only_not_native_test`. Это пользовательский вывод, не вызов через MCP.

Получены12 entries, все `builtin_callable`, callable_present=true. У всех doc
present без redaction/truncation, отдельный text signature missing_or_non_text.
Module doc также missing_or_non_text. Содержимое docstrings:

```text
GetPatternSize() -> int
GetPatternIndex(arg0: str) -> int
GetPatternIndexW(arg0: str) -> int
GetPatternIndexFrom2DView(arg0: float, arg1: float) -> int
GetPatternIndexFrom3DView(arg0: float, arg1: float) -> int
GetPatternInformation(arg0: int) -> str
GetPatternInformationW(arg0: int) -> str
GetPatternCount() -> int
GetPatternInputInformation: overload1 (arg0: int) -> str; overload2 () -> str
GetPatternInputInformationW: overload1 (arg0: int) -> str; overload2 () -> str
GetPatternPieceArea(arg0: int) -> float
GetLineLength: overload1 (arg0: int, arg1: int) -> float;
               overload2 (arg0: int, arg1: int, arg2: int) -> float
```

Последние три overload-записи сокращены из полученных docstrings, не новые
constructor/call signatures. Значения argN, units, namespace индексов и actual
overload execution этим не установлены. GetPatternSize и GetPatternCount не
объявляются эквивалентными по одинаковому return type.

`scanned=18`, `next_cursor=17`, `stop_reason=page_limit`, `truncated=true`:
штатное продолжение bounded страницы, не потеря/ошибка binding. Cursor — raw
dictionary position, не количество entries; следующую позицию брать только из
next_cursor, не вычислять как cursor+scanned. Лимиты12/4096/512/24576 соблюдены.
Отсутствие text signature не отсутствие callable: docstrings содержат формы
параметров и overloads. Native methods/constructors не вызывались этим probe;
реальные units/effects/options/constructibility и полная инвентаризация pending.
Отдельное визуальное подтверждение отзывчивости UI не получено.

Следующий короткий type-gate: один module-only запуск с
`SELECT_MODULE="ApiTypes"`, `SELECT_TYPE=None`, `SELECT_CURSOR=0`.
Не импортировать модуль, если результат not_loaded; не создавать экземпляры.
Это приоритетнее полного постраничного обхода pattern_api, callable inventory
которого уже доступен MCP. Продолжение pattern_api при необходимости — cursor17
в том же неизменном namespace, без автоматической пагинации.

## ApiTypes: not_loaded — 2026-11-09

Пользователь прислал следующий JSON: module=ApiTypes, selected_type=null,
cursor0, entries=[], next_cursor=null, status=not_loaded,
import_status=pending_joint_review_no_import. Schema/evidence/limits совпадают
с контрактом probe. Подтверждено только отсутствие загруженного exact module
в registry на момент проверки; доступность импорта/типов не установлена.
Не импортировали, не создавали options и не вызывали native API.

Read-only сверка official `scenario.rst.txt` подтвердила явный `import ApiTypes`
в Python examples; `optiontype.html` описывает ApiTypes options. Это documented
способ загрузки, не доказательство import-time safety установленной сборки.
Примеры целиком не запускались: они содержат scene/file mutations.

Следующий gate требует отдельного решения: разрешить один явный `import ApiTypes`
в CLO Script Editor, затем тот же module-only probe, либо отложить type-зависимые
операции. Сам static probe остаётся без native import/fallback. До разрешения
import gate pending; not_loaded не повышается до absent/unsupported.

После этого пользователь явно разрешил один import ApiTypes через выбор в чате.
Разрешение ограничено импортом этого модуля в CLO и повтором static module-only
probe: без constructors, getters/setters, выполнения official examples, changes
sys.path, pip installs или auto-retry. Native import ещё не выполнен/не принят.

Источники: https://developer.clo3d.com/_sources/scenario.rst.txt и
https://developer.clo3d.com/optiontype.html (прочитаны2026-11-09).

## ApiTypes: импорт и первая metadata страница — 2026-11-09

Пользователь сообщил `APITYPES_IMPORT_OK` после согласованного явного импорта.
Затем прислал два отдельных JSON: pattern_api/cursor0 со status=not_loaded и
ApiTypes/cursor0 со status=metadata_only. Первый относится к другому module
selection и не отменяет прежнюю успешную pattern_api страницу. Непрерывность
embedded namespace между запусками не установлена; причина различия неизвестна.
Не делать вывод о падении MCP, исчезновении pattern binding или необходимости
повторного импорта pattern_api по этому результату.

Последний JSON: ApiTypes identity registry/declared совпали, module_dictionary_only,
selected_type=null, 12 entries, scanned18, next_cursor17, page_limit/truncatedtrue.
Обнаружены class entries `WELD_TYPE`, `OBJECT_BROWSER_CATEGORY`, связанные имена
`FULLY_UNWELDED`, `DEFAULT_WELDED`, `FULLY_WELDED`, `SELECTED_WELDED`,
`OB_FABRIC`, `OB_BUTTON`, `OB_TOPSTITCH`, `OB_TRIM`, `OB_ZIPPER`, `OB_GRAPHIC`.
Class identity module=ApiTypes, name=null; own dict не подтвердил имя класса,
но registry key присутствует. Это ограничение metadata, не ошибка класса.
Class docs missing, constructor_not_inspected. Enum-like objects opaque,
value_withheld/not_followed: native numeric values не прочитаны и не установлены.

Подтверждены успешный возврат import и module-only metadata этой страницы.
Не подтверждены constructors, instance properties, options/defaults, native
effects и отдельное визуальное наблюдение responsiveness. В полученных отчётах
нет ошибки probe. Полный type-gate остаётся частичным.

Следующий bounded шаг: тот же probe ApiTypes/type=None/cursor17, один Run без
повторного import и без constructors. Если namespace не сохранился/not_loaded —
остановиться; не импортировать автоматически и не угадывать следующий cursor.

## Continuation ApiTypes17: namespace не подтверждён — 2026-11-09

Пользователь выполнил предложенный запуск ApiTypes/type=None/cursor17 и получил
not_loaded, entries=[], next_cursor=null. Пагинация остановлена. Source review:
probe делает только точный dict.get(sys.modules, module_name), не удаляет модули
и не выполняет native import. Наличие модуля в предыдущем Run не гарантировало
его наличие в следующем. Причина (контекст Script Editor/другая среда/другой
процесс/очистка registry) не установлена. Ни одна из гипотез не доказана.

Раздельные import → последующие Run больше не предлагать как надёжный workflow.
Кандидат исправления проверки — явный согласованный import и module-only probe
в одном запуске, с cursor0: старый cursor17 относится к прежнему namespace.
Это потребует разрешения на ещё один import; прежнее разрешение было на один.
Сам static probe остаётся без imports/fallback, runtime/MCP не меняются. Не
использовать reload, pip, sys.path tweaks или циклы/retries для обхода результата.

## Исправление запуска по запросу пользователя — 2026-11-09

Пользователь явно попросил добавить import перед пробой. Теперь
`run_selected_probe()` выполняет один literal import ApiTypes и затем один
static probe в том же запуске, при выборе ApiTypes. Настройки по умолчанию
ApiTypes/type=None/cursor0. Сам collector не импортирует, а импорт source file
не вызывает entrypoint. Никаких constructors, scene calls, retries или fallback.
Cursor0 выбран заново: namespace прежней страницы17 не сохранился.
Предыдущие запреты native import выше относятся к историческим runs до этого
согласованного изменения, не к новому entrypoint. Real запуск изменения pending.

## Real проверка исправленного entrypoint — 2026-11-09

Пользователь заново открыл обновлённый файл и прислал ApiTypes/type=None/cursor0:
status=metadata_only, identity match, 12 entries, scanned18, next_cursor17,
page_limit/truncatedtrue. Имена/kinds начальной страницы совпали с предыдущим
успешным ApiTypes0: WELD_TYPE/OBJECT_BROWSER_CATEGORY и10 opaque enum-like names.
Исправленный entrypoint import+probe в одном Run успешно вернул metadata;
not_loaded на этом запуске не повторился. Import-time эффекты и responsiveness
отдельно не измерены, constructors/options/default values по-прежнему pending.

Следующая настройка в файле — SELECT_CURSOR=17, остальное ApiTypes/None.
Явный import остаётся в entrypoint; отдельного import от пользователя не нужно.
Каждый запуск — отдельная ограниченная metadata страница, не atomic snapshot
всего модуля: совпадение страницы0 само по себе не доказывает неизменность всего
dictionary. При identity mismatch/not_loaded/ошибке STOP, без retry/reload.

## ApiTypes17: обнаружены options-классы — 2026-11-09

Пользователь прислал повтор страницы0 и новую страницу17. Последняя:
metadata_only, module identity match, module_dictionary_only, type=null,
12 entries, scanned30, next_cursor29, page_limit/truncatedtrue. Два opaque
имени OB_BUTTONHOLE/OB_PUCKERING;10 class entries: ObjectBrowserResult,
WindControllerOptions, AlembicUnit, ImportExportOption, VideoExportOption,
ImportZPRJOption, ImportDxfOption, RenderImageVideoOptions, RenderPropertyOptions,
ExportDxfOption. У class entries module=ApiTypes, name=null (own dict metadata
не подтверждает имя), docs missing, constructor_not_inspected. Это presence
классов, не доказательство полей/defaults или constructibility.

Следующий targeted gate вместо общего inventory — ExportDxfOption own class dict:
ApiTypes / SELECT_TYPE="ExportDxfOption" / cursor0. Настройки уже в файле,
согласованный import+probe в одном Run сохранён. Конструктор не вызывается,
instance properties не читаются, экспорт/запись файлов не выполняются. Цель —
увидеть доступные member names/kinds; property descriptors остаются not_followed.
Семантика/options defaults и real export acceptance остаются pending. Возврат
к module continuation при необходимости — type=None/cursor29 только с оговорками
неатомарного namespace; автоматического обхода нет.

## ApiTypes: получено окончание module-only обхода — 2026-11-09

Пользователь прислал14 JSON страниц с cursors
0,17,29,41,54,66,78,90,102,114,126,138,150,162. Связки next_cursor совпадают
со следующим cursor. На каждой status=metadata_only, identity ApiTypes совпала,
selected_type=null, scope=module_dictionary_only. Первые13 страниц содержат
по12 entries; последняя —2, scanned164, next_cursor=null, truncated=false.
Суммарно158 entries в присланных страницах:73 class и85 opaque_or_constant.
Это сумма наблюдений, не atomic snapshot runtime. Ограничение scan4096 не достигнуто.

Дополнительно к уже записанным страницам0/17 обнаружены классы:
ExportUSDOption, ExportTechPackType, ExportTechpackOption, CloApiRgb,
CloGroundData, CloApiRgba, AttachFileInfo, MimeData, CloApiRestRequest,
CloApiRestResponse, CloApiGraphicPosition, CloApiGraphicDimensions,
CloApiGraphicPlacementPoints, CloApiAnchorPoint, SeamlinePairGroupResult,
CloApiPoint, CloApiLine, CloApiIntersectionPoint, CloApiInternalShape,
ImportAlembicOption, PatternSnapShotPaperPreset, PatternSnapShotPaperUnit,
PatternSnapShotSizeOption, PatternSnapShotLineType, PatternSnapShotLineOption,
PatternSnapShotImageOption, PatternSnapShotPrintType,
PatternSnapShotInformationOption, PatternSnapShotColorwayOption, TextureMapTarget,
ObjectBrowserType, ObjectBrowserContextOptions, PropertyEditorContextOptions,
TransformOptions, ZipperObjectType, ZipperScaleUnit, GraphicRemoveMode,
ObjRegisterOptions, MaterialMapTransformationOptions, MaterialBaseColorMapOptions,
MaterialBaseColorOptions, MaterialNormalMapOptions, MaterialDisplacementMapOptions,
MaterialOpacityMapOptions, MaterialOpacityOptions, MaterialRoughnessOptions,
MaterialMetalnessMapOptions, MaterialReflectionOptions, MaterialFaceOptions,
MaterialTargetComponent, MaterialContextOptions, MaterialPropertyOptions,
CloApiAvatarMeasurement, HI_RES_TOLERANCE_TYPE, ButtonPairEdgeOrigin,
ButtonPairPlacementOption, CloApiGuiFormFieldType, CloApiGuiFormField,
CloApiGuiTextResult, CloApiGuiChoiceResult, CloApiGuiFormResult.

Module-only filtered traversal дошёл до конца. Это не полнота всех CLO types:
private/sensitive names намеренно исключены, inherited/instance members не
читаются. Расхождение с77 official types само по себе не missing binding.
Все class constructors остаются not_inspected; enum numeric values withheld,
class docs missing/own name null. REST/GUI типы лишь обнаружены: сетевые/GUI
операции не запускались. Поля/options/defaults/native semantics не проверены.

Targeted ExportDxfOption probe в этом сообщении отсутствует: во всех14 reports
selected_type=null. Текущий файл уже настроен ApiTypes/ExportDxfOption/cursor0;
нового общего module-only обхода не требуется. Следующий Run должен вернуть
scope=own_members_only_no_inherited_or_instance_access и selected_type=ExportDxfOption.

## Real автоматический ApiTypes batch и сверка документации — 2026-11-09

Пользователь передал локальный `result.json`. Файл не изменён и не добавлен в git.
Размер172706 bytes, SHA256
`e92be1ff1ab9706246d8008ebca227f47fe5ba078152470ac92806ad9c516fc9`.
JSON schema=clo_api_static_batch_v1, status=metadata_only, complete=true,
stop_reason=completed, next_selection=null, classes_completed=73.
Проверены все103 страницы: metadata_only, exact identity ApiTypes, старт cursor0
для каждой группы, непрерывные next_cursor, финал next_cursor=null/truncated=false,
отсутствие повторных имён в группе. Список73 class groups совпал с discovered.
Сумма736 entries совпала с summary:158 module entries и578 class-member entries.
Kinds:73 class,170 opaque_or_constant,481 property,12 opaque_callable.
Это пользовательский real-CLO metadata evidence; отдельное измерение времени,
UI responsiveness и native semantics этим JSON не подтверждены.

Сопоставление с `docs/api/official/types-001.json`…`types-003.json` (77 records,
582 documented members), с применением текущего `_public_name` фильтра:

- Все73 обнаруженных класса есть в official catalog; лишних class names нет.
- У этих73 классов найдены все550 разрешённых фильтром документированных member
  names. Недостающих разрешённых own member names нет. Это совпадение имён,
  не проверка annotations, значений, default arguments или поведения descriptors.
- Ещё15 документированных members этих классов исключены privacy-фильтром
  (fileName/filePath, image_path, primPath и подобные). Это не missing bindings.
- В class dictionaries присутствуют28 дополнительных имён: `name` и `value`
  у14 enum-like классов. Descriptors/объекты не раскрывались; это дополнительная
  metadata, не несовместимость с документацией.
- Из четырёх отсутствующих class names `CleanedPathResult` целиком исключён
  фильтром PATH. Его presence/absence этим результатом не установлена.
- `CLO_API_UNIT`, `HttpMethodType`, `RenderColorwayType` проходят фильтр, но их
  имена не найдены среди module entries. Документированные member names этих
  трёх enum-групп также не найдены на верхнем уровне ApiTypes. Это конкретные
  кандидаты расхождения формы/экспонирования с каталогом, не доказательство
  отсутствия соответствующей функциональности во всех CLO namespaces.
  Dynamic attributes, другие модули и конструкторы этим probe не проверяются.

Targeted `ExportDxfOption` теперь получен внутри batch: все11 документированных
полей найдены как property/not_followed, включая m_bDuplicateNotch,
m_ExportDXFFormatType, m_fScale и m_bMetric. Типы/default values, создание options
и ExportDxf overload не запускались. Повторный общий обход или отдельный запуск
ExportDxfOption для получения тех же имён не нужен. Static batch gate завершён;
дальнейшие real проверки должны относиться к выбранному небольшому пакету.

Проверка результата выполнялась офлайн внешним Python: разбор JSON, независимая
сверка агрегатов/цепочек/identity, сопоставление с сохранённым official catalog.
CLO повторно не запускался, native imports/calls не выполнялись. Последняя suite
для кода batch:722 passed,1 skipped (выше); при фиксации результата код не менялся.
