# Рецепты совместного использования CLO MCP tools

2026-11-09. Это orchestration recipes, **не новые server tools** и не новые
запущенные испытания. Exact contracts: `CLO_MCP_TOOLS.md`. Исторически принятые
pattern сценарии описаны в `PATTERN_API_CHECK.md`; здесь их не повторяем.
Примеры — synthetic, actual targets брать из fresh reads.

## B06: read-only outline, source/live19 / real BLOCKED

После user restart discovery19 PASS,first own rectangle outline invalid_native_result.
Отдельный ручной one-shot: native [] для own existing unique target index5;
причина пустоты неизвестна,no retry/move/delete/existing reads. Own fixture index5 remains,
original5geometry/mappings preserved by separate readonly reconciliation.
Diagnostic выполнен пользователем (`CLO_OUTLINE_CHECK.md`),не acceptance/schema fallback.
Рецепт ниже не возобновлять до отдельного плана,устраняющего blocker.

Только после actual discovery/capability19 и fresh CLO: ready/session → fresh
list → `get_pattern_outline({pattern_index,expected_name})` → schema/index/name/
frame check. Endpoints в мм bbox TOP-LEFT/Ydown,не global2D/curve controls/lineIndex.
Cross-domain: fresh list → outline → `get_pattern_fabric` с тем же fresh unique
target → проверить оба observations; не выводить material/3D/sewing validation.
На stale/changed/invalid/unknown stop,не automatic retry/fallback. Старый profile18
не поддерживает outline; не generic native call. Real gate `CLO_OUTLINE_CHECK.md`,
local fake traces в `tests/test_tool_workflow_evals.py`.

## Линии: read-only рецепт (tool20)

`get_pattern_lines` опубликован: fresh list → `get_pattern_lines({pattern_index,
expected_name})` → проверить line_count/уникальность line_index/finite mm; при
необходимости отдельно `get_pattern_geometry` с тем же fresh target. Не вызывать
lines вместо пустого outline, не подставлять 3-аргументную `GetLineLength`, не
выводить curve controls/швы/closure и не заявлять frame после move/rotate.
`CLO_LINE_API_CONTRACT_REVIEW.md`.

## Общий порядок

Намерение/scope → реальный profile/session → fresh reads → preflight → одна
mutation → result check → independent readback → следующий шаг. Один outstanding
mutation. На error/unknown/mismatch/session change остановить mutations.
Никаких speculative FIFO batches, retry или finally scene cleanup. Read-only
reconciliation — отдельное действие, не resume старого run. Client session check
не atomic; mutations сейчас не принимают server-side expected_session guard.

Серверный success теперь включает bounded (2 с) ожидание READY своего завершённого
job, не ожидание global idle. Чужую работу нельзя считать завершённой по этому
ответу. `executor_release_timeout/unavailable` останавливают зависимые действия;
нет retry или автоматического resume. До обновления внешнего MCP действует старая
поведенческая версия; новый worker загружается через Stop → Start.

## W1. Осмотреть сцену и проверить доступность

**Цель:** отличить HTTP availability, работающий UI executor и actual data.
**Tools:** info/status, optional ping, count/list/geometry. Только чтение.

1. `get_session_info({})`: сохранить session_id, проверить ready/profile/error.
2. При not-ready/busy/quarantine — один `transport_status({})`. Не посылать
   mutation или ping flood для «разблокировки».
3. Optional `ping({})` проверяет FIFO/UI roundtrip, но не вызывает native scene
   getter. Не обязателен перед каждым чтением и не обгоняет занятый executor.
4. Если нужен только count — `get_pattern_count({})`; если нужны targets —
   сразу `get_pattern_list({})`, без лишнего предварительного count.
5. Для выбранных элементов bounded serial geometry reads по fresh indices;
   сверить returned names. При UI editing это не atomic snapshot.

**Результат:** count/names/position/area/bbox, не полный outline/свойства ткани.
List limit256 не снимается диагностическим count. Mismatch → остановить обход.
**Anti-example:** HTTP отвечает → «CLO наверняка выполняет native API».

### W1b. Отдельные inventories тканей и аватаров

Source и live profile18 подтверждены после fresh restart. Новые recipes list →
get_pattern_fabric(expected name) → guard → assign_pattern_fabric(expected
pattern/fabric names/current index) → independent read, только если18 реально
published/capabilities ready. Нет native fallback при16. Full B05 runbook:
`CLO_FABRIC_ASSIGNMENT_CHECK.md`: direct API/readback PASS на своей детали,
UI подтверждён пользователем,temporary appearance не оценена. B05C: source
assign→copy→independent fabric read→rename/move→read→copy assign→read all→
delete lower source→fresh list/new index→read→assign new index→planned own delete
real PASS;fixture-specific inheritance не гарантия произвольной copy semantics.
Read-only runner `pattern-fabric-inspection` real PASS:
2passes5mappings,final lists/status,32RPC/0mutations; local tests отдельно.

