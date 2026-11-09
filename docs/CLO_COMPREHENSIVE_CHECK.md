# Комплексная приёмка CLO 2026.1.336: порядок и границы

Подготовка A0 и инструментов проверки разрешена пользователем 2026-11-09.
**Ни каталог, ни dry-run не означают, что сотни native методов уже реализованы
или приняты.** Реальная проверка выполняется совместно короткими пакетами,
после перезапуска CLO пользователем. Автономных real-CLO прогонов на этом этапе нет.

## Текущий подпакет B03/B04: read-only inventories

Расширенный profile содержит16 tools: исходные14 и get_fabric_list/get_avatars.
Реально прочитаны один загруженный аватар (count/name) и5 деталей кроя;
после чтений same-session ready/idle,error=null. Assignments/pose/geometry этим
подпакетом не проверены, пользовательская сцена не менялась агентом.

**Уточнение scope:** пользователь исключил colorway, нужен Fabric Object Browser.
Прежний prototype (count0 при3видимых тканях) снят до приёмки; причина0 не доказана.
Новый контракт: bool count keyword False + single-index name, без colorway_index.
В свежем CLO через `_start` два одинаковых native списка count4/names успешно
прочитаны, final same-session ready/idle,error=null; пользователь подтвердил
4ткани GUI/нормальный UI/нет замеченных сбоев: ограниченный gate ACCEPTED.
Дополнительный активный read-only пакет PASS:5cycles+final inventories4/1/5,
geometry5,23native-tool reads/24status,17.159с,p95=758мс,max766мс,mutations0.
Прежний запуск после только Stop→Start дал unknown и завершение MCP; причина
не доказана. Stop→Start не reload embedded sys.modules, прежняя инструкция
исправлена. Панель необязательна, пользователь предпочитает `_start`/`_stop`.
Count-comparison probe больше не требуется. Критерии/остановка:
`CLO_INVENTORY_CHECK.md`. Это не повтор принятых P0–P3/load gates.

Локально новый Object Browser контракт: focused228PASS; full780passed/1skip
(real symlink unavailable). Старые232/784 относятся к colorway prototype.
Source audit отдельно BLOCKED посторонним `opencode.json.openchamber.backup`;
файл и config не менять ради прохождения guard. Исторические инструкции ниже
с14 tools описывают исходный сеанс, не актуальный полный inventory.

## Что именно проверяем раздельно

Следующий B05a/B05b локально добавляет get_pattern_fabric/assign_pattern_fabric
(source/live profile18). После fresh restart real getter5mappings/2passes и
setter на своей детали0→1→3 PASS; independent readbacks/preservation5 и planned
own delete/final checks PASS. Read-only mapping runner PASS. UI подтверждён;
temporary appearance не оценена. B05C copy/material/rename/move/lower-delete
index shift/fresh-index assignment PASS;final originals5preserved.
Preflight names/current mapping и post-setter mappings
всех деталей/target geometry; option1 фиксирован, не colorway management.
Fresh-process blocker снят; embedded модули не hot-reload. Критерии, лимиты,
tests и preservation scope:
`CLO_FABRIC_ASSIGNMENT_CHECK.md`. Это не автоматический assignment существующему
пользовательскому крою и не повод менять протокол/перезапускать процесс агентом.

1. **Полнота спецификации:** source/version/hash, все обнаруженные объявления,
   перегрузки, типы и интерфейсы учтены; никакой потерянный метод не скрыт
   отсутствием у донора. Документационные повторы не увеличивают coverage.
2. **Mapping:** donor tool → handler/helper → native reference, local legacy →
   current tool. AST reference — кандидат связи, не доказательство semantics.
3. **Binding:** callable/docstring/class metadata в целевой сборке. Наличие
   типа не доказывает его constructibility, наличие метода — его безопасность.
4. **Implementation:** validators/adapter/registrar/profile/result validation
   и согласованные schemas. Не всякое упоминание getter в preflight есть полный
   реализованный native overload. Legacy не включается в новый executor.
5. **Локальные tests:** synthetic API, fault injection, HTTP, Windows pipes.
   Fake fixtures не запускают native CLO и не закрывают real gates.
6. **Real acceptance:** конкретная операция/перегрузка/fixture/readback/визуальное
   подтверждение. Нельзя распространить один successful call на весь домен.

## До перезапуска: offline подготовка

- Ознакомиться с `api/CLO_API_CATALOG.md` и незакрытыми gates в
  `api/review_gates.json`; никаких «вызвать все найденные functions».
- Выбрать пакет из `CLO_ACCEPTANCE_PACKAGES.md`. Доступность tools проверяется
  и по опубликованному inventory, и по executor capabilities; это разные списки.
- Проверить план через `scripts/verify_domains.py` в offline dry-run. Недоступные
  команды должны давать BLOCKED, не подменяться generic exec/legacy calls.
