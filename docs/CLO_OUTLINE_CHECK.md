# B06 — bounded pattern outline read

Target: только CLO2026.1.336 (build сообщён пользователем). Source/live19 после
пользовательского полного restart. **Real gate BLOCKED, затем документированное
ограничение:** первое чтение собственной детали вернуло invalid_native_result;
ручной one-shot подтвердил native `[]`; различающий read-only опыт на двух
существующих деталях тоже дал invalid_native_result (раздел ниже). Причина
пустого/layout результата не установлена; tool остаётся read-only с явной ошибкой.
Нельзя hot-reload, retry или самостоятельно restart worker/CLO.

## Контракт и traceability

`get_pattern_outline({pattern_index,expected_name})` →
`pattern_index,pattern_name,point_count,points_mm,units,coordinate_frame`.
Внешний successful response также имеет `ok:true`. Это observation, не
`verified` mutation и не гарантия полной геометрии. Подробная карточка:
`CLO_MCP_TOOLS.md`, раздел19.

- Official: `pattern_api.GetPatternOutlinePoints#8b6d1cfeb17b2fc2`,
  `GetPatternOutlinePoints(int)->List[List[float]]`; runtime describe в прошлой
  live18 подтвердил binding/docstring; первое native чтение в live19 отклонено
  validator. Последующий отдельный ручной one-shot подтвердил exact list length0.
- Boundary segment endpoints, без curve controls. Миллиметры относительно
  TOP-LEFT bounding box, Y вниз; не global2D. Native traversal order сохраняется,
  closure/duplicates не нормализуются. Не утверждать соответствие lineIndex,
  winding, tessellation или возможность воссоздать кривую из точек.
- Strict required index0–255/name1–128 без bool/string coercion/extra keys.
  Unique exact name по свежему real-pattern list, максимум256деталей.
- Native exact list из1–512 list-пар finite numeric ±100000мм. Empty, oversized,
  bool/NaN/неправильный layout → invalid_native_result; без truncation/fallback.
  Это policy bound, не заявленный native максимум. Не polygon validator:
  не выводить straight-edge topology, минимум3points или замыкание из результата.
- Два native outline reads и три bounded list checks с дополнительным count
  после каждого list; exact point comparison. Максимум2outline+768name+6count
  native calls. Нет atomic snapshot/устойчивых IDs, ABA между reads не исключён.
  Промежуточный list проверяется до второго getter. Первый result копируется,
  чтобы заметить reused mutable native list.
- stale_pattern до getter; invalid_native_result для bad layouts/count/name;
  inventory_changed для list/point drift; command_error для native exception,
  api_unavailable для отсутствующего binding. Stop, без auto retry/fallback.
  Отдельная bounded read-only сверка readiness/fresh list разрешена после stop.

Transport, dependencies, UI callback/queue lifetime не менялись. Никаких
generic calls, legacy listener, exports/assets/files IPC. Local tests — не
реальное доказательство native frame/layout.

## Короткий real gate после пользовательского restart

1. Пользователь сам полностью закрывает/запускает CLO с нужным проектом и
   выполняет `plugin/clo3d_mcp_start.py`. Ожидание READY; стоп через
   `plugin/clo3d_mcp_stop.py` в том же CLO. Не запускать другие probes.
2. Agent discovery19/capability/get_session_info ready/idle, same session;
   fresh pattern/fabric lists + baseline geometry/mappings исходных<=5деталей.
3. Создать только собственный уникальный rectangle120×80мм вне исходного кроя
   по fresh bounds; independent list/geometry. Один outline read (=2native reads).
   Проверить four bbox-local corners [0,0],[120,0],[120,80],[0,80] в native order,
   допускается cyclic/reversed traversal, не объявлять универсальную closure.
   При отличии не подгонять schema автоматически, остановиться с evidence.
4. При успехе ещё один независимый outline read; move собственной детали на
   [25,-30]мм → independent geometry/read outline: local points должны остаться
   прежними. Любая ошибка/unknown прекращает mutations, не finally cleanup.
5. Успех → planned delete только своей uniquely named детали с fresh guard;
   final original list/geometry/mappings/fabrics должны совпасть fresh baseline.
6. Отдельно bounded outline read<=5existing pieces только при unique names,
   без edits. Проверить finite pairs/frame/double-read, не curved fidelity или
   sewing semantics. Final idle/error=null; UI confirmation пользователя отдельно.

Ограничение: <=1test piece,<=3mutations(create/move/planned delete),<=8MCP
outline calls (16native reads), без stress/повтораP0–P3/load10/read1000/soak.
Ожидаемая длительность несколько минут. Dialog/hang/exception/shape/frame drift,
session change, timeout/unknown → STOP, без retry/rollback/cleanup/kill.

## Локальная проверка

`tests/test_pattern_outline.py`: raw/native/result contracts, stale/duplicate
guards, list/point drift, aliasing, native faults before/after first read,
call bound, queue/executor duplicate cache, SDK metadata/coercion checks.
Workflow evals сохраняют historical14/16/18; current19 отдельный.
Фактические команды и итоговые counts фиксируются после запуска, не заранее.

