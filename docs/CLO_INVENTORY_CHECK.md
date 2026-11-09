# B03/B04: read-only fabrics/avatar inventories

Target: **CLO2026.1.336**. Два новых tools в расширенном pattern profile
(16 вместо14); transport/FIFO/launcher архитектура не меняется. Native calls
только в существующем проверенном UI executor. Нет импорта assets, assignments,
сети, файловой записи, generic execution, native fallback или retries.

## Контракт и source traceability

`get_fabric_list({})` → `{ok:true,fabric_count,fabrics:[{index,name}]}`.
По уточнению пользователя нужен **Fabric из Object Browser проекта**, не colorway.
Индексы — zero-based Object Browser, лимит fabrics0–256. Count явно вызывается
с keyword `_bCurrentColorway=False`: bool overload без фильтра по текущему
colorway; keyword подтверждён live docstring целевой сборки. Names — single-index
overload того же Object Browser. Нет зависимости от export_api/current colorway.
Проверяются3 count reads и2 прохода names (максимум515 native calls).
Это bounded synchronous работа, не atomic snapshot
и не гарантия длительности native вызова. При слишком большой сцене отказ до
чтения имён. Возможны ABA/одинаковые имена у разных объектов.

Official declarations, сохранённые в `docs/api/official/`:

- `fabric_api.GetFabricCount#3df4ca91f263501d`: `(bool _bCurrentColorway) -> int`,
  False отключает ограничение текущим colorway; return docs: Object Browser project.
- `fabric_api.GetFabricName#26161b79bcf11b66`: `(int fabricIndex) -> str`,
  parameter docs явно указывают Object Browser index.
- Нет default/int/colorway overload fallback. При отказе keyword STOP, не пробовать
  positional bool/int. Старый colorway-контракт снят до приёмки, не parallel tool.

`get_avatars({})` → `{ok:true,avatar_count,avatars:[{index,name}]}`.
Лимит0–64; индексы zero-based в порядке GetAvatarNameList, не persistent IDs.
3 count reads и2 name-list reads (5 native calls). Official:

- `export_api.GetAvatarCount#32458f44fb66cd8c`: `() -> int`.
- `export_api.GetAvatarNameList#b96822598f0861db`: `() -> list[str]`.

Все params строго `{}` (extra keys invalid до enqueue); pagination/targets/options
отсутствуют. Имена exact str0–256 chars, без control chars<32/surrogates.
Пустые/duplicate names сохраняются: это не unique identity guards.
Результаты проходят общий validator до queue cache, count/index не принимают bool.
Никаких geometry/material properties/pose/assignment statements по names.

Ошибки: `api_unavailable` — preflight callable отсутствует; `inventory_limit` —
count выше bound; `invalid_native_result` — неверный тип/имя/index/count-list
shape; `inventory_changed` — смена count/names между reads; `command_error`
— native exception, без exception text. Общие queue/unknown/release ошибки сохраняются.
При любой ошибке STOP; не использовать partial list, не retry/fallback/import/
переключать colorway для восстановления. После review возможна новая отдельно
согласованная read-only диагностика. Client timeout не останавливает native call.

## Выбор и композиция

- Valid: «Покажи Fabric в Object Browser проекта» → info/guard → get_fabric_list `{}`.
- Valid: «Какие аватары загружены?» → info/guard → get_avatars `{}`.
- Invalid/no-call: `{"limit":10}`, `{"colorway_index":0}`, `{"avatar_index":0}`:
  exact-key validator отказывает без API call. Нет такой pagination/selection.
- Anti-selection: «Назначь ткань детали» — эти reads не assignment; соответствующий
  setter/getter ещё не реализован. Список не проверяет применение ткани к крою.
- Cross-domain: info/guard → get_pattern_list → guard → get_fabric_list → guard →
  get_avatars. Получены отдельные observations, не связи pattern↔fabric/avatar.
  При первом error/schema/session mismatch следующие calls не выполняются.
