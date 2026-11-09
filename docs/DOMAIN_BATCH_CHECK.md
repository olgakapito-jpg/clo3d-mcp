# Bounded domain acceptance prep — A5

**B06 source/live19:** read-only `get_pattern_outline`. First own rectangle read
invalid_native_result; user one-shot native [] для own target5; причина
неизвестна. Различающий read-only опыт на двух существующих деталях (`"2"`,`"3"`)
тоже invalid_native_result → проблема не только в программно созданной детали;
это документированное ограничение, не открытый blocker набора. No
retry/move/delete/fallback; own fixture5 remains. `CLO_OUTLINE_CHECK.md`. Этот
runner сверяет inventory20 исходников, не добавляет outline scenario и не
разрешает native fallback.

**B07 lines:** tool20 `get_pattern_lines` реализован (one `GetPatternLineInfo`,
strict bounded JSON, list/count guards). Real: own fixture success,4lines0–3,
absolute API-mm frame; отдельный length-probe 4/4 с delta0.0. Кривые/failure/
frame после move/rotate не проверены; outline fallback запрещён.
`CLO_LINE_API_CONTRACT_REVIEW.md`; eval39cases/20tools.

**B05 local update:** source18 содержит get_pattern_fabric/assign_pattern_fabric,
live18 после fresh CLO restart. Direct real assignment API/readback PASS,UI
подтверждён;temporary appearance не оценена. B05C composition/index shift PASS.
`pattern-fabric-inspection` read-only runner реализован и real PASS:
5objects/4fabrics/2passes,32RPC/0mutations. Object bound(default4,max16),budget
12+4*max_objects включая initialize. dry-run `fabric-assignment-future` не имеет
missing tools в source, но остаётся BLOCKED: client execution recipe не реализован
для mutating assignment, а не для read-only inspection. Нельзя считать наличие wrappers разрешением
автозапуска mutating runner. Direct serial acceptance runbook:
`CLO_FABRIC_ASSIGNMENT_CHECK.md`.

**Обновление inventory-пакета:** расширенный profile16 содержит get_fabric_list
и get_avatars; scene mutations/import/assignment tools не добавлены. Новый
scenario `fabric-avatar-inventory` — read-only,12steps с initialize,0mutations.
Discover теперь проверяет avatar getters в export_api (не utility_api).
Исторические sections ниже с inventory14 сохранены как журнал прошлых runs.
Real старого prototype: empty paths; после user assets avatar count1/name получен,
pattern list count5. Пользователь исключил colorway из текущего scope: нужен
Fabric Object Browser. Colorway prototype (count0 при3видимых тканях) снят до
приёмки, его count-only probe больше не нужен. Новый read использует явный bool
keyword False и single-index name; в свежем CLO count4/names дважды совпали,
GUI/UI подтверждены пользователем — limited gate ACCEPTED. Дополнительный direct
MCP batch5cycles+final lists4/1/5/geometry5 PASS17.159с,mutations0; это не запуск
runner scenario. Нет fallback. Точные contracts/evidence/
следующий real шаг — `CLO_INVENTORY_CHECK.md`.

Цель: подготовить совместную приёмку **CLO2026.1.336**, а не заявить покрытие
всего API. Новый внешний клиент: `scripts/verify_domains.py`. Текущий baseline —
14 опубликованных tools из `CLO_MCP_TOOLS.md`. Ни runtime, ни launcher, ни
`verify_patterns.py`/`verify_transport.py` не изменяются. Принятый pattern load10
не повторяется. Реальная CLO-приёмка этого клиента **pending**.

## Режимы и зависимости

`dry-run` — stdlib-only, без MCP/native imports и без сети. Проверяет статические
dependencies, permission, плановые limits; показывает BLOCKED/missing tools/asset.
Существование optional asset проверяет только `stat` явно выбранного файла,
без чтения содержимого/сканирования/копирования. `completed` верхнего уровня
означает «план построен», не PASS заблокированных сценариев и не готовность CLO.

`discover` — explicit read-only MCP inventory + session/profile + один
`list_clo_api` и ровно два `describe_clo_api`: fabric count/name и avatar
count/name-list из текущих фиксированных modules. Getters из docstrings **не
вызываются**. Никаких новых modules/types, imports или execution обнаруженных
функций. `available=false` — наблюдение, не вызов/ошибка самого native getter.
Длинные/приватные docstrings в отчёт не попадают: только available/doc_chars.
Это bounded A0 evidence **наличия**, не полный official/runtime каталог.

