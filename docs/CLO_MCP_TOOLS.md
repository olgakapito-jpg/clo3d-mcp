# Каталог действующих CLO MCP tools

2026-11-09. Источник: `src/clo3d_mcp/transport_server.py`, `pattern_contract.py`,
`pattern_api.py`, `inventory_api.py`, `jobs.py`, `pipe_session.py`, launcher.
**Текущий набор** в исходном и live расширенном profile после пользовательского restart.
Line info: `get_pattern_lines` (#20) реализован на observed `status=success` схеме,
один native read на деталь, длины согласованы с `GetLineLength` 4/4 на тестовом
прямоугольнике; кривые/failure/frame после move/rotate не заявлены.
Outline: real gate BLOCKED и затем документированное ограничение — invalid_native_result
для own fixture, native `[]`, и тот же отказ на двух существующих деталях;
schema не ослаблена, не retry. Подробности: `CLO_OUTLINE_CHECK.md`.
Relationship tools17–18: limited real API/readback PASS, UI подтверждён пользователем;
внешний вид временной детали отдельно не зафиксирован. Исходные14 приняты ранее,
inventory real scope частичный (см. `CLO_INVENTORY_CHECK.md`). Не legacy47/full API.
Этот документ не обновляет runtime descriptions сам по себе.

API линий проверен отдельно: `CLO_LINE_API_CONTRACT_REVIEW.md`. `GetPatternLineInfo`
опубликован как tool20 `get_pattern_lines`; обе `GetLineLength` остаются
внутренней проверкой и не являются MCP tools. Один real one-shot
`GetPatternLineInfo` на own120×80 детали вернул `status="success"`,4 lines,
только documented fields; координаты — absolute API-mm frame, не bbox-local.
Length-correspondence выполнен:4/4 2-аргументных `GetLineLength` по returned
indices0–3 дали120/80/120/80 с delta0.0 и multiset match. Live tool20 на
существующих деталях: `length_mm` arc-like на кривых (>chord), `mid_mm` —
середина endpoints, orientation — dominant-axis; move/restore подтвердил
absolute frame. Rotation, invalid indices и failed/partial остаются открытыми.

## Общие контракты

- В примерах JSON ниже — synthetic args, не команда выполнить вызов. Индексы
  и expected_name брать из свежего списка реальной сцены, не копировать index0.
- Все pattern-команды (включая outline и lines), два inventory reads и две relationship-команды проверяют exact keys raw HTTP payload,
  очередь и executor.
  Числа strict int/float без bool, NaN/Infinity; имена1–128 Unicode code points
  с ord≥32, без surrogates. Это не полная Unicode-category проверка: пробельные
  имена, DEL и некоторые невидимые символы сейчас допускаются; выбирать осмысленные
  видимые имена. Координаты/смещения |v|≤100000мм;
  `pattern_index` strict int0–255. Фактическое наличие — отдельная проверка.
  Пять tools без аргументов (`ping`, `get_pattern_count`, `transport_status`,
  `get_session_info`, `create_test_rectangle`) теперь тоже проверяют raw payload:
  допускается только `{}` или отсутствие аргументов, extras → `invalid_parameters`
  до queue/native.
- Queue calls success: `ok:true` + поля команды. `transport_status` и
  `get_session_info` возвращают status dict **без обязательного ok**.
- Error tool result: `isError:true`, structured `{ok:false,error:<code>}`;
  для scene_change_unverified/outcome_unknown также scene_may_have_changed:true.
  Отсутствие этого флага при другом error НЕ доказывает отсутствие эффекта.
- get_session_info/status не идут в CLO; остальные через одну FIFO/UI executor.
  Defaults очереди30с до dispatch и30с после dispatch, клиент может ждать иначе.
  Срок после dispatch не прерывает native call. Поздний результат возможен.
- Read tools имеют hints readOnly=true/destructive=false/idempotent=true/
  openWorld=false. Pattern mutations: false/true/false/false. Diagnostic square:
  false/false/false/false. Эти hints не ACL и не полная гарантия качества.
- Geometry: `{index,name,position_mm:[x,y],area_mm2,bounding_box}`. Position —
  native reference position (в проверенной2026.1 центр), не vertex/top-left.
  Box — native bounded JSON record, в реальном тесте строки Height/Width;
  не считать универсальным массивом min/max. Полного outline тут нет.
- Mutation result кроме delete: `{ok:true,verified:true,pattern_count,pattern,
  executor_ms}`. Executor timing включает preflight/setters/readback; не чистое
  API time и не client latency. Read tools его не возвращают.
- Все mutations без auto-retry/rollback. `verified` относится только к
  описанным invariants. Multi-setter create/copy+name не atomic.
- После успешного RESULT сервер ждёт до 2 секунд READY именно своего job,
  прежде чем вернуть success. Это освобождение слота, не глобальная idle-гарантия:
  другой клиент может уже поставить/выполнять работу. Client idle/session guards
  остаются обязательны. Release-wait не меняет command-specific success schemas.
- `executor_release_timeout` / `executor_release_unavailable`: RESULT уже получен,
  но READY не подтверждён в срок либо связь потеряна. `isError=true`, `ok=false`,
  `scene_may_have_changed=true` консервативно даже для reads. STOP зависимых действий,
  не retry, не cleanup; позднее отдельная read-only сверка. Native command не
  отменяется и slot не освобождается по тайм-ауту. Native ERROR возвращается сразу,
  без ожидания READY и без разрешения продолжать старый сценарий.
- Все перечисленные поля args обязательны, defaults у pattern-команд нет.
  Output `pattern_count` — число деталей, `index` — текущий zero-based индекс,
  `name`/`deleted_name` — точные имена без нормализации, `verified` — только
  invariants данной команды. Area: finite 0–1e16 мм²; executor_ms: finite
  0–1e12 мс. Position bounded ±100000 мм. Bounding box сохраняет native layout
  (также возможны вложенные массивы/числа), его строки не получают выдуманных units.
- Source mapping ниже указывает точные `pattern_api` names; status/info —
  внешние snapshots, ping — executor response, introspection читает modules.
  Official overload/build traceability для полного API остаётся задачей A0;
  эти карточки фиксируют текущий код, а не закрывают все будущие DoD требования.

## 1. get_session_info

**Когда:** старт сценария, identity/capability/readiness. **Не:** версия CLO,
имя проекта, прогресс native вызова. Args `{}`. Возвращает status + clo_pid,
server_pid, capabilities, `server_build`, `executor_build` и CLO session_id (не
HTTP session ID). Builds —12hex SHA-256 исходников; совпали = Stop→Start загрузил
текущий код, разные = stale embedded `sys.modules` (перезапустить Start; script
Editor открывать с диска). Capabilities — executor commands: два внешних status
tools в этот список не обязаны входить. Выбирать реально опубликованные tools и
профиль совместно. Read-only внешний snapshot, не доказывает текущий callback
response. Пример: `{}` → сохранить session_id, проверить ready/error/quarantine,
сверить builds. Invalid choice: для измерения roundtrip нужен ping, не повтор
info в цикле. Composition: W1/W3; до mutation статус перепроверить, но guard не
atomic.
No-call: при ready=false не переходить к create, даже если capabilities есть.

## 2. transport_status

**Когда:** queue/busy/not-ready диагностика, включая занятой executor. Args `{}`.
Результат: session_id, connected/closed/quarantined/ready, waiting/capacity,
active_id/active_state, cached/history_limit/waiters, HTTP flags/endpoint/error.
Внутренний job ID не даёт отдельного опубликованного lookup/cancel tool.
Не native progress и не гарантия что API не блокирует UI. Пример `{}`.
Invalid choice: ready=true не доказывает успешное завершение предыдущей mutation.
Composition W1/W4; один bounded snapshot, не бесконечный polling.
No-call: active_id не аргумент для несуществующего cancel tool.

## 3. ping

**Когда:** проверить обслуживание FIFO/UI executor без scene API. Args `{}`;
результат `{ok:true,pong:true}`. No scene effect; handler отвечает на CLO UI
thread, но не вызывает GetPatternCount. Может ждать очередь; не обгоняет
занятый CLO. Ошибки readiness/очереди/unknown — общие ниже.
Invalid choice: для числа деталей get_pattern_count; для внешнего busy status
transport_status. Пример `{}`. Composition W1 после info при доступном executor.

## 4. get_pattern_count

**Когда:** число деталей без полного списка. Args `{}`; GetPatternCount →
`{ok:true,pattern_count:<nonnegative int>}`. Диагностический count не ограничен
лимитом256 в отличие от bounded pattern list. Не geometry/идентичность.
Пример `{}`; invalid choice: count2 не определяет имена/index выбранной детали.
Composition W1, затем list если нужны targets. API failure → command_error;
не подавлять его нулём.

## 5. create_test_rectangle

**Когда:** осознанный transport mutation diagnostic: один квадрат100×100мм
в начале2D через CreatePatternWithPoints. Args `{}`; result
`{ok:true,created:true,pattern_count}`. Проверяет count+1, **не** полный geometry
readback/unique name/долговременную identity. Не production polygon tool.
Не нужен в обычном создании — выбрать create_pattern. Error может возникнуть
после создания, даже если только command_error. Не повторять/не удалять по
«последнему индексу» автоматически. Composition: отдельный diagnostic recipe,
не включать принятый gate снова в общий batch. Пример `{}` только при такой цели.
No-call: запрос произвольного контура не переводить в diagnostic square.

## 6. list_clo_api

**Когда:** bounded список публичных callable, без их native invocation.
Args `{}`; result `{ok:true,modules:{<module>:[names]}}`. Фиксированные modules:
pattern_api/export_api/fabric_api/import_api/utility_api; до512имён на модуль.
Не включает rest_api/gui_api/ApiTypes; возможная обрезка не даёт полного catalogue.
Presence не означает зарегистрированный MCP tool или безопасный binding.
Invalid args `{"module":"rest_api"}` — extra key; describe имеет другой контракт.
Composition W2 → выбрать до16имён → describe → official docs review, не execute.

## 7. describe_clo_api

**Когда:** bounded docstrings фиксированного module. Args `module` из пяти выше,
`functions`1–16 ASCII public identifier strings1–128. Пример:
`{"module":"fabric_api","functions":["GetFabricCount","GetFabricName"]}`.
Result `{ok:true,module,functions:{name:{available:<bool>,doc:<str>}}}`;
doc до8192символов. available=false/empty doc не ошибка исполнения метода:
он не вызывался. Invalid:17имён, `_private`, неизвестный module, extra keys.
Не гарантирует семантику arg0/constructible types/полноту сигнатуры.
Composition W2; official/version сверка обязательна до нового adapter.

## 8. get_pattern_list

**Когда:** свежие indices/names targets; args `{}`. GetPatternCount/Name →
`{ok:true,pattern_count,patterns:[{index,name}]}` с последовательными индексами,
максимум256; не pagination. Сцена больше лимита → ошибка, не truncated success.
Duplicate names в списке возможны; mutations требуют unique target name.
Invalid choice: list не содержит outline/area/fabric assignments.
Composition W1/W3/W4; после delete перечитать перед следующим target call.
Пример `{}` → patterns с index/name; `{"limit":10}` invalid (extra key),
такого pagination аргумента нет.

## 9. get_pattern_geometry

**Когда:** position/area/native bbox одной детали. Args
`{"pattern_index":0}` только если0 из свежего списка. Result `{ok:true,pattern}`
по общей geometry schema. GetPatternPieceName/GetPatternPiecePos/
GetPatternPieceArea/GetBoundingBoxOfPattern; не полный contour.
Read не принимает expected_name, поэтому сравнить returned name с ожиданием
самостоятельно. Bool index или256 invalid, отсутствующий target stale_pattern.
Composition W1, независимый readback W3. Не использовать bbox для point editing.

## 10. create_pattern

**Когда:** одна новая деталь с уникальным именем — прямая или с curve-вершинами.
Args `points`:3–64 пары[x,y]мм, `name`:bounded unique name, optional
`vertex_types`:ровно len(points) значений 0/2/3 (0 straight, 2 spline, 3 Bezier).
Без `vertex_types` действует прежняя polygon-валидация: неявное замыкание,
Shoelace area ≥0.01 мм², adjacent |cross|≥1e-8, без самопересечений. С curve types
проверяются только типы/bounds: self-intersection и форма кривой не валидируются,
native curve/control semantics предварительные. Пример прямой:
`{"points":[[0,0],[120,0],[100,80],[0,60]],"name":"sample_panel"}`; curve:
`{"points":[[0,0],[120,0],[100,80],[0,60]],"name":"curve_panel","vertex_types":[0,2,0,0]}`.
Invalid: неверная длина/тип vertex_types, bool/1/4, самопересечение только для
straight, holes. Имя занято/нет места → отказ до creation.
CreatePatternWithPoints+SetPatternPieceName; проверяются count+1, порядок/имена,
новое имя; для straight — площадь с допуском, для curve площадь читается, но
polygon-shoelace equality не применяется. Не гарантируется curve fidelity,
3D placement/sewing. Setter/readback failure → scene_change_unverified.
Composition W3: returned pattern.index/name → fresh readback → copy/move.
Не вызывать diagnostic square для параметризованной формы.

Real curve gate 2026-11-09 (own pieces, затем planned delete): straight
120×80 → area9600, bbox120×80,4 линии120/80/120/80. Один spline-vertex
`[0,2,0,0]` → area10940.8838, bbox126.16×93.85,3 линии; curved segment
206.96мм (arc). Один Bezier-vertex `[0,3,0,0]` → area7633.6606, bbox120×80,
3 линии; curved segment160.32мм. Все vertex types2 сразу (`[2,2,2,2]`) native
отклонил: count не изменился, adapter вернул консервативный
scene_change_unverified без повтора. Вывод: VertexType работает, но допустимость
конкретной раскладки control-точек нужно проверять; curve semantics остаются
provisional.

## 11. set_pattern_name

**Когда:** переименовать одну uniquely named деталь. Args
`{"pattern_index":0,"expected_name":"sample_panel","name":"front_panel"}`.
Все поля mandatory; target index/name должен совпасть, новое имя свободно
(то же имя на самой детали допустимо). Result — общая mutation schema.
SetPatternPieceName, readback list/name/position/area; verified сохраняет list/order/count,
position и area. Не durable identity. Wrong expected/duplicates → stale_pattern.
Нельзя далее использовать прежний expected_name. Composition W3; readback затем
последующие операции с новым именем. Bool index/пустая строка invalid;
строка из пробелов текущим валидатором не отклоняется.

## 12. copy_pattern_with_offset

**Когда:** копия одной детали со смещением относительно текущей позиции.
Args `{pattern_index,expected_name,name,dx,dy}`; пример
`{"pattern_index":0,"expected_name":"front_panel","name":"front_copy","dx":250,"dy":30}`.
CopyPatternPieceMove+SetPatternPieceName; проверка returned index/count+1/остальных имён,
new name, position=old+[dx,dy], area сохранена. Result содержит **новую** pattern.
Не абсолютная позиция и не обещание symmetry/сохранения всех sewing relations.
dx/dy finite bounded; итоговая position тоже в bounds; target/new-name stale
guard, максимум256деталей. Invalid: `dx:true`; отказ до setter при занятом name.
Composition W3; copy return index вместо guessed last index. Error может
оставить unnamed/copied деталь: STOP, без auto-delete/re-copy.

## 13. move_pattern_relative

**Когда:** сдвинуть целую существующую деталь, не создать новую/двигать точку.
Args `{pattern_index,expected_name,dx,dy}`; пример
`{"pattern_index":0,"expected_name":"front_panel","dx":20,"dy":-5}`.
SetPatternPieceMove; verified проверяет relative position, area, count/names.
dx/dy finite |v|≤100000; итоговая position тоже должна остаться в bounds.
Tolerance position/area: rel_tol1e-5 или abs_tol0.05 соответствующей единицы.
Не считать это strict0.05 для любых больших значений и не путать мм с мм².
Не 3D arrangement/point editing. Composition W3: fresh list/geometry → move →
отдельный geometry read. Если нужен duplicate — выбрать copy, не move.

## 14. delete_pattern

**Когда:** удалить ровно одну однозначно идентифицированную деталь в разрешённом
scope. Args `{"pattern_index":0,"expected_name":"front_copy"}`. DeletePatternPiece;
result `{ok:true,verified:true,pattern_count,deleted_name,executor_ms}`,
**нет pattern**. Readback сравнивает точный оставшийся список имён/order.
Нет гарантии полного восстановления связанных швов/material relationships;
индексы сдвигаются. Нельзя delete по prefix без fresh уникального target.
Wrong expected/duplicate name → stale_pattern, no automatic retry.
Composition W3 planned cleanup только own objects, затем fresh list; два delete
не gather и не использовать старый второй index. После ошибки — W4, не cleanup.

## 15. get_fabric_list

**Когда:** bounded список Fabric из Object Browser текущего проекта, без colorway.
Args строго `{}`, extras invalid до enqueue. Result
`{ok:true,fabric_count,fabrics:[{index,name}]}`; zero-based
Object Browser indices, fabrics≤256, names0–256chars без control<32/
surrogates; empty/duplicates сохранены. Три count reads и два прохода имён
перепроверяются, но snapshot не atomic, indices не durable IDs.
Source: fabric_api.GetFabricCount(_bCurrentColorway=False) с явным bool keyword,
GetFabricName(int ObjectBrowserIndex), без default/int/colorway fallback. Нет setters/imports/
assignments. При limit/changed/invalid result STOP, не partial success/retry.
Valid `{}`; invalid `{"limit":10}` или `{"colorway_index":0}` — такой selection
не реализован. Composition: info/guard → pattern list → guard → fabric list;
это не подтверждает assignment к деталям. Не выбирать для «примени ткань».
**Ограниченный real gate ACCEPTED:** два одинаковых списка count4/names,
пользователь подтвердил4ткани в GUI и нормальный UI. Затем5read-only cross-domain
cycles+final lists PASS, counts4/1/5,geometry5,status idle/error=null. Не assignment.
Прежний colorway prototype снят до приёмки; один внешний
worker restart не reload embedded modules. Runbook — `CLO_INVENTORY_CHECK.md`.

## 16. get_avatars

**Когда:** количество и имена загруженных аватаров, не import/pose/geometry.
Args строго `{}`. Result `{ok:true,avatar_count,avatars:[{index,name}]}`;
≤64, indices zero-based в порядке export_api.GetAvatarNameList, не persistent ID.
Имена0–256chars без control<32/surrogates, duplicate/empty names допустимы.
Source: export_api.GetAvatarCount()/GetAvatarNameList(),3count+2list reads.
Повторные count/list должны совпасть, не гарантия atomic scene snapshot.
No setters/imports/hidden recovery. Errors limit/changed/invalid result → STOP,
не retry/fallback или auto-import. Valid `{}`; invalid `{"avatar_index":0}`
(target getter отсутствует). Composition: info/guard → avatars → guard → pattern
list; не делать вывод о fit/pose/attachments. Real empty и count1/name path
получены; geometry/visual acceptance pending. Полная карточка/overload IDs/tests/
cross-domain recipe — `CLO_INVENTORY_CHECK.md`.

## 17. get_pattern_fabric

Читает Object Browser fabric index/name одной uniquely named детали. Required
`pattern_index` strict0–255, `expected_name` exact1–128chars из fresh list.
Result `{ok:true,pattern_index,pattern_name,fabric_index,fabric_name}`; fabric
name0–256chars. До/после snapshots, repeated mapping, no sentinel/fallback.
Read-only, не assignment/import. stale/changed/invalid/error → STOP/no retry.
Valid `{pattern_index:0,expected_name:"front"}` synthetic; bool index/extra
colorway invalid до enqueue. Composition list → read → guard → assign. Anti:
не использовать для «измени материал». Real: stable mappings5, independent
readback0→1→3 тестовой детали и preservation после planned delete PASS; UI подтверждён.
B05C: copy inheritance/rename/move/independent assignments/lower-delete index shift
и fresh-index assignment PASS в отдельном fixture; не полная topology/material гарантия.
Полный source/limits/errors/runbook — `CLO_FABRIC_ASSIGNMENT_CHECK.md`.

## 18. assign_pattern_fabric

Назначает одну имеющуюся Object Browser ткань одной uniquely named детали,
native option1 фиксирован, без colorway management/linking/face selection.
Required `{pattern_index,expected_name,fabric_index,expected_fabric_name,
expected_current_fabric_index}`; strict indices0–255, pattern name1–128/fabric
name0–256 exact+unique; current из fresh read. Result `{ok:true,verified:true,
pattern_index,pattern_name,fabric_index,fabric_name,previous_fabric_index,executor_ms}`.
До setter guards/readback preflight; после все mappings кроме target unchanged,
lists/target name/position/area/bbox проверены. Не atomic/full material proof.
Valid synthetic `{pattern_index:0,expected_name:"front",fabric_index:1,
expected_fabric_name:"jersey",expected_current_fabric_index:0}`. Bool/missing/
extra assign_option invalid. Не import. После входа error/False → potential effect,
STOP/no automatic retry/rollback/cleanup. Recipe read→assign→independent read.
Limited real API/readback PASS на собственной детали0→1→3 с preservation5,
плановым delete и final checks; UI подтверждён пользователем. B05C additional
composition/index shift PASS,temporary appearance не оценена. До256patterns/fabrics,
max4123native reads в UI callback. Full card — `CLO_FABRIC_ASSIGNMENT_CHECK.md`.

## 19. get_pattern_outline

**Source/live19, документированное ограничение (было BLOCKED)**, read-only. Читает конечные точки boundary сегментов
одной uniquely named детали. Native source:
`pattern_api.GetPatternOutlinePoints#8b6d1cfeb17b2fc2`, one real-pattern-list index.
Presence/docstring подтверждены в CLO2026.1.336; первое MCP чтение собственной
детали отклонено как invalid_native_result. Отдельный ручной one-shot пользователя
подтвердил native exact list `[]` для существующей uniquely named детали index5;
причина пустоты неизвестна. Различающий read-only опыт на двух существующих
деталях (`"2"`,`"3"`) тоже вернул invalid_native_result, то есть проблема не
ограничена программно созданной деталью. Публичный adapter не различает
empty/layout/bounds. Не повторять, не считать пустой контур успехом, не делать
bbox/line fallback; точечный fix требует отдельного adapter-изменения и restart.

Required `pattern_index`: strict int0–255, `expected_name`: exact1–128chars из
fresh `get_pattern_list`, уникальное имя. Extra keys/bool/string-index/missing
fields → invalid_parameters до queue/native. Никаких optional flags/пагинации.

Result `{ok:true,pattern_index,pattern_name,point_count,points_mm,units:"mm",
coordinate_frame:"bbox_top_left_y_down"}`. `point_count`1–512, `points_mm` —
native ordered list `[x,y]`, finite numeric ±100000мм. Координаты от **верхнего
левого угла bounding box**, Y вниз; **не global2D** и не position_mm reference.
Curve controls исключены native API; closure/duplicates/order сохраняются без
нормализации. Не выводить winding, tessellation, segment/lineIndex correspondence,
внутренние линии/швы или возможность восстановить curved shape/площадь.

Unique stale guard до getter; два exact endpoint reads с тремя list/count checks,
до256patterns. Максимум2outline+768name+6count native calls; read-only, но native
call может задержать UI. Не atomic snapshot/устойчивый ID или full geometry proof.
Пустой/слишком большой/неправильный native result отклоняется, не обрезается.

Errors: stale_pattern — fresh list отдельно; inventory_changed — данные между
reads/list checks изменились; invalid_native_result — unsupported layout/bounds;
api_unavailable — binding отсутствует; command_error — sanitised native exception.
При любом error/unknown **STOP, без automatic retry/fallback**; readiness/status
и bounded fresh list можно проверить отдельно, не продолжая старый сценарий.

Valid synthetic: `{"pattern_index":0,"expected_name":"panel"}`.
Invalid/no-call: `{"pattern_index":true,"expected_name":"panel"}` или extra
`line_index`/`include_controls`: raw validation до dispatch. Domain composition:
session/capability → fresh list → outline → schema/name/frame check. Cross-domain:
fresh list → outline → `get_pattern_fabric` с тем же fresh target → независимая
инспекция endpoints и назначения (не material/3D validation).
Anti-selection: для площади/позиции — `get_pattern_geometry`; для управляющих
точек кривых/швов/индексов сегментов доступного tool пока нет, не generic call.
Реальная приёмка/stop/failure criteria: `CLO_OUTLINE_CHECK.md`.

## 20. get_pattern_lines

**Source read-only, один real schema+length сэмпл.** Внешние линии одной uniquely
named детали по `pattern_api.GetPatternLineInfo#45ddc71808d7eb67`, RealPatternList
index. Не outline fallback и не заменяет `get_pattern_outline`.

Required `pattern_index` strict int0–255, `expected_name` exact1–128 из fresh
`get_pattern_list`, уникальное. Result
`{ok:true,pattern_index,pattern_name,line_count,bounding_box_mm:{min_x,min_y,max_x,max_y,width,height},lines:[{line_index,length_mm,orientation,location,start_mm,end_mm,mid_mm,mid_norm}],units:"mm",coordinate_frame:"api_2d_mm"}`.
`line_count`1–512 == len(lines); `line_index` уникальны0–511, native order
сохраняется; `mid_norm`0–1 внутри bbox. Координаты — native 2D мм; live-проверка
move `[25,−30]`/restore подтвердила absolute API frame и translation invariance,
не bbox-local; rotation/scale не проверялись. `length_mm` — native длина: на
прямых равна chord, на кривых больше chord (arc-like, max48.69мм в сэмпле), но
независимого arc-измерения нет. `mid_mm` — арифметическая середина start/end
даже на кривых, не точка дуги. `orientation` — dominant-axis label, не точное
направление (наклонный сегмент может быть `vertical`). Не выводить closure,
tessellation, seam/lineIndex topology, graded points или форму кривой.

Один native line-info read плюс list/count checks, до256patterns; не atomic
snapshot и не durable identity. Строгий bounded JSON: exact str≤64KiB, depth16,
duplicate keys/NaN/Infinity rejected, documented fields only. Errors:
stale_pattern, inventory_changed, invalid_native_result, api_unavailable,
command_error. Native invalid index наблюдался как `{"status":"failed","message"}`;
публичный tool превращает любой non-success/malformed в `invalid_native_result`,
не отдавая message. При любом error/unknown STOP, без retry и без fallback на
outline.

Valid synthetic: `{"pattern_index":0,"expected_name":"panel"}`.
Invalid/no-call: bool/string index, extra keys, несовпадающее/неуникальное имя.
Composition: session → fresh list → lines → независимое чтение geometry тем же
fresh target; cross-domain → `get_pattern_fabric`. Anti-selection: конечные точки
контура — `get_pattern_outline` (limited), управляющие точки кривых/швов — tool нет.
Evidence: `CLO_LINE_API_CONTRACT_REVIEW.md`.

## 21. add_seamline_pair

**Source, whole outer line pair.** Один `pattern_api.AddSeamlinePairGroup` 6-arg
overload: `(pattern_a, line_a, pattern_b, line_b, direction_a, direction_b)`.
Child overloads (childA/childB), `AddSeamlinePairGroupPartial`, topstitch, buttons,
`MergeSewnPatterns`, `DeleteLine` в tool не входят.

Required: fresh real-pattern indices/уникальные `expected_name_a/b`, `line_a_index/
line_b_index` из `get_pattern_lines`, strict bool directions (true forward),
разные детали. Preflight проверяет line count и geometry; один native call;
readback требует seam count +1 и неизменные line lengths/geometry/order. Result
`{ok:true,verified:true,seam_count}`; native false/exception или drift →
`invalid_native_result`/`scene_change_unverified`, без retry и cleanup.
Probe 2026-11-09: native return bool true, count16→17, lines/geometry unchanged.
Live tool gate on build975dcebc4e10: own MCP_SEAM_C/D line0 →
`{verified:true,seam_count:18}`, readback lines/geometry unchanged.
Один вызов = **одна пара кромок**, и каждая кромка — **одна `LineList`-линия**.
Multi-segment edge (кромка, разбитая насечками) требует несколько вызовов;
если кромка смоделирована одной curve/`Polyline`-линией, один вызов покрывает
её целиком. Merge-lines/edge-path API нет. Для трубы из двух
панелей нужны два шва: `A.left↔B.left` и `A.right↔B.right`; `line0↔line0`,
`bottom↔bottom` или один шов трубу не закрывают. Directions выбирать по
физическим концам кромок, не предполагать `True/True`. Исторический live gate
(C/D line0) подтвердил native call и seam_count, но не закрытость изделия.
Valid synthetic: `{"pattern_a_index":0,"expected_name_a":"panel","line_a_index":0,
"pattern_b_index":1,"expected_name_b":"back","line_b_index":0,
"direction_a":true,"direction_b":true}`. Composition: fresh list → lines → seam →
read seam count/connectivity отдельно. Одинаковый `pattern_a_index ==
pattern_b_index` отклоняется (`invalid_parameters`): darts и self-seam
выполняются через `add_seamline_pair_partial` с ratios 0..1. Anti-selection:
partial seam/merge/curve editing — не этот tool. Skills: `clo-sewing`,
`clo-seamlines`. Evidence: `CLO_SEAMLINING_CHECK.md`.

## 22. import_avatar

**Source, .avt avatar import.** Один `import_api.ImportFile(file_path)`; live
binding `ImportFile(str)->bool` доступен, а `ImportAvatar` требует
`ImportExportOption`, которого в этой сборке нет (describe available=false).
Child/pose/measurement/project/import-other-format не входят. Required absolute
`.avt` path <=128MiB; путь не эхоится/не логируется. Preflight проверяет
файл/размер; один call; readback требует native true и avatar count +1. Result
`{ok:true,verified:true,avatar_count}`; false/exception/count mismatch →
`invalid_native_result`/`scene_change_unverified`, без retry/fallback.
`.avac`/ImportAVAC маршрут не используется. Pose/fit/measurements — отдельные
пакеты; visual/3D не гарантируется. Valid synthetic:
`{"file_path":"C:\\assets\\mannequin.avt"}`. Anti-selection: `.avac` или pose
файл — не этот tool. Live gate: Mannequin avt → count0→1, name
`Female_Mannequin_final_v11_Aforsize_03`; path не эхоился.

## 23. get_arrangement

**Source, read-only.** `GetArrangementList()` для длины библиотеки и
`GetArrangementOfPattern(i)` для каждой детали. Native dict содержит строки:
`ArrangementName`, `ArrangementOffsetX/Y/Z`, `ArrangementOrientation`,
`ArrangementType`; tool парсит numeric strings в finite numbers и возвращает
`pattern_index/name`, `arrangement_name`, `offset{x,y,z}`, `orientation`,
`type`, `arrangement_library_count`, `units:"native_unspecified"`. Units/degrees
не заявлены; 3D fit не проверяется. Read-only, list drift → inventory_changed,
bad shape/numeric → invalid_native_result, без retry. Set/arrangement/drape tools
не входят. Live probe: count4, library110, все поля строки. Valid synthetic: `{}`.
Composition: fresh list → get_arrangement → при необходимости будущие setters.
Anti-selection: «поставь на аватар/сделай посадку» — не этот tool.

## 24. set_arrangement

**Source, fitting assignment.** `SetArrangement(pattern_index, arrangement_index)`
из библиотеки `GetArrangementList` (110 avatar points), затем один
`ReDrape3DArrangement(ApiTypes.ImportExportOption)` с flags
`bAddArrangementPoints/bAutoCreateFittingSuit/bMoveGarment`. Required fresh
pattern index/unique name, arrangement_index<library; readback
`GetArrangementOfPattern` должен совпасть с library preset по name/type/offset/
orientation. Result `{ok:true,verified:true,pattern_index,pattern_name,
arrangement_name,offset{x,y,z},orientation,type,units:"native_unspecified",
redrape:true}`. Offset units/degrees не заявлены; 3D fit visual-only; другие
детали не переставляются; ошибка после SetArrangement может оставить assignment,
без retry/cleanup. Live probe: Body_Front/Back/Arm points → детали встали на
аватар (UI подтверждён). Anti-selection: mass-layout всех деталей и simulation —
отдельные пакеты. Evidence: `CLO_FIT_CHECK.md`.

## 25. set_arrangement_orientation

**Source, fitting orientation.** `SetArrangementOrientation(pattern_index,
orientation)` — целое `0..359` для уже назначенной точки; затем один
`ReDrape3DArrangement(ApiTypes.ImportExportOption)` с теми же flags. Required
fresh index/unique name. Preflight читает текущий `GetArrangementOfPattern`;
после setter readback обязан вернуть запрошенный orientation и сохранить
name/offset/type, затем ReDrape и повторный readback orientation; drift списка →
`inventory_changed`. Result совпадает по схеме с `set_arrangement`:
`{ok:true,verified:true,pattern_index,pattern_name,arrangement_name,
offset{x,y,z},orientation,type,units:"native_unspecified",redrape:true}`.
Native units и ось вращения не установлены; 3D-посадка по-прежнему visual-only,
roll вокруг точки крепления может не убрать пересечение с аватаром — simulation
отдельно. Ошибка после setter может оставить orientation, без retry/cleanup.
Valid synthetic: `{"pattern_index":0,"expected_name":"MCP_SEAM_A","orientation":90}`.
Invalid: `orientation` 360/True/"90", stale/ambiguous name. Anti-selection: это
не 3D-gizmo/tilt и не simulation; произвольная ось/позиция не поддерживаются.
Live readback gate build `7e0f73d2c06e`: MCP_SEAM_A 180→90, verified, post-ReDrape
orientation 90, остальные детали не изменены. Проверка пользователя: в 3D деталь
визуально не изменилась — orientation field сам по себе не переставляет деталь на
этой сборке. Evidence: `CLO_FIT_CHECK.md`.

## 26. set_arrangement_position

**Source, fitting position.** `SetArrangementPosition(pattern_index,
position_x, position_y, offset)` — native signature `positionX, positionY,
offset`, не world x/y/z. Целые `0..100` (наблюдаемый диапазон; units
`native_unspecified`), затем один `ReDrape3DArrangement(ApiTypes.ImportExportOption)`
с теми же flags. Required fresh index/unique name. Preflight читает текущий
`GetArrangementOfPattern`; после setter offsets обязаны совпасть с запросом, а
name/orientation/type — остаться прежними; затем ReDrape и повторный readback
offsets; drift списка → `inventory_changed`. Result совпадает по схеме с
`set_arrangement`. Это **не свободный 3D-трансформ**: визуальный эффект не
доказан и проверяется только глазами. Ошибка после setter может оставить
состояние, без retry/cleanup. Valid synthetic:
`{"pattern_index":0,"expected_name":"MCP_SEAM_A","position_x":40,
"position_y":70,"offset":60}`. Invalid: 101/-1/True/50.0/"50", stale name.
Live readback gate build `57a23bf2cfdb`: 50/75/50→50/75/80, verified, offsets
прочитаны точно, но визуально деталь не сдвинулась. Evidence:
`CLO_FIT_CHECK.md`.

## 27. get_3d_screenshot

**Source, artifact.** `export_api.ExportThumbnail3D(path)` — silent снимок
текущего 3D-окна в PNG; диалог `ExportSnapshot3D` не используется. Tool сам
генерирует путь под `acceptance-output/screenshots/`, adapter проверяет, что
native вернул тот же путь и файл 1..16MiB, внешний server читает bytes и
возвращает MCP `Image` content. Сцена не меняется, произвольный путь не
принимается, retry нет. Пустой/non-image/oversized файл → ошибка. Это основной
self-check инструмент. Live build `aafcfac0323d`: PNG ~129–173KB, MCP image
content получен, файл под `acceptance-output/screenshots/`. Снимок зависит от
текущей 3D-камеры: после seam/solver камера может зумиться, нужен ручной Fit/zoom.
Valid synthetic: `{}`.

## 28. get_arrangement_list

**Source, read-only.** `GetArrangementList()` — до4096 точек: index, name, type,
offset{x,y,z}, orientation. Числовые native строки парсятся в finite numbers;
units `native_unspecified`. Индекс использовать в `set_arrangement`; имена не
считать durable ID. Без setter/drape/fit. Live build `b2f3fce822d6`: PASS,
`library_count=110`, имена/offsets/orientation читаются; extra `ArrangementIndex`
в library record игнорируется adapter-ом. Valid synthetic: `{}`.

## 29. get_seamline_pairs

**Source, read-only.** `GetSeamlinePairGroupCount/Name/ListInPattern` — число
швов, имена групп и membership по каждой детали (до4096 групп/256 деталей).
Это проверка швов без mutation; `seam_count` больше не единственный источник.
Delete/merge/partial/topstitch не входят; drift списка → `inventory_changed`.
Live build `aafcfac0323d`: 3 группы, C/D в одной, A/B в двух, 3D_TEST без швов.
Valid synthetic: `{}`.

## 30. get_avatar_measurements

**Source, read-only.** `utility_api.GetAvatarMeasurements(avatar_index)` —
до512 мерок: name/type/value/basic_length/surface_length/unit. Нужен перед
`set_pattern_edge_to_avatar_measure`; height/linear мерки для pin могут быть
отклонены native. Не pose/fit/measurement editing. Live build `b2f3fce822d6`:
Mara вернула 79 мерок (78 `Default` + 1 user `Circumference`); Default-мерки
Line Pin не поддерживают, user Circumference работает. Valid synthetic:
`{"avatar_index":0}`.

## 31. get_pattern_avatar_attachments

**Source, read-only.** `GetAllPatternToAvatarMeasures()` + `GetPinListSize()` —
пары pattern↔avatar measure (до1024, de-duplicated по именам) и число pins.
Пары keyed by name: одинаковые имена могут схлопнуться. Без attach/detach и
fit-гарантии. Live build `aafcfac0323d`: `pair_count=0, pin_count=0` на текущей
сцене. Valid synthetic: `{}`.

## 32. set_arrangement_shape_style

**Source, fitting style.** `SetArrangementShapeStyle(pattern_index, "Flat"|"Curved")`
+ readback `GetArrangementOfPattern`: type должен стать запрошенным, name/offset/
orientation — не измениться. Без ReDrape; визуальный эффект не установлен.
Ошибка после setter может оставить style, без retry/cleanup. Valid synthetic:
`{"pattern_index":0,"expected_name":"panel","style":"Flat"}`. Invalid: style
`flat`, stale name. Live build `aafcfac0323d`: MCP_SEAM_A → Flat, `verified`,
readback type Flat; визуально деталь не изменилась.

## 33. set_pattern_edge_to_avatar_measure

**Source, avatar fit.** `SetPatternEdgeToAvatarMeasure(pattern_index, line_index,
avatar_measure, attach)` — Line Pin одного whole outer edge к мерке аватара;
docs: native сам запускает cloth solver. Required fresh index/unique name,
`line_index` из `get_pattern_lines`, мера из `get_avatar_measurements`. Readback
`GetPatternEdgeToAvatarMeasureAttachment` JSON `{is_attached,line_index}`:
attach → true и запрошенный line, detach → false/-1. Другие edges не меняются;
visual fit отдельно; false/mismatch → STOP, без retry. Live build `b2f3fce822d6`:
attach/detach к user `CircumferenceMeasure_283316` PASS; Default-мерки
(`CIRCUMFERENCE_Bust`) возвращают false. Valid synthetic:
`{"pattern_index":0,"expected_name":"panel","line_index":0,
"avatar_measure":"Bust","attach":true}`.

## 34. simulate

**Source, simulation.** `utility_api.Simulate(steps)` один раз, steps 1..300.
Preflight: ready session, avatar_count≥1, fresh pattern list. Readback: native
bool true и неизменный список имён; result `{verified,steps,pattern_count,
avatar_count,elapsed_ms}`. Это visual-only, не fit acceptance; client timeout не
отменяет native call; settings не меняются, retry нет. Live build `aafcfac0323d`:
`steps=60`, `verified`, `elapsed_ms≈922`, 5 patterns/1 avatar; без закрепления
garment **упал** с торса. Повторный gate с Line Pin: `TEE_FRONT/BACK`, 2 seams,
`simulate(60)` verified/1110ms; garment остался на торсе, но ткань собрана —
toolchain PASS, fit не принят. Valid synthetic: `{"steps":60}`.
Invalid: 0/301/True/"60".

## 35. export_view_image

**Source, artifact.** `ExportStdViewImage(view, output_path, colorway,
width, height, fit_all_objects)` — стандартный 3D-вид (0 Bottom, 1 FrontRight,
2 Front, 3 FrontLeft, 4 Right, 5 Top, 6 Left, 7 Custom, 8 Back), не зависит от
текущей камеры. Tool генерирует путь под `acceptance-output/screenshots/`,
adapter проверяет, что native вернул файл в той же папке (native может добавить
colorway к имени), внешний server читает его и возвращает MCP `Image`.
Width/height 64..2048, файл 1..16MiB, без диалога/произвольного пути/retry.
Result `{verified,view,width,height,file_name,bytes}`. Live build `8e408f3132a0`:
PASS, front 800×600; native пишет файл по запрошенному пути, но возвращает
descriptive colorway-строку, поэтому adapter принимает запрошенный файл в той же
папке. `set_camera_view` + `get_3d_screenshot` остаются live-view вариантом.

## 36. export_snapshot_2d

**Source, artifact.** `ExportThumbnail2D(output_path)` — текущее 2D-окно как
есть, без перекадрирования; PNG/JPEG, файл в `acceptance-output/screenshots/`.
Возвращает MCP `Image`; `{verified,file_name,bytes}`. Не меняет сцену, не
открывает диалог, путь не принимает. Live build `8e408f3132a0`: PASS, 2D-раскладка
5 деталей tee.

## 37. set_camera_view

**Source, camera-only.** `SetCamViewPoint(view)` + optional `SetZoomView()` +
`Refresh3DWindow()`; индексы как у `export_view_image`. `zoom_to_fit` bool.
Result `{verified,view,zoom_to_fit}`; native не даёт camera readback, эффект
visual-only. Ошибка native → `command_error`; без retry. Live build
`8e408f3132a0`: view2 + zoom PASS, front-вид tee.

## 38. reset_cloth_arrangement

**Source, cloth reset.** Один `ResetClothArrangement()`; global: возвращает
cloth shape к состоянию загрузки, отбрасывая текущую simulation. Preflight —
fresh pattern list, после вызова список должен совпасть; visual-only. Result
`{verified,pattern_count}`. Без retry/cleanup. Live pending: на реальном tee не
запускался, так как сбрасывает текущую cloth-форму.

## 39. import_avatar_measurements

**Source, measurement import.** `ImportMeasurement(csv_path)` применяет CSV к
текущему аватару; требуется ровно один avatar, absolute `.csv` ≤16MiB.
Preflight читает count до, после вызова count должен вырасти; result
`{verified,avatar_index,before_count,after_count,added}`. CSV format native,
tool его не валидирует; path не эхоится; false/нет роста →
`scene_change_unverified`, без retry. Live pending: CSV нет; текущая Mara уже
отдаёт 79 мерок (включая user Circumference), поэтому для Line Pin импорт не
нужен.

## 40. get_pattern_body_details

**Source, read-only.** `GetPatternOnBodyDetails()` → JSON upperBody/lowerBody;
каждая запись: patternName/index, arrangementPosition, semanticLabel,
bodyRegion, patternPosition. Bounded strict JSON; до256 patterns. Помогает
выбирать arrangement points и понимать bodice/sleeve; не fit validation. Live
`8e408f3132a0`: tee → sleeve/collar/bodice_front/bodice_back.

## 41. get_pattern_details

**Source, read-only.** `GetPatternPieceGrainDirection/Category/Classification` —
grain degrees, category int, classification text. Required fresh unique
index/name. Read-only; category/classification native, не durable ID. Live
`8e408f3132a0`: tee piece `1` → grain0, category0, classification None.

## 42. set_pattern_grain_direction

**Source, grain.** `SetPatternPieceGrainDirection(index, degrees)` 0..359;
readback grain (mod360) и неизменные area/position/list. Result
`{verified,pattern_index,pattern_name,grain_direction}`. Ошибка после setter
может оставить grain, без retry. Live `ecab8fc77aee`/`8e408f3132a0` на копии
`MCP_GRAIN_TEST`: 90° readback PASS; копия удалена, реальный tee не изменён.

## 43. get_mesh_counts

**Source, read-only.** `GetMeshCountByType(pattern_index)` — native text
face/vertex counts by mesh type, до16 entries. Result
`{pattern_index,pattern_name,meshes:[{type,value}]}`; values не парсятся в
faces/vertices и не доказывают simulation quality. Live `8e408f3132a0`:
tee piece `1` → Face Count 3146, Mesh Type Triangle, Vertex Count 1640.

## 44. set_particle_distance

**Source, simulation mesh.** `SetParticleDistanceOfPattern(index, distance)`
1..1000 mm; readback `GetParticleDistanceOfPattern` и неизменные
area/position/list. Result `{verified,pattern_index,pattern_name,distance}`.
Меньше — точнее и медленнее; simulation не запускается, без retry. Live
`ecab8fc77aee`/`8e408f3132a0` на копии: `scene_change_unverified`; readback не
совпал, эффект неизвестен. Tool остаётся BLOCKED до отдельного разбора.

## 45. lesson

**Source, server-local lesson runner.** Один tool с action
`list|start|state|check|reset`. Урок — это последовательность шагов с
инструкциями и read-only проверкой; сам tool **не меняет сцену** и не вызывает
native mutations. Шаги выполняет клиент существующими tools; `check` только
читает `get_pattern_list`, `get_seamline_pairs`, `get_arrangement`,
`get_avatars` (4 bounded native reads) и двигает прогресс при pass.

Args: `action` — strict enum; `lesson_id` — обязателен только для `start`
(`[a-z0-9][a-z0-9_-]{0,63}`), для остальных actions запрещён. Extras,
неизвестный action, отсутствующий/лишний `lesson_id` → `invalid_parameters` до
любого чтения. State хранится в памяти MCP service и теряется при restart; файлов
и IPC нет.

Result: `{ok,status:"not_started"|"in_progress"|"completed",lesson:{id,title,
summary}|null,progress:{completed,total},current_step:{index,id,title,
instructions,tools}|null,last_check}`; `check` добавляет `{passed,evidence,
message}`. `start` перезапускает урок; `reset` очищает прогресс. Pass двигает
ровно на один шаг, fail оставляет шаг и не делает cleanup/retry. Ошибки:
`lesson_not_found`, `lesson_not_started`, `lesson_check_unavailable` (одно из
четырёх чтений не удалось), `invalid_parameters`.

Valid synthetic: `{"action":"list"}`; `{"action":"start","lesson_id":
"two_panel_tube"}`; `{"action":"check"}`. Invalid: `{"action":"start"}`;
`{"action":"state","lesson_id":"two_panel_tube"}`; `{"action":"run"}`.
Composition: `start` → клиент выполняет scene-шаги → `check` после каждого
шага → `state` для прогресса. Anti-selection: это не composite scene tool и не
замена `add_seamline_pair`/`set_arrangement`; при `lesson_check_unavailable`
STOP, не повторять и не запускать scene mutations «для проверки». Каталог и
контракт шагов: `docs/CLO_MCP_LESSONS.md`. Local tests only; real CLO gate
pending.

## 46. import_dxf

**Source, DXF append.** Один `import_api.ImportDXF(path, option)` с
`ApiTypes.ImportDxfOption`: adapter выставляет `m_bAppend=true`, а при наличии
полей — `m_bImportNotchTo=true` и `m_eNotchImportPlacement=2`. Это импорт
**новых деталей в текущую сцену**, не замена проекта и не AAMA-парсер.

Args строго `{"file_path"}`: absolute existing `.dxf` 1..64MiB, 1..260 chars,
без control/surrogates. Относительный путь, другой extension, extra keys,
bool/не-строка → `invalid_parameters` до native. Options не принимаются:
никаких arbitrary `ImportDxfOption` полей.

Result `{imported:true,pattern_count_before,pattern_count_after,imported_count,
imported_names,executor_ms}`; `imported_count = after-before >0`, names — новый
хвост списка. Проверка native true и роста списка; path не эхоится. False/no
growth/mismatch → `invalid_native_result`/`scene_change_unverified`; после
входа в native ошибка может означать уже выполненный импорт: STOP, без retry,
rollback или удаления «лишних» деталей.

Valid synthetic: `{"file_path":"C:\\project\\acceptance-output\\trousers_40.dxf"}`.
Invalid: relative path, `.txt`, extra `options`. Composition: импорт → fresh
`get_pattern_list` → `get_pattern_lines`/geometry → seams/arrangement. Anti:
не использовать для `.avt` (есть `import_avatar`), для замены проекта или для
AAMA-специфичной проверки; native notch/grain semantics не заявлены. Evidence:
`tests/test_import_dxf_api.py`; real CLO gate pending.

## 47. export_pattern_json

**Source, read-only artifact.** Один `pattern_api.ExportPatternJSON(path)` в
server-generated путь `acceptance-output/pattern_json/current.json`, native true
и файл 1..64MiB; result `{verified:true,file_name,bytes,top_level_keys}`.
Args `{}`; произвольный путь, импорт, scene mutation и retry не входят. Это
единственный публичный способ увидеть native `SeamLinePairGroupList`/`NotchList`
и построить line-level seam map; schema не заявлена до реального probe.
`LengthParam` в export — доля **периметра детали** от начала обхода, не
line-relative: `export = (prefix_offset + ratio * line_length) / perimeter`.
Один seam group может покрывать пробег нескольких `LineList`-линий.

Valid: `{}`. Invalid: `{"path":"..."}` или `{"file_path":"..."}` — extra keys.
Composition: export → чтение ключей → решение о JSON-конвертере или partial
seams. Anti: не использовать как замену `get_pattern_lines`/`get_seamline_pairs`
для простых reads; не публиковать содержимое файла как доказательство fit.
Evidence: `tests/test_pattern_json_api.py`; real schema gate pending.

## 48. import_pattern_json

**Source, destructive JSON import.** Один `pattern_api.ImportPatternJSON(path)`;
по контракту донора **заменяет сцену**, не append. Args `{file_path}`: absolute
existing `.json` 1..64MiB. Preflight проверяет файл; затем native call и
readback `get_pattern_list` + `GetSeamlinePairGroupCount`. Result
`{imported:true,pattern_count_before,pattern_count_after,patterns_after,
seam_count_after,executor_ms}`. False/исключение после native → error; scene мог
измениться. Нет backup, merge, retry, rollback или cleanup.

Valid synthetic: `{"file_path":"C:\\project\\acceptance-output\\pattern_json\\current.json"}`.
Invalid: `.dxf`, relative path, extra keys. Использовать только на пустой или
явно расходной сцене; перед импортом сделать `export_pattern_json` текущего
проекта. Live 2026-11-11: импорт 5 деталей сохранил имена, но
`seam_count_after=0` — JSON в этой сборке переносит детали, не швы. Anti: не
запускать поверх сшитого проекта; не считать `seam_count_after`
доказательством корректности line pairs. Evidence:
`tests/test_pattern_json_api.py`; real CLO gate: 5-детальный импорт.

## 49. add_seamline_pair_partial

**Source, partial seam.** 10-аргументный
`pattern_api.AddSeamlinePairGroupPartial`: две whole outer lines, у каждой
`startRatio`/`endRatio` — **line-relative** доли длины этой линии,
`0 <= start < end <= 1`, directions strict bool. Descending input native
отклоняет (`invalid_native_result`) даже если export пары с `direction=false`
выглядит descending: export хранит старт/end в обратном порядке, но
физический участок тот же. Ratios применяются буквально, snapping по насечкам
не выполняется; native success — `int 0`, не truthy. Адаптер требует свежие
indices/уникальные имена, проверяет line counts, `seam_count +1`, неизменные
длины линий/geometry/list. Result `{verified:true,seam_count}`. Non-zero/
exception → error, без retry/cleanup. Child overloads, topstitch, merge/delete,
seam allowance и качество шва не входят.

`export_pattern_json` пишет `LengthParam` как долю **периметра детали**:
`export = (prefix_offset(line) + ratio * line_length) / perimeter`, обратно
`ratio = (export * perimeter - prefix_offset(line)) / line_length`. Для
`line0` offset=0. Reference-группа может покрывать пробег нескольких линий
(один `LineID` + perimeter-доли); одним partial-вызовом она не
воспроизводится — декомпозировать на пары отдельных линий. Не передавать
reference `LengthParam` напрямую: это даёт сдвиг, наложения и CLO warning
«abnormal/overlapped seamlines».

Одинаковые `pattern_a_index == pattern_b_index` **допускаются**: darts,
вытачки и waistband self-seam делаются partial-вызовом с ratios 0..1.
`add_seamline_pair` такие пары отклоняет.

Valid synthetic: `{"pattern_a_index":0,"expected_name_a":"panel","line_a_index":0,
"start_ratio_a":0,"end_ratio_a":0.5,"pattern_b_index":1,"expected_name_b":"back",
"line_b_index":0,"start_ratio_b":0.5,"end_ratio_b":1,"direction_a":true,
"direction_b":false}`. Invalid: `start_ratio_a >= end_ratio_a` (включая
descending), ratio 1.1, bool-as-ratio, stale target. Composition: fresh lines →
проверить физические интервалы → partial seam → readback lines/geometry →
следующий участок; для multi-line кромки несколько вызовов.
Anti: whole-line шов — `add_seamline_pair`; удаление/merge/посадка — не этот
tool. Evidence: `tests/test_seam_api.py`; live calibration 2026-11-11,
`CLO_SEAMLINING_CHECK.md`.

## 50. import_avatar_size

**Source, avatar size.** Absolute `.avs` 1..16MiB через
`import_api.ImportFile`; требуется ≥1 avatar. Readback
`utility_api.GetAvatarMeasurements(0)` до/после; result
`{verified:true,measurement_count_before,measurement_count_after,added}`.
`added=0` — валидный observation: `.avs` меняет размер, но не обязан создавать
measurement set; не выдавать его за успешное появление мерок. False/exception
после native → error, без retry/cleanup. Native UI может показать подтверждение;
tool не ждёт ручного подтверждения. Valid:
`{"file_path":"C:\\...\\Olga.avs"}`. Invalid: `.avt`, relative path, extra keys.
Anti: для `.avt` — `import_avatar`, для CSV — `import_avatar_measurements`.

## Ошибки и безопасные действия

- invalid_parameters: проверить schema/bounds/extras, не пробовать наугад.
- api_unavailable: описать binding, сверить docs/build; не native fallback.
- stale_pattern: остановить старый план, fresh list/geometry; имя не ID.
- stale_fabric: до setter сменилось имя/index/unique fabric либо current mapping;
  остановить план, отдельно fresh inventories/mapping, не automatic retry.
- scene_change_unverified: эффект мог быть; stop mutations, separate read-only
  сверка. Иногда возникает и при invalid preflight snapshot — код консервативен.
- command_error: native exception sanitised; diagnostic square мог изменить
  сцену. Не считать его гарантированным no-op.
- queue_full/queue_timeout/executor_unavailable/waiter_limit: нет разрешения
  blind retry; проверить status. Отсутствие выполнения утверждать только при
  достоверном знании stage, не по клиентскому таймауту.
- outcome_unknown/disconnect/client timeout: прекратить сценарий; dispatched
  work может продолжаться. Нет опубликованного resume/cancel/job-lookup tool.

Status/info могут оставаться доступны при busy CLO. Любые native getters в
reconciliation ждут ту же FIFO; ограничивать запросы и не объявлять их способом
прервать заблокированный API. Историческая real acceptance:
`PATTERN_API_CHECK.md`, `P3_MCP_CHECK.md`; не все возможные сцены/геометрии.
