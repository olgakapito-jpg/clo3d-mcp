# Avatar + arrangement/fit — статус и probe

Target: CLO2026.1.336.

## Avatar import — live PASS

`import_avatar` с absolute `.avt` (≤128MiB) через live `ImportFile(path)->bool`
(ImportAvatar недоступен: его `ImportExportOption` тип отсутствует в binding).
Live gate 2026-11-09, build `5baaf8a15555`: `avatar_count 0→1`,
name `Female_Mannequin_final_v11_Aforsize_03`; path не эхоился.

## Arrangement — блокер и probe

- GetArrangementList/GetArrangementOfPattern (+setters) доступны.
- `ReDrape3DArrangement(opt)` требует `Marvelous::ImportExportOption`; в live
  `export_api.ImportExportOption/NewImportExportOption` available=false.
  Drape через MCP пока не подтверждён.
- `diagnostics/clo3d_mcp_arrangement_probe.py` читает arrangement для всех
  деталей (≤32) и печатает keys + numeric/bool values, строки только type/len.
  Один Run, idle service, без мутаций и retry. Нужен, чтобы понять:
  arranged ли детали после avatar import, какие индексы/поля использовать.

Ожидаемый JSON `clo_arrangement_probe_v1`: `count`, `list_length`,
`pieces[i].arrangement.keys/fields`.

## 3D visibility: уточнено 2026-11-09

Пять деталей (A–D seam + MCP_3D_TEST) имеют одинаковый arrangement (`Arrangement
Point`, offsets50/50/50, orientation180, typeCurved). **Все пять видны в 3D.**
Первые четыре были за пределами экрана; пользователь увидел их после zoom-out.
Значит 2D-координата и 3D-положение независимы, а сшитость не скрывает детали.
Предыдущая гипотеза про необходимость simulation для видимости **опровергнута**;
simulate probe не нужен и не запускался.

## ReDrape через ApiTypes.ImportExportOption

`utility_api.ReDrape3DArrangement` требует `Marvelous::ImportExportOption`.
`export_api.ImportExportOption/NewImportExportOption` в live недоступны, но тип
документирован как `ApiTypes.ImportExportOption` с полями
`bAddArrangementPoints`, `bAutoCreateFittingSuit`, `bMoveGarment`.
`diagnostics/clo3d_mcp_redrape_probe.py` создаёт option через `ApiTypes`,
ставит эти флаги (если есть), вызывает ReDrape один раз и печатает counts.
One-shot, avatar>=1, visual-only evidence; при option/construct/API exception —
STOP. После Run пользователь смотрит 3D: появились ли детали на аватаре.

## Дальше: SetArrangement indices

ReDrape v2 прошёл native (flags applied, return None), но визуально ничего не
изменил: вероятно, ReDrape только пересчитывает уже назначенный arrangement, а
детали стоят на `Arrangement Point`. Нужно назначить реальные points через
`SetArrangement(patternIndex, arrangementIndex)`, индекс брать из 110-элементной
библиотеки.

`diagnostics/clo3d_mcp_arrangement_list_probe.py` читает `GetArrangementList` и
печатает до110 записей: preset name/type/offset/orientation (read-only, one-shot).
По нему выберем индексы front/back/sleeve и сделаем bounded `set_arrangement`
tool с readback `get_arrangement` + UI.

## Arrange probe: SetArrangement + ReDrape

`diagnostics/clo3d_mcp_arrange_probe.py` назначает own-деталям реальные
arrangement points и делает один ReDrape:

- MCP_3D_TEST → 59 Body_Front_Center_1
- MCP_SEAM_A → 60 Body_Front_Center_2
- MCP_SEAM_B → 43 Body_Back_Center_2
- MCP_SEAM_C → 6 Arm_Front_1_L
- MCP_SEAM_D → 0 Arm_Back_1_L

