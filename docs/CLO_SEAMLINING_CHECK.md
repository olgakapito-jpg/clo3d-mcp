# Швы (seamline pairs) — контракт и bounded probe

Target: CLO2026.1.336. Статус: **whole-line и partial seam probe/live gates
пройдены**; `add_seamline_pair` и `add_seamline_pair_partial` опубликованы.
Калибровка 2026-11-11 уточнила семантику ratios и reference-плана; см. ниже.
Это отдельный домен, не продолжение построения.

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
  входные ratios **line-relative и ascending** (`start < end`). Export-нутый
  `LengthParam` — доля **периметра детали**, не line-relative; формула в
  калибровочном разделе ниже.
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

## Калибровка partial seam 2026-11-11

Build `a0ea945638b3` (server==executor). Сцена: `CAL_A/B` 120×80 (perimeter
400), `CAL_C/D` 200×100 (perimeter 600), каждый seam — отдельная линия,
чтобы исключить наложения. Все вызовы `add_seamline_pair_partial` вернули
`verified`, `seam_count` вырос на 1; затем `export_pattern_json`.

| Сторона | Линия / периметр | Вход (line-relative) | Export `LengthParam` |
| --- | --- | --- | --- |
| CAL_A/B | line0, 120 / 400 | 0.25–0.75 | 0.075–0.225 |
| CAL_A/B | line1, 80 / 400 | 0.25–0.75 | 0.350–0.450 |
| CAL_C/D | line1, 100 / 600 | 0.25–0.75 | 0.375–0.45833 |
| CAL_C/D | line3, 100 / 600 | 0.0–0.5 | 0.83333–0.91667 |
| CAL_A/B | line3, 80 / 400, dir=false | 0.30–0.90 | 0.980–0.860 |

Правило:

```text
export_start = (prefix_offset(line) + r_start * line_length) / perimeter
r            = (export * perimeter - prefix_offset(line)) / line_length
```

`prefix_offset` — сумма длин предыдущих линий `LineList` в порядке обхода.
Для `line0` offset=0, поэтому там `export = r * L / P`; для остальных линий
это неверно — именно эта ошибка дала сдвинутые и наложенные швы. Обратное
преобразование восстановило все входные ratios калибровки (7 швов, float
точность). `direction=false` только меняет порядок export (`fStart`
соответствует входному `end`), физический интервал тот же.

Descending input `0.9 → 0.3` native отклонил: `invalid_native_result`,
`seam_count` не изменился. Вход всегда ascending; ориентация — `direction`.

## Reference-проект: 20 groups = 80 segment pairs

`trousers_sewn_reference.json` (ручной проект, 20 seam groups) хранит
`LengthParam` как perimeter-доли, а каждая сторона группы покрывает
**непрерывный пробег нескольких линий**. Например группа 0:
`BACK_L` линии 4→11 (1064.8 мм) ↔ `FRONT_L` линии 27→19 (1064.6 мм).
Концы пробегов совпадают с границами линий с точностью 0.000 мм; исключение —
`WAISTBAND line2`, где несколько групп делят одну линию на последовательные
интервалы (0.024–1.0 в line-relative после преобразования).

Декомпозиция по stitch start (`seam_plan.py`) даёт 91 пару; 11 sub-0.5mm
slivers на границах отфильтрованы, остаётся **80 dispatchable пар**, 18 из них —
whole-line. Один сегмент `BACK_R line18` покрыт двумя группами
(`Sewing_645874` и `Sewing_690044`) — это топология самого эталона; план
сохраняет его как duplicate-warning, а не молча удаляет. Расхождение длин
сторон до 20.6 мм (`FRONT_R` 787.25 ↔ `BACK_R` 807.86) — посадка/ease, а не
ошибка ratios; план распределяет её пропорционально.

Один `add_seamline_pair`/partial-вызов покрывает **только одну** линию
`LineList`. Проверено на панели из 5 точек: вызов по `line0` сшил 60.8 мм из
120 мм кромки, export дал `fEnd=0.15144`. API merge-lines/edge-path не
предоставляет; `DeletePoint` есть нативно, но не опубликован и уничтожил бы
насечки. Поэтому multi-segment кромка воспроизводится несколькими парами.

`ImportPatternJSON` швы не восстановил: live-импорт 5 деталей дал
`seam_count_after=0`. Прямая передача reference `LengthParam` в partial tool
неверна (это не line-relative ratios) и дала CLO-предупреждение
«abnormal/overlapped seamlines». Рабочий путь — `seam_plan.py`:
декомпозиция, конвертация perimeter-долей в line-relative, валидатор
(`0 <= start < end <= 1`, попадание в линию, нет частичных overlap; точный
duplicate между группами — warning).

## Staged replay 2026-11-11

Build `31c59dbf42a8`. Пустая сцена → `import_pattern_json(trousers_olga_clo.json)`
(5 деталей, `seam_count=0`). Из `seam_plan_olga.json` применено **80 пар**:
13 whole-line cross-pattern + 67 partial; 11 sub-0.5mm slivers отфильтрованы.

Порядок и результат: left side 12, right side 12, right inseam 12, left inseam
10, center front 6, center back 11, darts 4, waistband 12, waistband self 1.
Каждый вызов `verified`, `seam_count` 0→80, без retry/unknown. Darts и
waistband self-seam сделаны partial с ratios 0..1: `add_seamline_pair`
отклоняет одинаковые pattern indices.

Arrangement: `Leg_Front_L`/`Leg_Back_L`/`Leg_Front_R`/`Leg_Back_R` +
`Body_Waist_L`; waistband orientation 180; `simulate(120)` verified.
Front/back screenshots показывают собранные брюки без explosion/разрывов и без
зазора на поясе. Это visual observation, не fit-вердикт; `Body_Back_Waist` и
поворот 90° давали зазор/складки, а сжатие пояса до 0..1 — collapse; рабочий
вариант — `Body_Waist_L` + 180.

## Будущий MCP tool (proposal)

`add_seamline_pair`: strict args `pattern_a_index/expected_name_a/line_a_index,
pattern_b_index/expected_name_b/line_b_index,direction_a,direction_b`; preflight
fresh list/lines, one native call, result `verified,seam_count,seam_group_index`;
errors `stale_pattern`, `invalid_line_index`, `invalid_native_result`,
`scene_change_unverified`, `command_error`; no retry/cleanup. Return literal
`AddSeamlinePairGroup` не считать успехом без readback seam count.

Local tests: `tests/test_seam_probe.py`.