- Assets только на чтение. Скрипт `scripts/prepare_acceptance_assets.py`
  инвентаризирует metadata с лимитами, не загружает и не копирует native files.
  Отбор по имени/расширению не доказывает содержимое или совместимость.
- Outputs только в выбранную подпапку проекта `acceptance-output/` вне inputs;
  она gitignored. Папку создавать только для явного экспорта/отчёта; никаких
  request/response/heartbeat/queue/discovery файлов в transport.
- Не обещать новые domains после одного перезапуска: если implementation нет,
  пакет остаётся BLOCKED до отдельной реализации и локальной проверки.

## Первый совместный сеанс после возвращения пользователя

1. Пользователь сохраняет нужную работу и открывает свежий CLO **2026.1.336**.
   Агент не закрывает приложение и не завершает процессы по имени/порту.
2. В Script Editor запускается `plugin/clo3d_mcp_start.py`, редактор закрывается.
   Если CLO не задаёт `__file__`, локально указать ROOT по действующей инструкции
   README; машинный путь не включать в коммит. Не hot-reload retained callbacks.
3. Проверить новый session_id, readiness/error, пустой active/waiting и фактический
   inventory. Пять текущих диагностических + девять pattern tools не означают
   availability fabrics/avatar/sewing/simulation.
4. B01: отдельно metadata probe по `CLO_API_PROBE_CHECK.md`, один выбранный
   module/page за раз. Это metadata, не native execution обнаруженных методов.
   Сохранённый stdout — evidence, не IPC. Не перезапускать принятый P0 gate.
5. B02: bounded scene inspection через текущие tools, без обязательного ping
   перед каждым getter и без повторения load1000/load10.
6. Выбрать **один** следующий реализованный пакет. Перед effect: исходная сцена,
   input asset, permissions, ожидаемый readback и visual criteria проговорены.
7. После пакета остановиться и сверить observed result с критериями. Обновить
   конкретные coverage/evidence rows; только затем переходить к следующему.

Подробные параметры запуска клиента и probe — в `DOMAIN_BATCH_CHECK.md` и
`CLO_API_PROBE_CHECK.md`; это канонические инструкции, не альтернативный runner.

## Общие лимиты и остановка

- Один outstanding mutation, каждое зависимое изменение только после result
  validation и обязательного независимого readback. Не pre-enqueue batches.
- Status/session check клиента не atomic pinning. Текущий server не принимает
  expected_session в mutation args; после подозрения на restart остановиться.
- Ошибка, unknown, timeout, disconnect, invalid schema, mismatch, неожиданное
  изменение сцены/session или dialog: **STOP последующим mutations**.
- Никакого auto retry, overload fallback, rollback или scene cleanup в finally.
  Плановое удаление своих объектов — отдельные успешные шаги с fresh guards,
  не способ скрыть ошибку. Partial output files после ошибки не удалять.
- Ctrl+C останавливает отправку/ожидание клиента; он не отменяет уже вошедший
  в native CLO вызов. Client deadline не гарантирует ограничение native времени.
- Если UI/вызов занят, status доступен снаружи; getters/ping ждут того же FIFO
  и не прерывают native operation. Не flood polling и не повторять команду.
- Обычный stop bridge: внутри того же CLO запустить `plugin/clo3d_mcp_stop.py`
  и закрыть редактор; ожидаются stopped/exit_code=0/cleanup_pending=False.
  Это lifecycle shutdown, не средство гарантированно прервать текущий native call.

## Как фиксируем итог пакета

- **VERIFIED:** выполнены ровно перечисленные invariants и независимые критерии;
  записан scope, не общее «API работает».
- **COMPLETED_UNVERIFIED:** native завершился, но эффект недостаточно доказан;
  нельзя автоматически использовать это как пройденный dangerous dependency.
- **BLOCKED:** отсутствует tool/binding/type/asset/permission/readback/контракт.
  Не PASS и не скрытый skip.
- **FAILED:** известный отказ или mismatch; текущая сцена может быть изменена.
- **UNKNOWN:** вызов мог выполниться; отдельная bounded read-only сверка,
  когда executor доступен, без resume старого плана.

Каждый отчёт содержит: package ID, target build, session continuity (без токенов),
точную command sequence, initial fixture, expected/observed, время клиента и
executor отдельно, error/uncertainty, user visual result, следующий gate.
Секреты и абсолютные private paths в portable reports не включать.

## Что не включать в автоматический комплексный прогон

- Принятые P0–P3, pattern load10/read1000 без причины регрессии.
- Отдельный 30-минутный soak, от которого пользователь отказался.
- Forced exit/crash CLO, global settings, REST/auth/cloud uploads, GUI/widget/
  plugin/script registration, произвольный filesystem scan или arbitrary exec.
- Dialog-only export с обходом через UI automation.
- Проверку всех setters по списку или hundreds of calls в одном UI callback.

Эти группы остаются видимыми в coverage/gates, но требуют отдельного scope и
согласования. Полнота каталога не расширяет полномочия инструментов.

