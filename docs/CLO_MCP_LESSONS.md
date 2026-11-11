# Уроки в CLO MCP — каталог и статус

2026-11-11. Это **server-local** lesson runner, не native API и не composite
scene tool. Уроки помогают пройти сценарий по шагам, но не выполняют за клиента
scene mutations: каждый шаг делает сам агент/пользователь существующими tools.
`lesson` только читает четыре bounded snapshot-а и двигает прогресс.

## Контракт

Tool: `lesson(action, lesson_id?)`.

- `list` — каталог без состояния и без CLO reads.
- `start` — начать/перезапустить урок; `lesson_id` обязателен.
- `state` — текущий шаг, прогресс, последняя проверка.
- `check` — 4 read-only native reads (`get_pattern_list`,
  `get_seamline_pairs`, `get_arrangement`, `get_avatars`), проверка текущего
  шага; pass двигает на один шаг, fail оставляет шаг без cleanup/retry.
- `reset` — очистить прогресс.

State живёт в памяти MCP service (одна CLO-сессия) и теряется при restart.
Файлов, IPC, очередей и native mutations нет. `lesson_check_unavailable`
означает, что одно из четырёх чтений не удалось: STOP, не повторять и не
запускать scene mutations «для проверки».

## Каталог

### `tee_copy_place` — копия кроя без швов и посадка

Сценарий: импортированная футболка, 5 деталей, 16 seam-групп, 1 аватар.

1. `audit` — 5 деталей, arrangement у всех, аватар, существующие швы.
2. `copy` — 5 копий `LESSON_*`; ожидается 10 деталей и отсутствие общих
   seam-групп с оригиналами. У рукавов/воротника копия может получить одну
   **внутреннюю** группу — это допустимо; общая группа с оригиналом — STOP.
3. `remove_originals` — удалить 5 оригиналов по одному с fresh list; остаются
   только `LESSON_*`, копии не сшиты между собой.
4. `place` — проверить унаследованные arrangement points; при смене —
   `get_arrangement_list` → `set_arrangement`. `orientation`/`position` не
   использовать для перемещения; simulation без швов не запускать.

Ограничение: копии рукавов/воротника могут нести одну внутреннюю seam-группу
(наблюдено live). Урок не утверждает «абсолютно без швов»; для строго чистых
копий нужен DXF/JSON route.

### `two_panel_tube` — две панели, два боковых шва

1. `panels` — `LESSON_TUBE_A/B` 120×80 мм; линии читаются, панели не сшиты.
2. `left_seam` — один `add_seamline_pair`, seam_count +1 от baseline.
3. `right_seam` — второй шов, seam_count +2; перекрёст на 3D — STOP.
4. `review` — `simulate(60)` и скриншот; ровно два новых шва, visual-only.

Урок использует первый успешный `check` как baseline `seam_count`; шаги надо
проходить последовательно. Он не заменяет `clo-sewing`/`clo-seamlines` и не
доказывает посадку.

## Проверка

- Local: `tests/test_lessons.py` — state machine, pass/fail, baseline,
  malformed snapshot, read failure, reset.
- Offline inventory: `scripts/evaluate_tool_workflows.py --check --self-test`
  (45 tools, current45).
- Real CLO gate: **pending**. Нужен Stop → Start, затем `lesson` list/start и
  один `check` на текущей сцене; проверить, что `server_build ==
  executor_build`, а `check` не меняет `pattern_count`/`seam_count`.