- Synthetic eval cases `fabric_inventory`/`avatar_inventory`, fake native faults
  на каждом read и executor/cache/SDK metadata tests — `tests/test_inventory_api.py`.

## Bounded внешний сценарий

`scripts/verify_domains.py run --scenario fabric-avatar-inventory`:
initialize → inventory → info/idle guard → fabric → avatar → повтор fabric/avatar
с guards → final guard.12 runner steps с initialize,0mutations,90с client bound,
15с/step. Вывод только counts/flags, без имён/scene paths/tokens. Nonempty flags
обязательны для утверждения nonempty acceptance; empty success их не заменяет.
Default generic runner сохраняет shared no-retry/stop policy. Пакет не требует
asset path и не импортирует ткань/аватар автоматически. Offline prep:

```powershell
uv run --frozen python scripts/verify_domains.py dry-run --scenario fabric-avatar-inventory
uv run --frozen --with pytest pytest -q tests/test_inventory_api.py tests/test_verify_domains.py
```

## Historical real evidence — снятый colorway prototype, 2026-11-09

Результаты ниже относятся к прежнему контракту, НЕ к новому Object Browser read.
По уточнению пользователя colorway сейчас не нужен; расследование старого count
не является prerequisite нового подпакета. Причина старого0 не установлена.

Пользователь подключил обновлённый MCP с16 tools. Проверены same-session ready,
empty queue/error=null; describe подтвердил count/name overloads fabric_api и
GetCurrentColorwayIndex/GetAvatarCount/GetAvatarNameList в export_api.

Первый serial read-only gate: fabric colorway0/count0/list[],avatar count0/list[].
После обоих final status ready/idle,error=null. Это empty-path evidence;
GetFabricName при0 не вызывался. Сценовых изменений не выполнялось.

После добавления пользователем тканей get_fabric_list снова вернул0 для
colorway0. Пользователь подтвердил ткани в Object Browser; скриншот показывает
3 строки Fabric. Поэтому **nonempty fabric acceptance FAILED/unresolved**:
успешный JSON не совпал с пользовательским наблюдением. Не считать0 доказательством
отсутствия тканей. Причина (namespace/binding overload/context) не установлена;
не вводить автоматический fallback. Пользователь затем добавил крой, аватар и
назначил ткань нескольким деталям; assignments этим пакетом не читаются.

Отдельный read после добавления аватара вернул count1, index0 и непустое имя.
Это nonempty avatar count/list path; имя не записывается в source docs. Поза,
геометрия/visual соответствие, Unicode/duplicates и все faults real не проверены.
UI responsiveness отдельно пользователем не подтверждена.

Свежий get_pattern_list после user fixture вернул5 деталей. Final status после
avatar/pattern reads: same-session,ready/idle,error=null. Геометрия и assignments
не читались; пользовательские изменения не отменялись.

Локальная проверка пакета: focused inventory/runner/evals232PASS; full
`uv run --frozen --with pytest pytest -q -rs` — **784 passed,1 skipped**,43.47с.
Skip: реальный symlink недоступен, fake reparse contracts пройдены. Проверены
native faults на каждом шаге/no retry, bounds/types/extra keys, empty/duplicates,
changed counts/names/colorway старого prototype, queue/executor/cache, official SDK metadata/raw
validation, offline выбор и runner stop-on-fault. Dry-run нового scenario completed,
network_calls=native_calls=0. Mapping rebuild/check и diff-check PASS.
Full source audit не прошёл только из-за постороннего untracked файла
`opencode.json.openchamber.backup` (неподдерживаемое расширение); backup/config
не изменялись и не удалялись. Это не native acceptance и не повод ослаблять guard.

### Object Browser inventory: ограниченный real gate ACCEPTED