## Итог локальной подготовки — 2026-11-09

После финального review coverage пересобран. Validator отвергает ложное exact-
overload evidence и binding без evidence; historical runtime document закреплён
SHA-256. Отдельные negative tests проверяют изменение historical evidence,
небезопасные provenance paths и неверный hash scope до чтения файла.

Выполнено локально:

- `uv run --frozen python scripts/build_api_coverage.py` и повторный `--check`:
  PASS, 1134 declarations; per-overload implementation/acceptance не повышены.
- `uv run --frozen python scripts/build_official_api_catalog.py --check` и
  `uv run --frozen python scripts/build_api_source_mappings.py --check`: PASS,
  offline snapshots согласованы; native CLO modules не импортировались.
- Focused tests восьми файлов подготовки (coverage, official, mappings, audit,
  assets, probe, client, workflow eval): **374 passed, 1 skipped**.
- `uv run --frozen --with pytest pytest -q -rs`: **680 passed, 1 skipped**,
  42.51 с. Выполнены существующие isolated Windows pipe/process tests, не CLO.
- Единственный skip: `tests/test_prepare_acceptance_assets.py`, создание
  настоящего symlink недоступно; synthetic reparse contracts прошли.
- `uv run --frozen python scripts/evaluate_tool_workflows.py --check --self-test`:
  PASS, 14 tools / 30 cases, 2 valid accepted / 6 invalid rejected. Это не LLM eval.
- `uv run --frozen python scripts/check_acceptance_preparation.py --all-source`:
  PASS, source/untracked metadata/privacy/size/link/inventory audit.
- `git diff --check`: PASS; только стандартные предупреждения LF → CRLF.

Локальная подготовка закрыта в указанном scope. Production runtime/dependencies
не изменены, CLO и действующий MCP не вызывались, assets не загружались.
Коммитов/push нет. Следующий gate — совместные B00/readiness, B01 metadata/type
probe и B02 scene reads после перезапуска пользователем; новые домены остаются
BLOCKED до контрактов, реализации и отдельной real acceptance.

## Последующие изменения и совместная real проверка — 2026-11-09

Приведённый выше итог680/skip1 относится к подготовке A0. После неё по запросу
пользователя сохранены локальные commits `7164043` (каталог/подготовка),
`edb7fad` (Win32-панель/предложение контроллера), `842c1e8` (bounded correlated
RESULT → READY). Push не выполнялся. Последняя полная suite исправления:
**708 passed, 1 skipped**, 42.90 с; skip — real symlink unavailable.

После подтверждённого пользователем Stop → Start через панель два новых real
read-only runs прошли: discovery completed (9 RPC steps, inventory14) и
scene-inspection verified (7 RPC steps, два стабильных списка, count0).
В обоих 0 mutations; geometry reads0, assets не загружались. Точные run IDs,
команды, metadata findings и пределы доказательства — `DOMAIN_BATCH_CHECK.md`.
Прежний RESULT → READY blocker закрыт только в scope короткого real gate,
не stress/всех faults. Пустая сцена не закрывает geometry acceptance B02.

Следующий совместный шаг B01 — один запуск `plugin/clo3d_mcp_api_probe.py`
в CLO с pattern_api / type=None / cursor=0, затем просмотр JSON. Gate ещё pending;
types/options/overloads/native semantics и новые домены не считаются принятыми.
Полная приёмка панели остаётся частичной; macOS GUI и внешний supervisor — только
предложение `CLO_MCP_CONTROLLER_PLAN.md`, не реализованная поддержка.

Позднее пользователь прислал первую B01 страницу: pattern_api/type=None/cursor0,
12 builtin callables, docstrings присутствуют, next_cursor17/page_limit.
Metadata-only gate подтверждён для этой страницы; native calls и types/options
не приняты. Подробности — `CLO_API_PROBE_CHECK.md`. Следующий шаг — ApiTypes
module-only/cursor0 без import/constructor; not_loaded не означает absent.

Последующее B01 обновление: пользователь явно согласовал import ApiTypes перед
probe; исправленный entrypoint import+probe в одном Run real проверен. Получены
14 module-only страниц ApiTypes вплоть до cursor162/next_cursor=null/truncatedfalse:
158 filtered entries (73 class,85 opaque). Это конец filtered traversal, не
atomic/full native-type acceptance. Constructors/fields/defaults/enum values
не проверены. Последующий автоматический batch получен в пользовательском
result.json: complete=true,103 страницы,73 класса,736 entries. У73 классов
совпали все550 разрешённых фильтром documented member names; ExportDxfOption
11/11 property names найден. CleanedPathResult исключён PATH-фильтром;
CLO_API_UNIT/HttpMethodType/RenderColorwayType не найдены в own module inventory
(кандидаты различия экспонирования, не глобальная missing-functionality оценка).
Повторный общий probe не нужен. Constructors/defaults/export execution остаются
pending. Подробности и SHA256 evidence — `CLO_API_PROBE_CHECK.md`.
