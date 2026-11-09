# Статические source mappings CLO API

Сгенерировано `scripts/build_api_source_mappings.py`; дата проверки 2026-11-09.
Ни один исследуемый модуль не импортируется. Это A0-факты, **не native/contract acceptance**.

Донор: [`df150d95db604e4651bbbdfb151b8204209a7d12`](https://github.com/adriendelmas/clo3d-mcp-extended/tree/df150d95db604e4651bbbdfb151b8204209a7d12), MIT.
Attribution: Copyright (c) 2026 Violet Sphinx (original clo3d-mcp); Copyright (c) 2026 adriendelmas (clo3d-mcp-extended).
LICENSE/NOTICE: pinned URLs и SHA-256 в JSON; NOTICE указывает upstream Ubani-Studio/clo3d-mcp и отсутствие SDK/аффилиации CLO.
Сохранены нормализованные факты, сигнатуры и описания; production-код донора не копируется/не выполняется.

## Полнота инвентаря

- `donor_tools`: `170`
- `donor_handlers`: `172`
- `donor_server_tools`: `33`
- `donor_extended_tools`: `137`
- `donor_reachable_native_ids`: `336`
- `donor_tools_without_native_references`: `3`
- `legacy_tools`: `47`
- `legacy_handlers`: `47`
- `legacy_handler_functions_outside_registry`: `2`
- `shared_donor_legacy_tool_names`: `44`
- `donor_only_tool_names`: `126`
- `legacy_only_tool_names`: `['import_dxf', 'list_extensions', 'ping']`
- `current_tools`: `20`

## Схема и доказательства

Основной JSON — индекс; списки хранятся в `mappings/*.json` shards <=180000 bytes, каждый с SHA-256/count. `load_mappings(path)` возвращает full structure и flat aliases `donor_tools`, `local_legacy_tools`, `current_tools`, `source_refs` для coordinator join.
`donor.tools` содержит все170 имён, exact source descriptions, нормализованные Python signatures/parameters, literal routes, handler_commands, native_ids и явные name_aliases.
`donor.handlers` содержит все172 registry commands, handler/registry line ranges, qualified references и helper chains. `local.legacy` — отдельные47 tools/47 registry commands и DEV extras вне registry.
`local.current.tools` — отдельные19 tools: profile, contract/adapter/test evidence, primary/supporting native ids и раздельная local/partial/historical acceptance. Outline real BLOCKED: user manual one-shot native [] for existing own target;cause unknown,not accepted. `shared_native_alias_candidates`/`current_replacement_limits` явно отделяют aliases от ограниченных замен.
`sources` содержит SHA-256 исходных bytes, lengths, pinned raw/browse URLs (донор), Git blob SHA-1 и local relative paths. При donor rebuild bytes сверяются с blob IDs pinned tree; local bytes не нормализуются по CRLF, при смене line endings пересобрать.
`normalized_sha256` защищает целостность нормализованных donor facts (не криптографическая подпись). Offline-проверка не доказывает соответствие недоступному raw source: для этого нужен pinned refresh/cache rebuild.
`references.kind=direct_call` означает AST Call.func; `callable_reference` — ссылка на функцию/тип, не direct invocation. `invoked_via` фиксирует передачу callable аргумента helper-параметру и место его вызова.
`via` — кратчайшая синтаксическая цепочка helper calls; confidence syntactic_direct/indirect не означает контрактную корректность/реальное исполнение. Dynamic getattr остаются отдельными unresolved expressions.
Join с official manifest выполняется по `module.symbol`; overload/type/units/return semantics автоматически не назначаются.

## Воспроизводимость

```powershell
python scripts/build_api_source_mappings.py --check
python scripts/build_api_source_mappings.py --refresh-donor --write
# Offline rebuild donor facts from a previously downloaded research cache:
python scripts/build_api_source_mappings.py --donor-cache <cache-folder> --check
```

По умолчанию сеть выключена; --check валидирует сохранённый donor snapshot и заново строит local facts AST. --write обновляет только index/report/mapping shards; refresh bounded, pinned, без retries.
Cache содержит tree.json и выбранные source paths; это исследовательский ввод, не IPC и не production dependency. Скрипт cache не исполняет и не сохраняет donor source в checkout.
Unit tests: `uv run --frozen --with pytest pytest -q tests/test_api_source_mappings.py`. Они не вызывают CLO и не являются real-CLO evidence.

## Явные local legacy aliases

- `assign_fabric_to_pattern` → wire `assign_fabric` → `handle_assign_fabric` (routing only).
- `get_pattern_bounding_box` → wire `get_bounding_box` → `handle_get_bounding_box` (routing only).
- `save_project` → wire `save_file` → `handle_save_file` (routing only).

`open_file` / `import_file` и `add_fabric` / `import_fabric` имеют общие native names, но это не автоматически эквивалентные контракты. `list_extensions` не имеет native handler.
Legacy copy_pattern/CopyPatternPiecePos не объявлен эквивалентом current copy_pattern_with_offset/CopyPatternPieceMove; create_pattern current покрывает только simple straight polygons.

## Current19 и граница приёмки

- `assign_pattern_fabric` (pattern_package): `fabric_api.AssignFabricToPattern`; evidence `docs/CLO_FABRIC_ASSIGNMENT_CHECK.md`.
- `copy_pattern_with_offset` (pattern_package): `pattern_api.CopyPatternPieceMove`, `pattern_api.SetPatternPieceName`; evidence `docs/PATTERN_API_CHECK.md`.
- `create_pattern` (pattern_package): `pattern_api.CreatePatternWithPoints`, `pattern_api.SetPatternPieceName`; evidence `docs/PATTERN_API_CHECK.md`.
- `create_test_rectangle` (base_service): `pattern_api.CreatePatternWithPoints`; evidence `docs/P3_MCP_CHECK.md`.
- `delete_pattern` (pattern_package): `pattern_api.DeletePatternPiece`; evidence `docs/PATTERN_API_CHECK.md`.
- `describe_clo_api` (pattern_package): нет фиксированного native вызова; evidence `docs/PATTERN_API_CHECK.md`.
- `get_avatars` (pattern_package): `export_api.GetAvatarCount`, `export_api.GetAvatarNameList`; evidence `docs/CLO_INVENTORY_CHECK.md`.
- `get_fabric_list` (pattern_package): `fabric_api.GetFabricCount`, `fabric_api.GetFabricName`; evidence `docs/CLO_INVENTORY_CHECK.md`.
- `get_pattern_count` (base_service): `pattern_api.GetPatternCount`; evidence `docs/P3_MCP_CHECK.md`.
- `get_pattern_fabric` (pattern_package): `fabric_api.GetFabricIndexForPattern`; evidence `docs/CLO_FABRIC_ASSIGNMENT_CHECK.md`.
- `get_pattern_geometry` (pattern_package): `pattern_api.GetPatternPieceName`, `pattern_api.GetPatternPiecePos`, `pattern_api.GetPatternPieceArea`, `pattern_api.GetBoundingBoxOfPattern`; evidence `docs/PATTERN_API_CHECK.md`.
- `get_pattern_lines` (pattern_package): `pattern_api.GetPatternLineInfo`; evidence `docs/CLO_LINE_API_CONTRACT_REVIEW.md`.
- `get_pattern_list` (pattern_package): `pattern_api.GetPatternCount`, `pattern_api.GetPatternPieceName`; evidence `docs/PATTERN_API_CHECK.md`.
- `get_pattern_outline` (pattern_package): `pattern_api.GetPatternOutlinePoints`; evidence `docs/CLO_OUTLINE_CHECK.md`.
- `get_session_info` (base_service): нет фиксированного native вызова; evidence `docs/P3_MCP_CHECK.md`.
- `list_clo_api` (pattern_package): нет фиксированного native вызова; evidence `docs/PATTERN_API_CHECK.md`.
- `move_pattern_relative` (pattern_package): `pattern_api.SetPatternPieceMove`; evidence `docs/PATTERN_API_CHECK.md`.
- `ping` (base_service): нет фиксированного native вызова; evidence `docs/P3_MCP_CHECK.md`.
- `set_pattern_name` (pattern_package): `pattern_api.SetPatternPieceName`; evidence `docs/PATTERN_API_CHECK.md`.
- `transport_status` (base_service): нет фиксированного native вызова; evidence `docs/P3_MCP_CHECK.md`.

PATTERN_API_CHECK.md: исторический CLO2026.1, simple polygon и load10, <=2 тестовых деталей, <=256 всего; count/name/position/area/bbox и пользовательское visual/UI подтверждение. Точный patch build не зафиксирован.
Introspection доказывает presence/docstrings, не исполнение найденных функций. Транспортные status/ping/diagnostic evidence не расширяют pattern gate. Не покрыты curves/holes/avatar/sewing/simulation/import/export/point editing/большие сцены.
Тестовые ссылки — traceability, не новые результаты тестов. Full official overload/build traceability и весь tool-authoring DoD не заявлены.

## Ограничения

- Static AST evidence only. No donor/local inspected module import, no CLO call, restart, mutation or SDK execution.
- Native ids are module.symbol. No inferred official overload, binding/type availability, error semantics, units or contract acceptance.
- Helper reachability is a conservative syntactic graph including conditional/fallback paths, not proof that a call occurs. One shortest evidence path per helper; callable references remain distinct from direct calls.
- getattr/dynamic module/type lookup and strings are reported as unresolved expressions, never expanded into guessed native calls. Arbitrary alias/dataflow, closures, decorators and reflection are not evaluated.
- Current command-to-native selection is explicitly reviewed metadata tied to AST callsite evidence; references may be shared preflight/readback/conditional sites and are not an execution trace.
- Exact descriptions are source docstrings (ast.get_docstring clean=True), signatures are ast.unparse-normalized Python declarations, not generated MCP JSON schemas or live tools/list.
- Test function references establish traceability only, not execution/pass status or complete scenario coverage. Historical acceptance remains limited to cited documents and no new real CLO gate is closed.
- Official coverage join and reconciliation of removed names/types are separate; raw donor symbol matches are not coverage percentages.