Первый full run:921passed/1skipped46.70с; затем добавлены11count/name/bound fault
tests. Focused итог282passed2.31с для outline/workflow/domain runner. Предыдущие
два focused запуска обнаружили ошибки новых test fixtures (job_id и positional
dataset lookup), исправлены без ослабления validators. Eval37cases19tools,
self-test2valid/6invalid PASS. Installed/lock official mcp1.26.0 проверен.
Fresh live info после local full: ready/idle/error=null, прежняя session18 без
outline capability. Native scene operations в этом пакете не выполнялись.
Финальный full run и generated checks сообщаются при передаче.

## Real B06, 2026-11-09 — STOP на первом outline read

Пользователь полностью перезапустил CLO и запустил plugin. Новый CLO PID22924,
server PID31328, session `03cc0407367fefa6be814f25e2a79458`, discovery19 и capability
get_pattern_outline подтверждены, ready/idle/error=null. Сначала client catalog
ещё показывал18, после refresh actual19; никакого вызова отсутствующего tool.

Fresh original list5: index/name0:"2",1:"3",2:"5",3:"6",4:"1"; mappings[2,3,0,0,1],
fabric list4 без изменений. Геометрия после restart отличалась от прошлого
прогона **до любых новых mutations**; причина неизвестна. Использован fresh baseline:

- 0: position[956.7947998046875,1183.44482421875],area132081.421875,
  Height772.398071/Width258.042175;
- 1: [562.0184936523438,1089.6197509765625],area66726.578125,
  Height612.262390/Width201.852448;
- 2: [1348.8319091796875,1183.44482421875],area132081.625,
  Height772.398071/Width258.042236;
- 3: [-560.5061645507812,1109.6048583984375],area66726.5,
  Height612.262390/Width201.852448;
- 4: [0,1187.5904541015625],area315267.3125,
  Height752.800232/Width592.706665.

После same-session idle guard создана own `MCP_B06_outline_03cc0407`,index5,
points[[2000,1250],[2120,1250],[2120,1330],[2000,1330]],verified/executor62мс,
center[2060,1290],area9600.0009765625,Height80/Width120. Fresh list/independent
geometry PASS. **Первый единственный MCP get_pattern_outline(index5,exact name)
вернул {ok:false,error:invalid_native_result}.** Фактическое число native outline
calls внутри failed adapter неизвестно (0–2), публичный error не содержит stage.
Не выдавать предположение о tuple/empty/triple за найденную причину.

Сценарий остановлен. Второй outline,move,planned delete и existing outlines НЕ
выполнялись. Отдельная read-only reconciliation: same-session ready/idle,
original5 names/positions/areas/boxes **точно** fresh baseline,assignments unchanged,
fabrics4 unchanged. Собственная detail5 остаётся без перемещения/удаления;
count6 ожидаем, это не finally cleanup. Final status ready/idle/error=null,
cached30. Всего29scene commands (1create,1failed outline,27reads),4external info/
status calls; без retry/fallback/rollback и без записи native payload в IPC files.

### Ручной one-shot diagnostic — выполнен пользователем, не MCP fallback

Гипотезы: empty return, иной builtin container/row layout, либо invalid numeric
value; также публичный код скрывает list/count validation stage. Схема не
ослабляется без evidence. Подготовлен `diagnostics/clo3d_mcp_outline_probe.py`, затем
**выполнен пользователем в CLO** (результат ниже). Это explicit read diagnostic только для оставленной own
uniquely named детали; не native escape hatch/generic tool/автоматический retry.

Историческая инструкция: пользователь запускает `.py` **один раз** в Script Editor.
Теперь запуск выполнен; **не повторять**, one-shot marker не сбрасывать.
Перезапуск CLO/MCP не требуется. Другие MCP scene calls в это время не отправлять.
Требуется активный verified idle service на прежнем owner/callback UI thread;
probe проверяет thread/window/executor guards и временно busy guard от reentrancy.
Один GetPatternOutlinePoints по свежему индексу своей детали, before/after name
list/count; никаких setters,imports assets,callbacks,threads,files/network/IPC.
Сохраняет только one-shot marker в памяти builtins (до entry); повтор в этой
session блокируется даже после exception. Отчёт stdout — одна JSON строка
`clo_outline_probe_v1`: type/length и максимум4rows×4numeric cells,без произвольных
repr/строк/имён пользователя/paths/session tokens,без NaN/Infinity в JSON.
До517native calls при256pieces (2*256names+3counts+1targetname+1outline=517),
без циклов ожидания.

Ожидается status observed,outline_calls1,native type/length/sample. Это не PASS
контракта/координат даже при list result. Blocked/command_error/dialog/hang →
STOP, не повторять, показать JSON/error symptom. Длительность обычно секунды;
уже entered native call нельзя отменить timeout. Probe не создаёт постоянных
callbacks; после возврата останавливается сам. Общий service stop при доступном
UI — `plugin/clo3d_mcp_stop.py`. Не kill по порту/имени процесса.

