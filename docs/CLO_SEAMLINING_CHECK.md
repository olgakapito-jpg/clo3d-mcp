# Швы (seamline pairs) — контракт и bounded probe

Target: CLO2026.1.336. Статус: **whole-line seam probe и live tool gate пройдены**;
`add_seamline_pair` опубликован (21 tools), partial/child/merge остаются
отдельными пакетами. Это отдельный домен, не продолжение построения.

## API-факты

- `pattern_api.AddSeamlinePairGroup` — три overload:
  - `(patternA, lineA, patternB, lineB, directionA, directionB) -> bool`
  - `(patternA, lineA, patternB, childIndex, lineB, directionA, directionB) -> bool`
  - `(patternA, childA, lineA, patternB, childB, lineB, directionA, directionB) -> bool`
- Docstring первого overload противоречит сигнатуре: `@return name of sewing
  group` при объявленном `-> bool`. Реальный literal/тип нужно наблюдать.
- `directionA/B`: true forward, false backward. Порядок и направление пары
  влияют на stitch orientation; фиксировать явно.
- `lineIndex` — линия границы в порядке обхода; брать из свежего
  `GetPatternLineInfo` (`lineIndex`), не из позиции массива. Child overloads
  используют child namespace и в первый tool не входят.
- Reads: `GetSeamlinePairGroupCount`, `GetSeamlinePairGroupName`,
  `GetSeamlinePairGroupListInPattern`;
  `GetPatternGroupsBySeamlineConnectivity(bool,bool)` → JSON groups.
- `AddSeamlinePairGroupPartial` возвращает `int`, `SEAMLINE_PAIR_SUCCESS=0`;
  ratios start<end; отдельный следующий пакет.
- `MergeSewnPatterns`, `DeleteLine` — destructive, не в первый пакет.

## Probe

`diagnostics/clo3d_mcp_seam_probe.py`, один Run, verified idle service:

1. Находит own `MCP_SEAM_A`/`MCP_SEAM_B` (уже созданы, 120×80), уникальные имена.
2. Берёт `lineIndex=0` у обеих (длины120), снимает lines/geometry/seam count.
3. Один `AddSeamlinePairGroup(A,0,B,0,True,True)`.
4. Читает native return type/literal, seam count/connectivity, lines/geometry
   после; имена групп не выводятся.
5. Один native seam call, без retry; exception → STOP.

Ожидаемый JSON `clo_seam_probe_v1`: `seams_before/after`, `native_return_type`,
`native_return`/`native_return_int`, `lines_after == lines_before`,
`geometry_after == geometry_before`, `connectivity_after.group_count`.

## Результат probe 2026-11-09

Сцена: example pieces + own `MCP_SEAM_A` index5/`MCP_SEAM_B` index6, line0
длина120. Один `AddSeamlinePairGroup(5,0,6,0,True,True)`:

- `native_return_type=bool`, literal `true` (docstring с name string опровергнут);
- `seams_before=16`, `seams_after=17`;
- line lengths/line count и area/bbox обеих деталей не изменились;
- `connectivity_after` status success, group_count3.

Вывод: whole-line seam создаётся и readback-verifiable. Child overloads и
partial остаются отдельными gate.

## Live tool gate 2026-11-09

Build `975dcebc4e10` (server==executor), 21 tools. Созданы own `MCP_SEAM_C`
index9/`MCP_SEAM_D` index10 (120×80). Вызов
`add_seamline_pair(C,0,D,0,True,True)` → `{ok:true,verified:true,seam_count:18}`
(до этого 17). Независимый readback: lineCount4/длины120–80 у обеих, area
9599.999/bbox120×80/position без изменений. Partial/child/merge не вызывались.

## Границы

- Только own pieces; чужие детали не трогать.
- Если seam count не вырос или geometry/lines изменились — считать неизвестным
  эффектом, не повторять и не удалять.
- Partial seam, topstitch, buttons, merge — отдельные пакеты.
- После probe own pieces/seam остаются; удаление — отдельными fresh-list шагами.

## Правильная сборка: два боковых шва

Исторические probe/live gate (`A0↔B0`, `C0↔D0`) проверяли native call и
`seam_count`, а **не** замкнутость изделия. Один `AddSeamlinePairGroup` — одна
пара кромок. Для трубы из двух панелей нужны два шва:
`A.left↔B.left` и `A.right↔B.right`, каждый отдельным вызовом с readback
`seam_count`+1 и неизменных lines/geometry. `line0↔line0` или
`bottom↔bottom` трубу не закрывает. `direction_a/b` выбирать по физическим
концам кромок; `True/True` не универсален. Если второй шов не прошёл —
«открытая труба, частичная сборка», STOP без retry/cleanup. Замкнутость —
топология, не посадка и не simulation. Skills: `clo-sewing`, `clo-seamlines`;
рецепт: `CLO_MCP_WORKFLOWS.md`.

## Live A/B rebuild и два боковых шва 2026-11-10

Build `57a23bf2cfdb`: own `MCP_SEAM_A/B` удалены и созданы заново (120×80,
прежние 2D-координаты), возвращены на `Body_Front_Center_2`/
`Body_Back_Center_2`. Свежие lines: left=`line3` (80 мм, top→bottom),
right=`line1` (80 мм, bottom→top) у обеих.

- `add_seamline_pair(A,3,B,3,true,true)` → verified, `seam_count` 2;
- `add_seamline_pair(A,1,B,1,true,true)` → verified, `seam_count` 3;
- lines/geometry обеих не изменились.

**Результат:** оба бока сшиты, но швы **перекрещены** — труба перекручена.
Пользователь развернул `MCP_SEAM_B` вручную гизмо, после чего 3D выглядит
правильно. `True/True` на обеих сторонах не является правильным рецептом;
направления пар и 3D-поворот через API не установлены. Перекрёст виден только
визуально, `seam_count` его не показывает.

## Read-only проверка швов

`get_seamline_pairs` опубликован: count, имена групп и membership по каждой
детали через `GetSeamlinePairGroupCount/Name/ListInPattern`. Mutation не нужна
для проверки; delete/merge/partial/topstitch не входят. Live build
`aafcfac0323d`: 3 группы; C/D в одной, A/B в двух, MCP_3D_TEST без швов.

## TEE toolchain 2026-11-10

`TEE_FRONT`/`TEE_BACK` 400×300: верхние `line2` прикреплены к user
`CircumferenceMeasure_283316`; два боковых шва `line3↔line3` и `line1↔line1`
(`true/true`) → `seam_count=2`, обе детали в обеих группах; readback lines/
geometry не проверялся после швов отдельно, но mutation вернул verified.
`get_seamline_pairs` подтвердил 2 группы. Визуально после Fit перекрёста не
видно, но ткань собрана; fit не принят. Line Pin + simulation удерживают garment.

## Будущий MCP tool (proposal)

`add_seamline_pair`: strict args `pattern_a_index/expected_name_a/line_a_index,
pattern_b_index/expected_name_b/line_b_index,direction_a,direction_b`; preflight
fresh list/lines, one native call, result `verified,seam_count,seam_group_index`;
errors `stale_pattern`, `invalid_line_index`, `invalid_native_result`,
`scene_change_unverified`, `command_error`; no retry/cleanup. Return literal
`AddSeamlinePairGroup` не считать успехом без readback seam count.

Local tests: `tests/test_seam_probe.py`.
