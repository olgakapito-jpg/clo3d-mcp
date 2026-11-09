# B05a/B05b — связь крой ↔ Fabric Object Browser

Target **CLO2026.1.336**. Пользователь разрешил последовательные пакеты без
промежуточных остановок, включая редактирование проекта, до конкретного блока.
Существующий крой/назначения сохраняются; тестовые mutations только на отдельной
созданной детали. Никаких повторов принятых load10/load1000/P0–P3, colorway
management, hidden cleanup, arbitrary exec или transport изменений.

## Реализация и граница evidence

Расширенный profile18 = принятые16 + `get_pattern_fabric`/`assign_pattern_fabric`.
После пользовательского полного restart CLO live discovery подтвердил18tools,
16executor capabilities, ready/idle/error=null. Real API/readback gate ниже
**PASS в ограниченном fixture**; пользователь затем подтвердил нормальную работу
интерфейса. Внешний вид временной детали отдельно не зафиксирован.
Local tests отдельно от real acceptance.
Новый stdlib adapter `fabric_assignment_api.py` вызывается только существующим
verified UI executor, интегрирован в PatternAPI, protocol/FIFO/executor/HTTP
через общий strict contract. Официальный FastMCP/зависимости не меняются.

Source traceability, `docs/api/official/`:

- `fabric_api.GetFabricIndexForPattern#9629b432c54ed333`, `(patternIndex:int)->int`:
  return docs явно Object Browser fabric index. Только single-index overload.
- `fabric_api.AssignFabricToPattern#f520a3b0171cae75`, `(fabricIndex,patternIndex,
  assignOption)->bool`. Source Object Browser; option **1 фиксирован**: применение
  только в текущем контексте изделия, другие варианты не изменяются согласно docs.
  Option2/3, linking и explicit colorway selection не доступны. Нативная семантика
  текущего контекста не превращается в пользовательский colorway workflow.
- Supporting: GetFabricCount(_bCurrentColorway=False)/GetFabricName(index) из
  принятого Object Browser inventory и pattern count/name/position/area/bbox.
- GetPatternPieceFabricIndex/SetPatternPieceFabricIndex presence тоже подтверждены
  metadata, но НЕ используются/fallback: official не раскрывает их namespace
  столь же явно. Native setter не вызывается ради discovery.

Live describe подтвердил getter1/2args и assignment3/4args, return int/bool.
Option1 реально проверен на тестовых деталях; полные material/cross-context
side effects и внешний вид временной детали не установлены. UI подтверждён.

## 17. get_pattern_fabric

Когда: «Какая ткань назначена этой детали?» Не выбирать для изменения ткани,
материалов/позы/fit. Required args: `{pattern_index,expected_name}` — strict int
0–255 и exact unique pattern name1–128chars, ord≥32 без surrogates.
Read fresh list перед выбором. Name/index — stale guards, не durable IDs.
Result `{ok:true,pattern_index,pattern_name,fabric_index,fabric_name}`.
fabric_index0–255 в Object Browser, fabric_name0–256chars ord≥32 без surrogates;
empty/duplicates сохраняются для чтения, не unique fabric identity.

Preflight callable names до первого native read. Pattern/fabric lists читаются
до и после, mapping getter дважды совпадает. Max256patterns/256fabrics,
максимум1546 native reads. Не atomic snapshot, ABA/name collisions не исключены.
Нет setter/files/import. Не распознаём undocumented -1/unassigned: invalid result.
Valid synthetic `{pattern_index:0,expected_name:"front"}`.
Invalid/no-call `{pattern_index:true,expected_name:"front"}`, extra colorway/face/
limit keys или missing expected_name — invalid_parameters до enqueue.

## 18. assign_pattern_fabric

Когда: назначить одну имеющуюся Fabric одной детали, не import/material edit.
Required args `{pattern_index,expected_name,fabric_index,expected_fabric_name,
expected_current_fabric_index}`. Indices strict0–255; pattern name как выше,
fabric name0–256chars exact и **unique** в текущем списке (включая пустое имя).
Expected current index из fresh get_pattern_fabric, не guessed0.
Result `{ok:true,verified:true,pattern_index,pattern_name,fabric_index,fabric_name,
previous_fabric_index,executor_ms}`; executor_ms≥0, includes preflight/readback,
не чистое API время. No-op same index разрешён, но это mutation tool без retries.