Local diagnostic tests: `tests/test_outline_probe.py`; focused probe+outline
106passed0.50с. Реальный script result получен, но не заменяет failed MCP
gate. Diagnostic не меняет embedded production modules и не требует
fresh restart; после выяснения причины adapter fix потребует нового restart.

### Полученный результат пользователя, 2026-11-09

```json
{"evidence":"single_native_structure_not_acceptance","native":{"length":0,"rows":[],"type":"list"},"outline_calls":1,"pattern_index":5,"schema":"clo_outline_probe_v1","status":"observed","stop_reason":"stop_no_retry"}
```

Скрипт также записывает этот sanitized отчёт в
`<project>/acceptance-output/clo_outline_probe_v1.json` (gitignored, не IPC) и
печатает `[LOG] <path>`; при не найденном project root — `[LOG] unavailable`.

Предоставленный native log содержит один GetPatternOutlinePoints между успешными
before/after count/name reads (в каждой полной inventory read по6имён). `observed`
означает только завершённое наблюдение и совпадение списков; это **не принятие
outline контракта**. Exact builtin list пуст: нет tuple/triple/numeric layout для
адаптации. Для probe ожидаемое имя найдено ровно один раз по fresh index5, списки
до/после совпали; нет оснований объяснять пустоту отсутствием детали в этих reads.
Прямой вызов в Script Editor тоже пуст: проблема не ограничена MCP сериализацией.
Stage первоначального failed MCP call всё ещё не виден из публичного кода ошибки;
не утверждать, что diagnostic восстановил его внутреннюю историю.

Official #8b6d1cfeb17b2fc2 обещает boundary endpoints и empty при pattern not found.
Для этой существующей own детали наблюдение расходится с ожидаемым nonempty
результатом. Точная причина (binding/build/context/index semantics) не установлена;
не заявлять дефект всей сборки/неработоспособность всех деталей. Frame,coordinates,
point ordering,move invariance и existing patterns не проверены.

**Решение:** B06 остаётся BLOCKED. Production validator не ослаблять: `[]` не
успешный контур и не stale_pattern по догадке. Не синтезировать bbox corners вместо
native endpoints, не переключать overload/index space, не повторять вызов и не
сбрасывать marker. В этом ходе только source review/evidence/local tests, новых
live API calls, scene edits, cleanup или restart нет. Fixture остаётся по последнему
подтверждённому состоянию (новой geometry reconciliation после manual probe нет).

Следующая приёмка возможна только отдельным bounded distinguishing plan после
проверки build-specific API evidence: например, отдельный контракт documented
line-info getter, а не fallback этого инструмента. Сначала exact native signature,
индексы и output semantics; не считать соседний API работающим без real gate.
Отдельный source review выполнен: `CLO_LINE_API_CONTRACT_REVIEW.md`; line-info
JSON success/frame и length error semantics требуют real evidence,новых tools/
native calls нет. Это не разблокирует B06 и не разрешает outline fallback.

После получения user evidence добавлен fake regression для empty-native diagnostic:
observed не acceptance,ровно1native call,повтор блокируется. Production code не менялся.
Focused probe+outline107passed0.50с; full957passed/1skipped44.85с (real symlink
creation unavailable). Source mappings/coverage1134/eval37(self-test2valid6invalid)/
git diff --check PASS. Это local evidence,не новый real-CLO run.

## Различающий read-only опыт, 2026-11-09

Проверено, связана ли пустота только с нашей программно созданной деталью.
Та же live-сессия `acd3782f4a8156787f81435ca91e00e1`, ready/idle/error=null,6
деталей (fixture index5 осталась без изменений). Свежий список: index0 `"2"`,
index1 `"3"`, уникальные имена. Последовательно вызван публичный
`get_pattern_outline`:

- `{pattern_index:0, expected_name:"2"}` → `{ok:false, error:"invalid_native_result"}`
- `{pattern_index:1, expected_name:"3"}` → `{ok:false, error:"invalid_native_result"}`

Ноль мутаций, scene edits, retries, restart и fallback; после вызовов сцена не
менялась. Публичный adapter сворачивает empty/layout/bounds в один
`invalid_native_result`, поэтому по этим двум ответам нельзя отличить `[]` от
неподдерживаемого layout. Но установлено: проблема **не ограничена** нашей
`CreatePatternWithPoints` деталью — существующие пользовательские детали с
валидными именами тоже не дают результата через этот binding на CLO2026.1.336.

Вывод: `get_pattern_outline` остаётся read-only и возвращает явную ошибку; это
документированное ограничение сборки/окружения для проверенных сцен, а не
открытый вопрос, блокирующий набор tools (20 после добавления `get_pattern_lines`).
Схема не ослабляется, `[]` не
становится success, bbox/line fallback запрещён, marker probe не сбрасывается.
Точечный fix/диагностика layout потребовали бы изменения adapter + нового
restart и отдельного gate; в текущем объёме не выполняются.