`run` требует **одного явно выбранного whitelist scenario**:

- `scene-inspection`: свежий list → serial geometry каждого элемента → fresh
  list, names/index matching, стабильный список. Только reads; не требует
  `--allow-mutations`. Не больше `--max-objects` деталей (по умолчанию 4).
  Слишком большая сцена BLOCKED, не тихо truncated success. Пустая сцена
  допустима: отчёт явно показывает 0 geometry reads, не доказывает geometry API.
- `current-pattern-fixture`: только с `--allow-mutations`; fresh list/session →
  **один** create simple polygon с уникальным generated name → независимый
  geometry readback + fresh list. Проверяются count+1, имя/index, площадь7800мм²,
  position против mutation result, неизменность остальных index/name.
  Не гарантирует vertices/sewing/material relationships/3D или готовую одежду.
  Деталь **остаётся в сцене** даже при успехе. Нет delete/rename/copy/move,
  cleanup в finally, load cycles. Этот scenario — отдельно выбранная зависимость,
  никогда не запускается автоматически ради fabric/avatar сценария.
- `fabric-assignment-future`: всегда **BLOCKED**. Отсутствуют
  `get_fabric_list`, `get_fabric_for_pattern`, `assign_fabric_to_pattern`, A0/A1/A2
  contracts/integration и выбранные unique pattern/fabric targets. Нет native
  fallback. Следующий gate после реализации: fresh targets → одна assignment →
  independent assignment getter. Count/name ткани сами assignment не доказывают.
- `avatar-import-future`: всегда **BLOCKED**, в том числе при выбранном asset.
  Отсутствуют `get_avatars`, `import_avatar`, A0/A1/A3 contracts/integration и
  проверенная import/add/replace semantics. Optional `--avatar-asset` принимает
  существующий непустой `.avt`/`.avac` до256MiB **лишь для dependency prep**:
  формат не объявляется native-совместимым. Будущий run требует отдельного
  permission, независимого readback и визуальной проверки геометрии/позы.

**Нет inputs manifest произвольных команд, dynamic execution, browse/download,
exports или report files.** Сейчас stdout достаточно; автоматической записи
отчёта нет. Будущие export outputs разрешены только в явно выбранной подпапке
repo, вне inputs, без overwrite/удаления partial outputs по умолчанию. Это
уточнение задания заменяет старое A5 brief «вне repo». До file contracts и
дополнительного согласования никакого export tool/файловой записи не добавлено.

## Безопасность, валидация и bounds

Inventory не вызывает инструменты. Для выбранных tools проверяются наличие,
unique names, object input schema, exact properties/required fields и types.
Pagination inventory запрещена (unsupported, без обхода страниц), максимум64
tools. Profile capabilities и readiness проверяются совместно с inventory;
отсутствующие инструменты не выдумываются по native callable names.

Tool result требует structuredContent; isError/ok:false не подавляются. Внешний
status имеет отдельную schema, у queued tools требуется ok:true и текущий
command-specific stdlib contract из `pattern_contract.py`. Describe проверяет
exact module/functions correspondence и doc≤8192. Boolean вместо int, NaN,
invalid geometry/list/verified=false не открывают следующий gate.

Один serial outstanding call; session_id хранится только в памяти. До каждого
queued read/mutation — status с same-session, ready/connected/open,
not-quarantined, HTTP/executor ready, error absent, waiting=waiters=0,
active_id=active_state=null. Это **client-only TOCTOU guard, не атомарный
server-side expected_session**. Другой клиент/UI может изменить состояние между
проверками. Success ID не публикует job lookup/resume: run_id — только локальная
метка отчёта, не session token и не correlation/job ID.

Первый error/timeout/disconnect/schema mismatch/session change/busy/quarantine/
failed readback завершает run. Ноль retries, reconnect/resume, speculative
enqueue или scene cleanup. Даже command_error не доказывает отсутствие эффекта.
После mutation submission любой незавершённый gate помечает
`scene_may_have_changed=true`; `outcome_unknown`/unverified остаются unknown.
Нет cancel/Stop/rollback вызовов. Ctrl+C прекращает ожидание/отправку клиента,
**не native execution**; уже отправленная mutation может закончиться позже.

Используется JSON-response профиль текущего Streamable HTTP endpoint, только
POST `http://127.0.0.1:8765/mcp`. Official MCP1.26 result models/initialize
сохраняются. Convenience SDK streamable_http_client содержит автоматические
GET/SSE reconnect, поэтому маленький acceptance-only JSON клиент намеренно не
использует этот helper: нет GET/SSE/resumption, redirects, прокси env, transport
retries, DELETE-session или native IPC изменений. SSE/другой protocol profile —
unsupported, не повод fallback. Для запуска нужен установленный project env.