До setter: snapshots lists, все текущие назначения, expected guards и геометрия
target. Перепроверка snapshots и всех mappings. Один native setter(fabric,pattern,1),
только exact True считается завершённым. После:2прохода mappings всех деталей,
оба snapshots unchanged, изменилась только target mapping; target name/position/
area(~0.05мм²/relative1e-5)/bbox unchanged. Max4123 native reads для256/256;
один synchronous UI callback: bounded calls НЕ hard time bound и могут блокировать
UI. Длительность на max fixture real не проверена. Не доказывает отсутствие всех
материальных side effects/полную topology/cross-colorway linking invariants.

Valid synthetic `{pattern_index:0,expected_name:"front",fabric_index:1,
expected_fabric_name:"jersey",expected_current_fabric_index:0}`; эти числа не live
targets. Invalid: extra assign_option/colorway/face или bool indices; no-call.
Anti-selection: «Добавь ткань из файла» — tool не import; такой tool ещё отсутствует.

## Errors и safe next action

- invalid_parameters: strict raw schema до enqueue; не угадывать overload.
- api_unavailable: отсутствует callable/preflight readback, scene changes0.
- stale_pattern: index/name/unique mismatch; stale_fabric: target fabric
  index/name/unique или expected-current mismatch; оба до setter.
- inventory_limit/invalid_native_result/inventory_changed: STOP, не partial list;
  сохраняется политика inventory adapter, no native retries/coercion/sentinels.
- command_error: sanitized pre-entry native exception, без paths/traceback.
- scene_change_unverified: любая ошибка/False/nonbool/несоответствие после входа
  в setter. **Мог быть эффект**, не rollback/retry/cleanup. Queue unknown/timeout
  и release errors также STOP. Client timeout не cancellation native операции.

Composition: info/session/idle → pattern list → fabric list → get_pattern_fabric
по fresh target → guard → assign_pattern_fabric с обоими expected names/current
index → independent get_pattern_fabric → guards/lists и сравнение. Один outstanding
mutation, не pre-enqueue зависимых изменений. Session check клиента не atomic.

## Local verification и следующий real gate

Локальные результаты 2026-11-09: focused5files **312passed**; full suite
`uv run --frozen --with pytest pytest -q -rs` — **824passed,1skipped**,46.96с.
Skip: real symlink unavailable, synthetic reparse tests сохранены. Offline
selection34cases/18tools,self-test2valid/6invalid PASS (не LLM benchmark).
Mappings/coverage rebuild+check и git diff-check PASS. Full source audit202files
blocked только `opencode.json.openchamber.backup: asset/binary extension rejected`;
backup/config не менялись. Assignment dry-run имеет0native/network calls,
missing_tools=[], но BLOCKED domain_contract_and_runner_not_integrated: отдельный
client recipe не реализован; direct serial runbook ниже готов для будущего gate.
Это результаты локальной подготовки до restart. Последующий real run — ниже.

`tests/test_fabric_assignment_api.py`: strict args/result, all-read+setter fault
injection at every native step, no retry/post-effect cleanup, stale/duplicates,
changed mappings, unexpected other-target/material/name/geometry changes, missing
readback preflight, queue/executor/cache/official SDK metadata. Synthetic selection
cases расширяют offline eval; real LLM selection этим не доказан.

Блок fresh CLO restart **снят** пользовательским restart и `_start`. Stop→Start
только worker не reload embedded sys.modules. Агент не hot-reload callbacks и
не перезапускает приложение. Выполненный direct serial runbook:
чтение существующих5assignments → стабильный повтор, без mutation → одна
uniquely named test piece вне
пользовательского кроя → independent mapping read → назначение другой имеющейся
ткани → independent readback/all-mapping preservation → при успехе ещё одна
ткань → fresh guards → плановое удаление только своей детали. Не cleanup on error.
Fixture/точные coordinates из fresh geometry; не импортировать assets. Visual
assignment/UI confirmation отдельно, пакет не объявлять полностью принятым без неё.
Остановить через `_stop.py` при доступном UI; при ошибке/unknown/dialog/hang
ничего не повторять/не kill по имени/порту. Full source audit отдельно blocked
посторонним backup, не удалять его и не ослаблять guard.

