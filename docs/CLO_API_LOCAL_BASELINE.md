# Локальный baseline переноса — 47 legacy tools

Источник: `src/clo3d_mcp/server.py`, native mapping —
`plugin/clo3d_mcp_plugin.py`. Read-only инвентаризация 2026-11-09, без импорта
legacy listener. Это **не** полный официальный API и не граница проекта.

## Каталог

```text
Scene/project (5):
  get_project_info, new_project, open_file, save_project, get_garment_info
Pattern/arrangement (10):
  get_pattern_count, get_pattern_list, get_pattern_info,
  get_pattern_bounding_box, set_pattern_name, copy_pattern, delete_pattern,
  flip_pattern, create_pattern, get_arrangement_list
Fabrics/materials (9):
  get_fabric_list, add_fabric, replace_fabric, assign_fabric_to_pattern,
  set_fabric_color, get_fabric_for_pattern, get_fabric_count,
  import_fabric, delete_fabric
Export (8):
  export_obj, export_fbx, export_glb, export_gltf, export_thumbnail,
  export_snapshot, export_turntable, export_tech_pack
Import (2):
  import_file, import_dxf
Simulation (2):
  simulate, set_simulation_quality
Colorways (5):
  get_colorways, set_current_colorway, set_colorway_name,
  copy_colorway, delete_colorway
Avatar (4):
  get_avatars, get_avatar_genders, show_hide_avatar, import_avatar
Infrastructure (2):
  list_extensions, ping
```

## Сопоставление с принятым новым путём

- `get_pattern_count`, `get_pattern_list`, `set_pattern_name`, `delete_pattern`,
  `ping` покрыты каноническими одноимёнными инструментами. Схемы ответов/параметров
  не обязаны быть legacy-совместимыми: появились лимиты, expected_name/readback.
- Bounding box покрывается полем `get_pattern_geometry`, не нужен дублирующий
  native route. `get_pattern_info` НЕ покрыт полностью этой геометрией:
  GetPatternInformation содержит другие сведения.
- `copy_pattern_with_offset` покрывает копирование со смещением; старый
  CopyPatternPiecePos и новый CopyPatternPieceMove не объявляются одной
  позиционной семантикой. Для абсолютной позиции нужен отдельный контракт.
- `create_pattern` покрыт частично: simple straight polygon, 3–64 пары [x,y].
  Кривые/type triplets/другие формы ещё не покрыты.
- `flip_pattern`, arrangement и прочие домены не реализованы новым пакетом.

Принятые дополнительные tools нового пути: `transport_status`,
`get_session_info`, `create_test_rectangle`, `list_clo_api`, `describe_clo_api`,
`get_pattern_geometry`, `copy_pattern_with_offset`, `move_pattern_relative`.
Часть — инфраструктура/замены, а не новые native capabilities.

## Устранение дублей и исторических имён

- `open_file` / `import_file`: оба вызывают ImportFile. Будущий canonical route
  определяется форматом и add/replace semantics, не двумя одинаковыми handlers.
- `add_fabric` / `import_fabric`: оба AddFabric, один canonical route.
- `get_avatar_genders`: проекция общего avatar snapshot при необходимости.
- `save_project` → wire `save_file`; bounding box → `get_bounding_box`;
  assignment → `assign_fabric`. Новая naming-схема согласуется A1, случайные
  legacy mismatches не переносить автоматически.

## Handler extras и непереносимые механизмы

47 штатных записей HANDLERS: 46 plugin routes для MCP tools и `stop`.
`list_extensions` формируется внешним legacy server, native handler отсутствует.
Дополнительно два DEV handler: `run_script`, `reload_plugin`; всего 49 функций
`handle_*`, не 49 штатных MCP tools. Session stop уже есть в новом lifecycle.

Не переносить DEV exec/reload, auto-loaded extensions, файловый listener,
retry-on-error и blocking fallback. Полное покрытие официального API не
означает повторное включение этих legacy механизмов.

Дальнейшие соответствия official/runtime/extended формируются в реестре W0:
`docs/CLO_API_COVERAGE_PLAN.md`. Не считать этот baseline доказательством
native compatibility или прохождения новых реальных сценариев.