Inventory-only recipe был введён в profile16. Info/guard → get_pattern_list → guard →
get_fabric_list → guard → get_avatars. Это отдельные counts/names snapshots,
не pattern↔fabric assignment, не качество fit/pose/geometry. `get_fabric_list`
возвращает Fabric проекта с Object Browser indices, без colorway API/фильтра.
Limits256fabrics/64avatars; extras/pagination invalid. При changed/limit/error STOP,
не fallback/import/switch colorway. Прежний colorway prototype снят после
count0 при3видимых тканях. В свежем CLO Object Browser дважды вернул4одинаковых
count/names, status idle/error=null; пользователь подтвердил GUI/UI — limited gate
ACCEPTED. Дополнительные5read-only cycles+final inventories/geometry5 PASS.
Аватар count1/name реально прочитан. Полные cards/next gate:
`CLO_INVENTORY_CHECK.md`; внешний bounded runner имеет scenario
`fabric-avatar-inventory`, но не диагностирует совпадение с GUI автоматически.

## W2. Исследовать API перед проектированием tool

**Tools:** list_clo_api → describe_clo_api → official docs вне CLO.

1. Получить bounded callable names пяти фиксированных modules.
2. Выбрать qualified symbols, не более16 за describe call. Например:
   `{"module":"fabric_api","functions":["GetFabricCount","GetFabricName"]}`.
3. Сопоставить docstring с official version/signature, units, enum/options;
   заполнить coverage/tool card, явно записать unresolved типы и поведение.

**Результат:** evidence для спецификации, не native execution или новый tool.
GUI/REST/ApiTypes не входят в текущий introspection whitelist; не обходить это
generic import/exec. Doc может быть обрезан или содержать только arg0.
**Anti-example:** увидев ImportAVAC, вызвать отсутствующий MCP import_avatar.

## W3. Создать деталь, копию и сдвинуть копию

**Scope:** явно запрошенная ограниченная2D задача. Не новый test run.
**Preconditions:** pattern profile, valid polygon, свободные unique names,
room для2новых деталей (исходно≤254), user-approved scene scope.

1. Info/status → fresh list. Не считать prefix ownership существующей детали.
2. `create_pattern({points:<valid_pairs>,name:<source_name>})`.
3. Проверить ok/verified/schema/count, сохранить returned index/name.
4. Independent `get_pattern_geometry({pattern_index:<returned_index>})`:
   сверить имя/площадь. Exact vertices этим getter не доказываются.
5. Session/status + fresh target guard →
   `copy_pattern_with_offset({pattern_index:<source_index>,
   expected_name:<source_name>,name:<copy_name>,dx:250,dy:30})`.
6. Взять **новый index из copy result**, не guessed last/source index. Проверить
   copy ok/verified/schema и сделать independent geometry read копии (name,
   area, position). Только после совпадения и свежей проверки session/target:
   `move_pattern_relative({pattern_index:<copy_index>,expected_name:<copy_name>,
   dx:-15,dy:20})` → verify → independent geometry. При неизменном source
   суммарное относительное2D смещение копии[235,50].
7. Optional rename обновляет expected_name для следующих вызовов.
8. Если требуется planned cleanup своих тестовых объектов — только explicit
   успешные delete steps с fresh unique identity. После каждого delete fresh
   list, прежде чем искать следующий target. Не cleanup в finally.

**Не гарантирует:** symmetry, sewing preservation,3D arrangement, готовую одежду.
**Failure:** STOP mutations, отдельно W4; no copy-again/undo/delete остатка.
**Anti-example:** gather(copy,move,delete) с заранее известными indices.

## W4. Сверить сцену после неизвестного исхода

**Цель:** current observations без повторного изменения.

1. Зафиксировать command/error/known pre-state; прекратить dependent mutations.
2. Один status/info snapshot: same session? active/quarantined/error?
   Timeout клиента не означает native stop; не flood getters при busy.
3. Когда executor доступен, bounded fresh list/geometry: сравнить имена/count/
   площадь/позиции. Похожая сцена не доказывает историю исполнения. Duplicate
   names/changed scene могут не позволить надёжную атрибуцию.
4. Сообщить observations и uncertainty. Новая mutation/cleanup — отдельный
   осознанный план по актуальному состоянию, не automatic resume.

**Block:** при quarantine нет обещания обхода. Restart/stop согласовать,
не kill by port/name. Текущий HTTP API не публикует job lookup/replay/cancel;
active_id не даёт права выдумать такой tool.
**Anti-example:** timeout create → повтор create с тем же именем.

## W5. Будущий cross-domain рецепт — сейчас BLOCKED

Панели → ткань/цвет → выбранный аватар → расстановка → швы → короткая симуляция
→ export. Сейчас опубликован только pattern фрагмент. Для каждого звена нужны
domain tools/contracts, assets, scope и readback/visual criteria. Sewing ждёт
проверенную topology/index namespace; simulation — корректные preconditions и
честную timeout semantics; export — выбранную папку/overwrite policy.

Разрезать на отдельные acceptance plans: fabrics-colorways, avatar visibility/
import, geometry-sewing, arrangement-short-sim, export. Не мегатул «сделать
одежду» без partial effects/failure контракта. Успешный count не доказывает
условия для следующей опасной операции.

## Будущие доменные skills

Кандидаты после появления tools: fabric-colorway, avatar-pose, geometry-sewing,
arrangement-simulation, project-export, grading-nesting-UV, render-animation.
Это backlog, не installed skills. Шаблоны:
`../.opencode/skills/clo-tool-workflows/templates/domain-skill.md` и
`../.opencode/skills/clo-tool-workflows/templates/workflow-card.md`.
Каждый skill: trigger, выбор tools, bounded recipe, anti-example, stop/
reconciliation и evidence. Один smoke не означает acceptance всего домена.