## Real CLO2026.1.336, 2026-11-09 — limited API/readback PASS, UI подтверждён

Build сообщён пользователем, не извлечён отдельным native version getter.
Одна и та же CLO session на status guards, очередь ready/idle/error=null.
Native calls последовательно; ни одного retry, fallback, rollback или ошибки.
Direct run:55scene commands, из них4mutations (create,2assign,delete),51reads.
Не повторяли P0–P3/load gates. Это bounded functional check, не latency benchmark.

Исходные pattern names/index→fabric index:0/`2`→2,1/`3`→3,2/`5`→0,
3/`6`→0,4/`1`→1. Два полных mapping passes совпали; fresh fabric list:
0=`FABRIC 1`,1=`V2_Cut_Sew_Knit_JacquardKnit_1`,
2=`V2_Cut_Sew_Knit_ITY_MatteJersey_2`,3=`V2_Cut_Sew_Knit_Waffle_3`.

Создана только `MCP_B05_20261109_5c083e25`, returned index5, прямоугольник
[[2000,1000],[2120,1000],[2120,1080],[2000,1080]]мм вне bounding extents
исходного кроя. Independent geometry: center[2060,1040],area9600.0009765625мм²,
box Height80/Width120. Independent initial mapping0, не предположение о default.
Assignment0→1 exact success/verified,executor31мс; independent getter→1.
Assignment1→3 exact success/verified,executor16мс; independent getter→3.
Executor time из результата, не client latency/чистое setter time.

После каждого назначения независимо прочитаны все5исходных mappings; unchanged.
После второго назначения geometry всех6деталей совпала с baseline, включая
точные position/area/Height/Width (full outline/3D/sewing не прочитаны).
Fresh list+same-session idle guard → плановый delete только собственной index5
с exact unique expected name,verified/count5. Это не cleanup после ошибки.
После delete fresh list/order5,все5mappings и geometry совпадают с baseline;
fabric list4 unchanged; avatar count1/name `Mara_09_eye_Joint` прочитан.
Геометрия/поза аватара не проверялись, исходного pre-run avatar snapshot здесь нет.
Final status ready=true,active=null,waiting=waiters=0,error=null.

### Следующий клиентский пакет — read-only runner

`scripts/verify_domains.py` теперь имеет `pattern-fabric-inspection`: fresh
pattern/fabric lists,2serial mapping passes с identity/name/index сверкой,
final lists/status. Нет setters/creation/deletion,0mutation submissions.
Object bound1–16(default4); duplicate pattern names STOP до mapping reads;
empty scene допустима, но nonempty_mapping_checked=false. Индексы transient,
проверки не atomic. Budget12+4*max_objects RPC включая initialize.

Реально выполнено:
`uv run --frozen python scripts/verify_domains.py run --scenario pattern-fabric-inspection --max-objects 5 --max-steps 32 --total-seconds 60`
→ verified/bounded_fabric_mapping_observations_only,32RPC,14scene read commands,
5objects/4fabrics/2passes,0mutations,session guard PASS. Всего с direct run69scene
commands/4mutations. JSON summary не содержит private names/paths/session tokens.
Failure: первый error/schema/identity/mapping/list/session mismatch → STOP без
retry/cleanup. Ctrl+C останавливает только клиент; `_stop.py` запускает пользователь.
`fabric-assignment-future` остаётся BLOCKED: отдельный mutating runner не реализован;
это не отменяет успешный direct serial real run.

После этого прогона пользователь сообщил: «в интерфейсе все хорошо» и разрешил
дальнейшее тестирование. Это закрывает UI gate ограниченного readback-пакета,
но не является отдельным visual appearance verdict временной детали: она уже
планово удалена, не восстанавливать для повтора автоматически. Не объявлять весь
fabric domain fully accepted: imports/material editing/cross-context semantics
не покрыты.

### Проверки после клиентского пакета

Focused runner/assignment/workflow:231passed. Full suite
`uv run --frozen --with pytest pytest -q -rs`:839passed,1skipped,52.42с;
skip только real symlink creation unavailable, fake reparse checks сохранены.
Mappings/coverage rebuild+check,eval34cases/18tools+self-test,diff-check PASS.
Новых server/native изменений в этом клиентском пакете нет, restart не нужен.
Общий source audit не повторялся: ранее blocked посторонним backup, который
не менялся; это отдельный незакрытый пункт, не PASS всего source audit.