Локальная проверка нового Object Browser контракта: focused inventory/runner/
evals **228 passed**; full suite **780 passed,1 skipped**,49.13с. Skip прежний:
real symlink unavailable. Количество уменьшилось из-за снятия5 parametrized
colorway validation cases и2 colorway-change cases; добавлены3 Object Browser
tests: export-independent/keyword-False route, missing-name+keyword-error
no-fallback, bound256/515reads. Fault injection по всем оставшимся native reads
сохранён; raw extra keys и старый result с colorway_index запрещены. Live metadata
semantic assertions проверяют Object Browser и отсутствие colorway_index.
Mappings/coverage rebuild+check, dry-run и diff-check PASS. Source audit199files
по-прежнему blocked только посторонним backup/config extension, guard не ослаблен.

Colorway count-comparison `diagnostics/clo3d_mcp_fabric_probe.py` больше не требуется;
не запускать ради текущего scope. Файл сохранён как историческая диагностика.
Live describe повторно подтвердил bool keyword `_bCurrentColorway` и single-index
name overload. Metadata само по себе не acceptance; native evidence ниже.

Предыдущая инструкция «достаточно Stop→Start» была неверной: новый внешний worker
не перезагружает sys.modules внутри CLO. После пользовательского Stop→Start
новая сессия была ready/idle, но единственное чтение вернуло outcome_unknown;
внешний status затем ECONNREFUSED, MCP process отсутствовал, CLO отвечал Windows.
Не было retry/cleanup. Смешение старого embedded и нового external контрактов —
гипотеза, не доказанная причина: console/error evidence не получено.

Для изменённого embedded кода нужен свежий процесс CLO после сохранения нужной
работы пользователем; не hot-reload retained callbacks. Запуск/остановка через
`plugin/clo3d_mcp_start.py` / `plugin/clo3d_mcp_stop.py`, панель необязательна
и пользователю неудобна. Агент не перезапускает CLO/worker самостоятельно.

Пользователь затем запустил `_start`. Info подтвердил новый CLO PID и новую
ready/idle сессию. Serial sequence: info → get_fabric_list → status → независимый
get_fabric_list → final status. Оба результата **ok=true,count4**, одинаковые
indices0–3 и exact names; colorway_index отсутствует. Это успешное native чтение
нового контракта с keyword False и single-index names. Fixture теперь4, не прежние3.
Все status same-session ready/idle,waiting=waiters=0,active=null,error=null.
Scene mutations0. Имена полностью выведены в чат, в source docs не копируются.

Пользователь подтвердил соответствие4строкам Fabric в Object Browser,
нормальную работу UI и отсутствие замеченных сбоев CLO. Ограниченный gate
**ACCEPTED**: counts/indices/names текущего fixture; assignment не проверен.
Никакого импорта/assignment/переключения вариантов, names не доказывают назначения.
При error/unknown/mismatch/dialog/hang STOP без retry/fallback/cleanup.
Обычная остановка bridge — `plugin/clo3d_mcp_stop.py` только при доступном UI;
не kill по имени/порту. Native call time не ограничен client timeout.

### Дополнительная активная read-only проверка — 2026-11-09

Пользователь разрешил более активные проверки; объявлен bounded scope без
mutations:5serial cycles fabric/avatar/pattern inventories, geometry до16деталей,
final inventories и status. При первой error/schema/session/inventory mismatch
STOP без retry/cleanup. Client budget90с, один outstanding call, guards до reads.
Это direct MCP orchestration, не запуск verify_domains scenario и не load1000.

Результат **PASS**,17.159с:5полных циклов,23native-tool reads +24external status
reads (+initial info), геометрия всех5деталей (position_mm/area_mm2/bounding_box,
index/name matched fresh list), cap16 не достигнут. Все6наблюдений каждого списка
(5cycles+final) совпали: fabrics4,avatars1,patterns5. Final same-session ready/idle,
waiting=waiters=0,active=null,error=null; mutations0. Client call p50=743мс,
p95=758мс,max766мс; это wall time MCP calls, не чистое native API время.
Полная топология/кривые/свойства ткани/assignment/pose/fit/simulation не проверены.
Подтверждение UI пользователем относится к предыдущим чтениям и исходному
состоянию перед этой17секундной проверкой, не к отдельному замеру её UI latency.