Defaults:32 runner steps, ≤1 mutation submission, ≤4 scene objects,
response≤256KiB **до JSON parse** в HTTP-клиенте (также проверяется полный MCP
result fake-клиента), report≤16KiB. Per-step15с, весь клиент90с. Initialize
считает одним runner step два последовательных protocol messages (request и
initialized notification); максимумHTTP POST≤steps+1. Верхние CLI limits:
64 steps/16 objects/65с step/300с total; response/report limits фиксированы CLI,
тестовый Limits допускает максимум1MiB/64KiB. Scene plan:7+2×objects steps
включая initialize; fixture11. Если лимит меньше плана — BLOCKED **до сети**.

Эти сроки ограничивают клиент, не native продолжительность/закрытие CLO API.
JSON response decoder до official result models отвергает duplicate object keys
на любой глубине, NaN/±Infinity и float overflow (`1e400`). Разбор неоднозначного
или non-finite ответа завершается failure без следующего вызова/retry.
Нет polling/sleeps/load. Большие response/report завершают проверку с failure,
не усечённым успехом. Report не печатает machine paths, scene names/geometries,
asset basename/content, docstrings, session IDs, tokens, server/native errors
или tracebacks. Только fixed labels, counts, local run_id и текущие whitelist
названия. Чужие inventory names не выводятся (лишь количество).

Статусы: `verified` — только конкретные readback invariants сценария;
`completed` — discovery/planning, не mutation acceptance; `unsupported` —
несовместимый API/profile; `blocked` — отсутствующая зависимость/permission/
ready scope; `failed` — ошибочная schema/readback/tool; `unknown` — неизвестный
исход/клиентский сбой. Exit0 verified/completed,2 blocked/unsupported,1
failed/unknown,130 Ctrl+C. Никакой status не означает «весь домен принят».

## Команды подготовки — безопасны сейчас

Из корня repo, **снаружи CLO**, PowerShell:

```powershell
uv run --frozen python scripts/verify_domains.py dry-run
uv run --frozen python scripts/verify_domains.py dry-run --scenario current-pattern-fixture --allow-mutations
uv run --frozen python scripts/verify_domains.py dry-run --scenario avatar-import-future
uv run --frozen --with pytest pytest -q tests/test_verify_domains.py
```

Dry-run показывает dependencies без открытия endpoint. Fake tests проверяют
каждый fault step/no further calls, guard failures/session change/busy,
unknown/post-dispatch timeout/Ctrl+C, missing tools/assets, schema/readback,
output/time/objects bounds, protocol JSON/no retries. Дополнительно ASGI integration
тест вызывает **настоящий installed official FastMCP `build_mcp(Service fake)`**
с lifespan/session manager: initialize → initialized notification202 → inventory14
→ info/status → безопасный not-ready error. Проверены JSON POST, HTTP session
header, negotiated protocol header и отсутствие GET/DELETE/replay. ASGITransport
исполняет приложение in-process: сокеты не создаются, реальный127.0.0.1:8765
не затрагивается; CLO/pipe/executor не запускаются. Это не real socket HTTP,
Windows pipe или CLO API acceptance. Общую regression suite запускает integration owner.

Фактически выполнено при подготовке (2026-11-09): focused команда выше —
**57 passed** после review-добавления real SDK ASGI handshake и strict JSON tests;
`dry-run` всех планов и отдельный fixture dry-run с permission —
exit0, network_calls=native_calls=0. До финального запуска исправлен один
ошибочный размер test bound (inventory сам превышал1KiB); production bound
не ослаблялся. Реальные discover/run, CLO restart/native calls и полная suite
этим A5 заданием не запускались.
Также metadata-only тест сверил generated inventory действующего
`build_mcp(pattern_package=True)` со всеми14 whitelist names и input schemas:
server/listener/pipe/native executor при этом не запускались.

## Следующий совместный real gate — только после перезапуска пользователем

1. Пользователь перезапускает CLO, выбирает disposable сцену≤4 деталей и запускает
   `plugin/clo3d_mcp_start.py` из CLO Script Editor. Закрыть Script Editor;
   дождаться ready. Один CLO instance, без параллельных clients/UI editing.
   Сам клиент не запускает/перезапускает launcher или CLO.