## B05C — composition/copy/index shift, следующий real пакет

После подтверждения UI выполнен новый functional scenario, не повтор load:
54scene commands,9mutations,до2собственных деталей,serial calls без ошибок,
unknown/retry/rollback/cleanup-on-error. Исходный list5/fabric4 и geometry/mappings
прочитаны заново. До новых mutations площадь некоторых исходных деталей слегка
отличалась от прошлого прогона (максимум0.6875мм² на площади~359871мм², меньше
relative1e-5 tolerance). Причина не установлена; это не приписывается новому
сценарию. Внутри нового прогона final geometry **точно** совпала со fresh baseline.

1. Создана own `MCP_B05C_source_5c083e25`,index5,points
   [[2000,1250],[2120,1250],[2120,1330],[2000,1330]],center[2060,1290],
   area9600.0009765625мм²,Height80/Width120. Independent mapping0.
2. Assign source0→2,verified/executor32мс,independent read2.
3. Copy source dx200/dy0 → returned index6 `MCP_B05C_copy_5c083e25`,center
   [2260,1290],area9600мм². Independent read: ткань2 унаследована в этом fixture;
   это НЕ новая общая гарантия copy tool о material/3D/sewing semantics.
4. Rename copy→`MCP_B05C_renamed_5c083e25`,mapping2 unchanged. Move dx25/dy-30 →
   center[2285,1260],area9600,box unchanged,independent geometry+mapping PASS.
5. Assign copy2→3,verified/executor32мс. Independent mappings всех7: исходные
   [2,3,0,0,1] preserved,source2/copy3 — независимые назначения.
6. Fresh list/idle guard → planned delete own source index5. Fresh list: copy
   стала index5 (была6). Independent geometry/name/mapping3 preserved. Старый6
   не использовался и не вызывался как intentional live error.
7. По fresh index5 назначение copy3→0,verified/executor16мс,independent read0.
   Fresh list/idle guard → planned delete own copy5; final list5 исходных names/
   order,все5mappings и geometry/box точно как fresh baseline,fabric list4 unchanged.
   Final status same-session,ready/idle,error=null. Нет claims о полном outline/3D.

Offline composition tests добавлены в `tests/test_fabric_assignment_api.py`:
synthetic copy/material model,rename/move/independent assignments/delete/index
shift; failure injection before/after effect на каждом шаге рецепта останавливает
все дальнейшие calls,без cleanup/retry. Отдельно stale index после lower delete
отклоняется getter/setter без assignment. Fake copy модель не real evidence сама
по себе. Focused assignment42tests PASS.

Итог локальной проверки B05C: full843passed/1skipped49.82с (symlink unavailable),
после чего synthetic recipe дополнен успешным assignment по shifted index и
повторно проверен полной suite. Итог последнего запуска сообщён в ответе;
перегенерация source/coverage выполняется после каждого изменения input evidence.

### Следующий настоящий blocker — отсутствуют topology MCP tools

Bounded describe после B05C подтвердил bindings:
GetPatternOutlinePoints(int)->List[List[float]],GetPatternLineInfo(int)->str,
GetLineLength(2/3int)->float,GetPatternBaselinePoints/GetPatternInternalShapePoints
(2int)->List[List[float]]. Это metadata, native getters НЕ выполнялись.
Official reviewed candidates: GetPatternOutlinePoints#8b6d1cfeb17b2fc2 — boundary
endpoints,без curve controls,мм от bbox TOP-LEFT,Y down,real-pattern-list index;
GetPatternLineInfo#45ddc71808d7eb67 — JSON schema с lineIndex в порядке
GetLineLength/DeleteLine;GetLineLength#1ae661ba75ad2f5a — outer line overload.
Real response/layout/coordinate/index correspondence ещё не проверены.

Live18 не содержит явных outline/segment/line tools. Следующая meaningful real
проверка topology/sewing BLOCKED_IMPLEMENTATION: нужен отдельный read-only tool
с bounded schema/guards/official mapping/local fault+workflow tests и свежий
CLO процесс для embedded изменений. Не generic exec/legacy/fallback и не
повтор принятых нагрузочных gates. Пользователь сам управляет CLO restart.
