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
  готовой одежду по count/имени/площади. Расширенный profile16 включает только
  get_fabric_list/get_avatars reads (не assignment/import). Fabric indices —
  Object Browser, без colorway selection/filter. Новый контракт заменил снятый
  colorway prototype; два real count4/names reads в свежем CLO успешны,
  GUI/UI подтверждены пользователем;5serial cross-domain read cycles/geometry5
  PASS. Это не assignment/pose acceptance. Worker restart не reload embedded modules:
  ../../../docs/CLO_INVENTORY_CHECK.md. Не менять overload автоматически.
  Source/live profile18 добавляет get_pattern_fabric/assign_pattern_fabric;
  после fresh restart limited real API/readback PASS: own piece0→1→3,independent
  mappings/geometry preservation5,planned own delete. User UI confirmed;
  temporary appearance не оценена. B05C copy inheritance/rename/move/independent
  assignment/lower-delete index shift/fresh-index assignment real PASS;
  не общая material/sewing гарантия copy. После delete всегда fresh list.
  Read-only runner pattern-fabric-inspection real PASS,2passes5mappings,0mutations.
  Всё равно сверять actual discovery/capabilities. Assign только после
  fresh names/current mapping, один effect→independent readback; post-entry
  error/False не retry/rollback/cleanup. Full contract:
  ../../../docs/CLO_FABRIC_ASSIGNMENT_CHECK.md. Sewing/simulation недоступны.

## Создание будущего доменного skill

Использовать `templates/domain-skill.md` и `templates/workflow-card.md`.
Каждый skill: один domain/класс задач, ясный trigger, required tools/version,
preconditions, verified recipes, anti-patterns, stop/reconciliation, evidence.
Не создавать skill на каждый из сотен методов. Detailed tool contracts живут
в каталоге; skill объясняет выбор и композицию и ссылается на них.
При API change обновлять coverage/card/live description/workflow/skill вместе.
Permission/validation живут в harness/server, не только в текстовом skill.