2. Отдельно согласовать **read-only** команды (каждая до90с client bound):

   ```powershell
   uv run --frozen python scripts/verify_domains.py discover
   uv run --frozen python scripts/verify_domains.py run --scenario scene-inspection
   ```

   Ожидание: discover completed, inventory14/profile match, bounded doc metadata;
   inspection verified и actual count/число geometry reads. Это **не** проверка
   CLO build по get_session_info: пользователь вручную подтверждает2026.1.336.
3. Только при отдельном разрешении на одну новую деталь:

   ```powershell
   uv run --frozen python scripts/verify_domains.py run --scenario current-pattern-fixture --allow-mutations
   ```

   До запуска оставить место в max-objects (по умолчанию исходно≤3).
   Ожидание: одна четырёхугольная деталь, +1 count, verified независимого readback,
   `fixture_left_in_scene=true`. Пользователь подтверждает отзывчивость UI.
   Не удалять автоматически и не запускать future scenarios.
4. Любой mismatch/error/диалог/hang/unknown — STOP. Ctrl+C останавливает клиент,
   но native работа может идти дальше. Явная остановка bridge пользователем:
   `plugin/clo3d_mcp_stop.py` в CLO, когда UI способен обработать script; это не
   гарантия прерывания заблокированного native API. Не kill по имени/порту.
5. После unknown — не повторять старый run. Позже отдельно согласовать один
   read-only status snapshot и bounded list/geometry, когда executor свободен.
   Похожая текущая сцена не доказывает историю исполнения. Возобновления нет.

Оставшиеся blockers: A0 provenance/signatures всего API; A1 atomic fencing
не реализован; fabric/avatar tools/adapters отсутствуют; assets/targets/permissions
не выбраны; полные topology/sewing/simulation/export gates не входят сюда.
Последующая интеграция domains требует отдельного изменения whitelist **и**
contracts/readback/fake-fault tests — одно появление tool name не включает run.

## Первый совместный real прогон — 2026-11-09

Пользователь запустил CLO и новую панель, разрешил MCP tests. Выполнены только
reads, без mutations, загрузки assets, рестарта или остановки сервера:

1. `uv run --frozen python scripts/verify_domains.py discover`: inventory14,
   начальные info/status и `list_clo_api` verified. Counts callables:
   pattern217/export92/fabric135/import39/utility366. Следующий status завершил
   run `failed/invalid_status_schema`, rpc_steps=6, mutations=0. Describe calls
   не выполнены; discovery **не принят**. Counts — presence, не native acceptance.
2. Отдельная bounded read-only сверка (initialize + один transport_status):
   schema valid, ready/connected/http_serving/executor_verified=true,
   closed/quarantined=false, waiting=waiters=0, active_id/state=null, error=null.
   Этот snapshot не восстановил исходный payload, вызвавший schema failure.
3. По source и deterministic JobQueue tests выявлен пропуск client schema:
   RESULT публикует outcome до отдельного READY; active_state законно бывает
   succeeded/failed при ещё занятом active_id. Schema принимает эти два состояния,
   но guard по-прежнему запрещает продолжение при active_id/state или not-ready.
   Runtime/server/transport не изменены. Это объяснение совместимо с первым
   failure, но исходный status payload не сохранён, точное состояние неизвестно.
4. Отдельный `run --scenario scene-inspection`: inventory/info/initial guard и
   get_pattern_list verified, pattern_count=0. Следующий guard остановил run
   `blocked/unexpected_queue_work`, rpc_steps=6, mutations=0. Geometry reads=0;
   финальный fresh list не выполнен. Scene-inspection **не принят целиком**.

`Service.status().ready` означает готовность сервиса, не свободный queue slot:
оно может быть true до освобождения active_id по READY. Существующий клиент
немедленно проверяет status после результата и может поймать этот промежуток.
Не ослаблять idle guard, не resend native call и не auto-resume старый run.
Следующий инженерный gate — отдельно спроектировать bounded observation
завершения точно своего job/READY без маскировки чужой работы, затем fake tests
и новый согласованный read-only real run. До этого multi-step acceptance blocked.

Локальная проверка исправления schema: focused verify_domains/jobs/async_jobs
**93 passed**, full **700 passed, 1 skipped**, 43.92 с. Skip — real symlink asset
helper unavailable, unrelated. Панель: запуск пользователем подтверждён, но
hide/reopen/Stop→Start/new session/UI responsiveness отдельно ещё не приняты.
Standalone metadata/type probe B01 не запускался, новых bindings не подтверждено.

## Исправление RESULT → READY — реализация и локальная проверка

