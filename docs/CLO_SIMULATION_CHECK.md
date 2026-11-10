# Simulation — bounded probe (B09)

Target: CLO2026.1.336. Статус: **BLOCKED_IMPLEMENTATION**; опубликован bounded
`simulate(steps 1..300)` tool. Probe ниже остаётся историческим evidence, не
fit-приёмка. Tool проверяет native bool и неизменный список деталей, не посадку.

## API-факты

- `utility_api.Simulate(_steps: int) -> bool`; `_steps` = число шагов/кадров.
  Динамика (time step, CG iterations и т.п.) берётся из текущих simulation
  settings, probe их не меняет.
- `True` означает только успешный native call, не физически правильную посадку.
- `Simulate` — синхронный native call; клиентский timeout не отменяет его.
  Длинный вызов может блокировать UI; поэтому один короткий запуск.

## Probe

`diagnostics/clo3d_mcp_simulate_probe.py`, один Run в Script Editor при verified
idle service и явном разрешении пользователя. `STEPS = 60` (можно изменить до
запуска; повторный Run в той же сессии запрещён marker-ом).

Preconditions: service active/ready, executor ready, verified UI thread,
`pattern_count 1..256`, `avatar_count >= 1`. Иначе BLOCKED до native call.

Ожидаемый JSON `clo_simulate_probe_v1`:
- `status: observed`, `native_return_type: bool`, `native_return`;
- `steps`, `elapsed_ms`, `pattern_count_before/after`, `avatar_count`;
- `names_unchanged`;
- `stop_reason: stop_no_retry`.

Остановка: exception/non-bool → `command_error`, без retry; `native_return=false`
→ observed, не success. Отсутствие avatar/count/ready → BLOCKED, native call не
выполняется.

## Probe run 2026-11-10

Build `57a23bf2cfdb`, один Run пользователем:
`status=observed`, `native_return=true`, `steps=60`, `elapsed_ms=1031`,
`pattern_count=5/5`, `avatar_count=1`, `names_unchanged=true`. Native exception
и non-bool не было; marker израсходован, повторный Run в этой сессии запрещён.
Визуальный результат: **посадки нет**. Одна панель (жёлтая) висит далеко над
телом, красные швы натянуты, вторая панель у бедра/талии; труба не облегает
аватар. `get_arrangement` после ручного gizmo по-прежнему показывает
Body_Front/Back_Center_2, orientation 180, offsets 50/75/50 и 0/75/50 —
gizmo-трансформ в arrangement metadata не отражён. Гипотеза: ручной поворот
спинки увёл панель с тела, а 60 шагов не дают посадку без близкого старта или
avatar fit. `Simulate -> true` не доказывает fit.

## Tool gate 2026-11-10

Build `aafcfac0323d`, `simulate({steps:60})`:
`{verified:true, steps:60, pattern_count:5, avatar_count:1, elapsed_ms:922}`.
Визуально garment без закрепления упал с торса: передняя панель у колена,
детали у запястья. Native call PASS, fit FAIL — нужен Line Pin/avatar attachment.

## Tool gate with avatar pins 2026-11-10

Build `b2f3fce822d6`, `TEE_FRONT/BACK` 400×300, верхние края прикреплены к
пользовательской грудной мере `CircumferenceMeasure_283316`, два боковых шва.
`simulate({steps:60})` → `{verified:true, steps:60, pattern_count:2,
avatar_count:1, elapsed_ms:1110}`. Визуально garment остался на торсе (не упал),
но ткань собрана/прозрачна; fit не принят. Это подтверждает, что Line Pin
удерживает garment во время simulation; качество посадки — отдельный gate.

## Что проверяет пользователь

- Деталь/труба не исчезла и не «взорвалась»; нет сильного нежелательного
  проникновения в аватар; UI остаётся отзывчивым.
- Видимый эффект simulation — отдельное visual evidence, не доказывается
  `Simulate -> bool`.

## Ограничения

- ≤1 simulation на пакет; без retry и без автоматического cleanup.
- Settings (gravity/time step/quality) не менять в этом gate.
- Mesh/position API readback не подключён; независимые mesh-наблюдения —
  следующий пакет.
- После probe нужен отдельный вывод: работает ли bounded simulation достаточно
  для текущей сцены, и стоит ли делать `simulate` tool.