Пять `SetArrangement` + readback имени + один ReDrape с ApiTypes option/flags.
One-shot, no retry; exception на assign/redrape → STOP. Effect visual-only; если
детали встали на аватар — оформляем `set_arrangement` tool и повторяем ReDrape
через отдельный tool.

## set_arrangement_orientation — live readback PASS

2026-11-10, build `7e0f73d2c06e` (Stop→Start после изменения embedded
`pattern_api`; server/executor builds совпали). `MCP_SEAM_A` 180→90:
`verified:true`, `redrape:true`, post-ReDrape `GetArrangementOfPattern` вернул
orientation 90; name/offset/type и остальные четыре детали не изменились.
`get_arrangement` подтвердил то же. **Визуальная проверка пользователя: деталь в 3D
не изменилась.** Значит `SetArrangementOrientation` меняет только arrangement-поле
и сам по себе не переставляет/не поворачивает деталь на этой сборке; native
units/axis остаются неустановленными. 2D geometry не читалась повторно, avatar
fit/simulation не входят. Поворот гизмо в 3D через API не найден; следующий
кандидат — `SetArrangementPosition`/offsets, но это смещение, не rotation.

## set_arrangement_position — live readback PASS, визуально без изменений

2026-11-10, build `57a23bf2cfdb`: `MCP_SEAM_A` offsets 50/75/50→50/75/80,
`verified:true`, post-ReDrape readback offsets точные, name/orientation/type и
остальные четыре детали не изменились. **Визуальная проверка пользователя:
деталь в 3D не сдвинулась.** Значит offsets, как и orientation, сами по себе не
двигают деталь; `SetArrangement` (смена point) двигал её в прошлом probe.
Оставшиеся рычаги: смена arrangement point, ручной 3D-гизмо (вне API) или
simulation. Native units не установлены; это не rotation.

## Toolchain PASS 2026-11-10 (build `b2f3fce822d6`)

Avatar `Mara_09_eye_Joint`, 79 measurements: 78 `Default` + 1 user
`CircumferenceMeasure_283316` (817.5 мм). Default-мерки Line Pin **не
поддерживают** (`scene_change_unverified`, attachments остаются 0); пользовательская
Circumference работает.

Собран тестовый верх `TEE_FRONT`/`TEE_BACK` 400×300:
`create_pattern` → `set_arrangement` (60/43) → `get_pattern_lines` → верхние
`line2` обеих панелей прикреплены к `CircumferenceMeasure_283316`
(`attachments=2`) → два боковых шва `line3↔line3` и `line1↔line1`
(`seam_count=2`) → `simulate(60)` (`verified`, 1110 мс, 2 patterns) →
`get_3d_screenshot`.

Toolchain PASS: create → arrange → avatar measure pin → two side seams →
simulation → self-check screenshot. Визуально garment **остаётся на торсе**, но
посадка черновая: ткань собрана/прозрачна, есть диагональная складка; fit не
принят. `get_avatar_measurements`/`get_pattern_avatar_attachments`/
`get_seamline_pairs` readback совпали. Скриншот зависит от текущей камеры: после
seam/solver камера может зумиться, нужен ручной Fit/zoom.

## Следующие шаги

1. Fit: попробовать панели ниже (≈400×180), pin низа к мерке талии или более
   длинную simulation; это отдельные visual gates.
2. Default avatar measures не подходят для Line Pin; нужна user Tape/Circumference
   (или импорт CSV — отдельный tool).
3. Свободного 3D-transform в Python/C++ API нет; gizmo остаётся UI-only.
4. `get_avatar_measurements` возвращает 79 мерок Mara; старый 0-мерный манекен
   заменён.
5. Extended tools live `8e408f3132a0`: `export_view_image` (front 800×600),
   `export_snapshot_2d`, `set_camera_view`, `get_pattern_body_details`,
   `get_pattern_details`, `get_mesh_counts` PASS; `set_pattern_grain_direction`
   PASS на копии; `set_particle_distance` BLOCKED (readback mismatch);
   `reset_cloth_arrangement`/`import_avatar_measurements` pending.