Внешний `Service.call` использует `AsyncJobQueue.call(release_timeout=2.0)`:
после successful outcome ждёт release event точного job_id. `on_ready` освобождает
observer только этого job; следующий чужой job/непустая очередь не маскируются
ожиданием global idle. Нет status polling, sleep, resend, нового MCP tool или IPC.
Status остаётся responsive. Timeout/disconnect/close/cancellation не меняют
native outcome и не снимают execution slot. Caller cancellation удаляет observer,
не повторяет job. Error codes/semantics — `CLO_MCP_TOOLS.md`.

До нового real run нужен **ручной Stop → Start** внешнего сервера через панель,
поскольку работающий MCP использует старый код. Embedded executor не менялся,
для этого исправления полный CLO restart не требуется. Критерий: discover
completed и отдельный scene-inspection verified, без фоновой работы/UI editing.
При пустой сцене geometry по-прежнему не проверяется. Real success пока не заявлен.

Локальная проверка после реализации release wait: полная suite **708 passed,
1 skipped**, 42.90 с; skip прежний real symlink unavailable. Deterministic tests
покрывают delayed READY, уже полученный READY, следующий чужой job, timeout,
disconnect, close, cancellation и immediate native error. Service test проверяет
responsive status и неизменный success result. Source/coverage regeneration и
`--check` PASS; all-source audit191 PASS. Новых real calls после изменения нет.

## Новый совместный real прогон после Stop → Start — 2026-11-09

После commit `842c1e8` пользователь подтвердил остановку и новый запуск внешнего
MCP через `plugin/clo3d_mcp_panel.py`. Внешний вид панели не менялся; embedded
executor для этого исправления не обновлялся. Выполнены два новых самостоятельных
read-only сценария, не resume прежних failed/blocked runs:

1. `uv run --frozen python scripts/verify_domains.py discover` — exit0,
   `completed/discovery_is_not_native_acceptance`, run_id
   `811b35ca75934b10a9c57528a1d0dc7f`, 9 RPC steps, 0 mutations.
   Inventory14, без missing/extra tools; info/status/list и два describe verified.
   Callable counts pattern217/export92/fabric135/import39/utility366.
   `fabric_api.GetFabricCount/GetFabricName` available=true; конкретные имена
   `utility_api.GetAvatarCount/GetAvatarNameList` available=false. Это metadata,
   не вызовы fabric/avatar getters и не вывод об отсутствии аватара в сцене.
2. `uv run --frozen python scripts/verify_domains.py run --scenario scene-inspection`
   — exit0, `verified/bounded_scene_observations_only`, run_id
   `a773d122384c4659b22e7486728aab68`, 7 RPC steps, 0 mutations.
   Два стабильных списка и промежуточные guards verified, pattern_count=0,
   geometry_objects_checked=0. Геометрия непустой сцены **не проверена**.

Короткий real gate исправления RESULT → READY пройден для CLO2026.1.336:
прежние schema/idle-guard failures в этих двух новых runs не повторились.
Это не stress, не проверка всех timing/fault cases и не приёмка новых доменов.
Assets не читались/не загружались, сцена не менялась. Полная приёмка панели
(hide/reopen, responsiveness, clean exit и новая session identity) отдельно
не доказана. Следующий gate — один ручной B01 static metadata probe
`diagnostics/clo3d_mcp_api_probe.py`: pattern_api / type=None / cursor=0.

### Прямой MCP после включения пользователем — 2026-11-09

Пользователь включил MCP в клиенте и разрешил самостоятельные проверки.
Каталог прямых tools содержит те же14 операций. `get_session_info` подтвердил
ready/connected, idle, error=None, без quarantine. Затем последовательные
`list_clo_api` → `transport_status` → `describe_clo_api` дали дополнительное
metadata evidence: **`export_api.GetAvatarCount`** доступен с doc
`GetAvatarCount() -> int`, **`export_api.GetAvatarNameList`** — с doc
`GetAvatarNameList() -> List[str]`. Сами getters не вызывались, count/имена
аватаров не прочитаны. Предыдущее отсутствие этих имён в utility_api не относится
к export_api и не является отсутствием API вообще. Mutations=0.

Включение MCP не добавило B01 probe: list/describe ограничены пятью modules;
ApiTypes/gui_api, class own-member inspection и запуск Python scripts не входят
в опубликованный контракт. Для полного B01 по-прежнему нужен ручной standalone
probe либо отдельно спроектированное узкое расширение; generic exec/import
как обход не применяется. Автозапуск/перезапуск CLO worker этим прогоном не проверен.
