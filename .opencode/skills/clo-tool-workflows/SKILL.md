---
name: clo-tool-workflows
description: Safely choose and combine CLO MCP tools for scene inspection, pattern operations, API discovery and post-error reconciliation. Use before multi-tool CLO work or drafting domain workflow skills; distinguishes currently available tools from planned API.
---

# CLO: совместное использование инструментов

Прочитать корневой `AGENTS.md`. Корень проекта относительно skill — `../../..`.
Открыть `../../../docs/CLO_MCP_TOOLS.md` для exact текущих contracts и
`../../../docs/CLO_MCP_WORKFLOWS.md` для рецептов. Templates ниже — заготовки,
не дополнительные включённые навыки/инструменты. Для проектирования нового
tool загрузить `clo-mcp-tool-design`.

## До вызовов

1. Установить намерение, разрешённый scope и ожидаемый эффект. Не выводить
   разрешение на files/network/global settings из расходности сцены.
2. Сверить реально опубликованные tools и `get_session_info` capabilities.
   Native API из list_clo_api ещё не MCP tool. Не вызывать planned/legacy names.
3. Проверить ready/session, затем прочитать targets. Name/index — stale guard,
   не persistent ID. После удаления/замены получить новый список.
4. Bounded план: reads → preflight → одна mutation → readback → следующий шаг.
   Serial await; не ставить зависимые mutations заранее в FIFO, не gather.
   Status/session check не atomic: текущие mutations не имеют server-side
   expected-session аргумента. При подозрении на restart остановить сценарий.

## Во время и после

- Проверять isError/error и command-specific schema, а не только отсутствие
  exception. `verified=true` подтверждает только описанные invariants adapter.
- При stale target остановить старый план, заново прочитать идентичности;
  не повторять mutation автоматически даже после command error.
- При timeout/disconnect/outcome_unknown/scene_change_unverified: прекратить
  дальнейшие mutations. Никаких retry/rollback/finally scene cleanup.
- Client cancel/timeout не останавливает CLO. transport_status доступен снаружи;
  ping/getters идут через тот же executor и не могут обогнать занятый native call.
- После ошибки разрешена отдельная bounded read-only сверка, когда executor
  доступен. Не считать текущую похожую сцену доказательством истории выполнения.
- Плановая очистка своих объектов допустима только отдельными успешными шагами
  с fresh target guards и в разрешённом scope, не как recovery по умолчанию.
- Описывать actual result, remaining uncertainty и next action. Не объявлять
  готовой одежду по count/имени/площади.

## Текущий profile: что реально опубликовано

Номер профиля — исторический ярлык; перед сценарием сверять live
`get_session_info` capabilities и discovery, а не число из этого текста.
Source/live, принятые ранее подпакеты:

- Диагностика (1–7): info/status/ping, count, test rectangle,
  list/describe API. Introspection не исполняет описанные методы.
- Лекала (8–14): list, geometry, create, rename, copy, move, delete.
- Inventory (15–16): `get_fabric_list`/`get_avatars` — только read-only.
  Fabric indices — Object Browser, без colorway selection/filter; два real
  count4/names reads и 5 serial cross-domain cycles PASS, GUI подтверждён
  пользователем. Это не assignment/pose acceptance.
- Relationship (17–18): `get_pattern_fabric`/`assign_pattern_fabric`.
  Limited real API/readback PASS: own piece0→1→3, независимые mappings/geometry
  сохранены, плановое удаление; B05C copy inheritance/rename/move/independent
  assignment/index shift PASS. UI подтверждён, временный вид материала отдельно
  не оценён — не общая material/sewing гарантия copy. После delete всегда fresh
  list. Assign только после fresh names/current mapping, один effect →
  независимый readback; post-entry error/False не retry/rollback/cleanup.
  Контракт: `../../../docs/CLO_FABRIC_ASSIGNMENT_CHECK.md`.
- Outline (19): `get_pattern_outline` read-only, required fresh index/unique
  expected_name,1–512endpoints, mm от bbox TOP-LEFT/Ydown, не global2D/curve
  controls/lineIndex. **Документированное ограничение**: invalid_native_result
  на own fixture, native `[]`, и тот же отказ на двух существующих деталях;
  причина неизвестна. `[]` — не success и не повод на bbox/line fallback;
  marker одноразового probe не сбрасывать. Деталь `MCP_B06_outline_03cc0407`
  оставлена как есть. `../../../docs/CLO_OUTLINE_CHECK.md`.
- Линии (20): `get_pattern_lines` read-only, required fresh index/unique
  expected_name, один native read; `status="success"`, absolute API-mm frame;
  длины 4/4 совпали с `GetLineLength` на прямоугольнике. Live: на кривых
  `length_mm` > chord (arc-like), `mid_mm` — середина endpoints, `orientation`
  — dominant-axis; move/restore подтвердил translation invariance. Rotation,
  failure и дочерние формы открыты; не outline fallback.
  `../../../docs/CLO_LINE_API_CONTRACT_REVIEW.md`.
- Швы (21): `add_seamline_pair` — whole outer line pair, 6-arg overload,
  lineIndex из lines, strict bool directions; live seam_count+1, линии/geometry
  неизменны. Partial/child/merge/topstitch не входят.
  `../../../docs/CLO_SEAMLINING_CHECK.md`.
- Аватар (22): `import_avatar` — absolute `.avt`≤128MiB через live
  `ImportFile(path)` (ImportAvatar требует недоступный ImportExportOption);
  live count0→1. Pose/measurement/fit не входят.
- Arrangement (23–26): `get_arrangement` читает preset/offsets/orientation/type
  (native strings, units native_unspecified); `set_arrangement` назначает
  library point и делает ReDrape через `ApiTypes.ImportExportOption` flags;
  `set_arrangement_orientation` задаёт целое orientation 0..359 уже назначенной
  детали и проверяет readback после ReDrape; live visual gate показал, что поле
  само по себе не переставляет деталь в 3D (units/axis native не установлены);
  `set_arrangement_position` задаёт целые offsets 0..100 — это смещение, не
  поворот; live visual gate тоже без движения, поле не двигает 3D.
  2D и 3D позиции независимы; одинаковый arrangement не значит видимость.
  Live: Body_Front/Back/Arm points посадили детали, UI подтверждён.
  `../../../docs/CLO_FIT_CHECK.md`.

Worker restart не перезагружает embedded modules: `CLO_INVENTORY_CHECK.md`.
Не менять overload и не добавлять fallback автоматически. Simulation/import
project/pose/export остаются недоступны. Composition: list→outline→check;
cross-domain list→outline→`get_pattern_fabric` с тем же fresh target,
независимые наблюдения, не garment validation.

## Создание будущего доменного skill

Использовать `templates/domain-skill.md` и `templates/workflow-card.md`.
Каждый skill: один domain/класс задач, ясный trigger, required tools/version,
preconditions, verified recipes, anti-patterns, stop/reconciliation, evidence.
Не создавать skill на каждый из сотен методов. Detailed tool contracts живут
в каталоге; skill объясняет выбор и композицию и ссылается на них.
При API change обновлять coverage/card/live description/workflow/skill вместе.
Permission/validation живут в harness/server, не только в текстовом skill.
