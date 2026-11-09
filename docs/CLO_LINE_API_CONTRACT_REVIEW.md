# CLO API линий — отдельный разбор контракта

2026-11-09. Target: CLO2026.1.336 / SDK11.0.1. Статус: **документация
проверена; один real `GetPatternLineInfo` наблюдён (раздел7) и length-
correspondence 4/4 на прямоугольнике (раздел8), MCP tools линий не реализованы**. Это не исправление/fallback `get_pattern_outline`:
B06 остаётся BLOCKED после native `[]` для existing own fixture. См. `CLO_OUTLINE_CHECK.md`.

## 1. Источники и уровень доказательства

- Официальный [API List](https://developer.clo3d.com/list.html#pattern-api),
  [RST source](https://developer.clo3d.com/_sources/list.rst.txt).
- [Changelog](https://developer.clo3d.com/changelog.html) /
  [RST](https://developer.clo3d.com/_sources/changelog.rst.txt): GetPatternLineInfo
  указан среди новых Geometric Data APIs V11.0.0, August2026; GetLineLength —
  V3.2.0, December2021. Возраст метода не доказывает работоспособность binding.
- Повторно прочитаны текущие RST sections: сигнатуры и приведённые ниже
  docstrings совпадают по содержанию с локальным official snapshot. Полный
  каталог не перегенерировался, совпадение SHA всего сайта не утверждается.
- Локальная provenance: `api/clo_official_api.json`, SDK11.0.1 / CLO2026.1.336,
  source RST SHA256 `bbd825dad535c44525b98bdbe358d8129a6fcb300d89c90e7e5297443cf34862`.
  Это hash прежнего snapshot, не hash нового HTTP fetch.
- Исторические runtime metadata: `CLO_API_RUNTIME_EVIDENCE.md` и
  `CLO_FABRIC_ASSIGNMENT_CHECK.md` (после B05C). Имена callable/docstrings и
  arity видны; это не successful native call/JSON schema/семантическая приёмка.
- В этом разборе нет вызовов CLO, probe, legacy listener, SDK downloads или
  изменения transport/production contracts. Новые runtime metadata не снимались.

## 2. Точные Python declarations

### GetPatternLineInfo: описание внешних линий одной детали

```python
def GetPatternLineInfo(_patternIndex: int) -> str
```

Official ID: `pattern_api.GetPatternLineInfo#45ddc71808d7eb67`.
Snapshot: `api/official/pattern_api-003.json`, Python RST block1291/line14766,
HTML block1291/line15507. В текущем RST def находится на line14768.

Документировано:

- `_patternIndex` — RealPatternList order, не full list с фурнитурой.
- Возвращается **строка JSON**, не Python dict/record и не список outline points.
- Назначение — выбрать outline `_lineIndex`, в частности для attachment API;
  сам getter не выполняет attachment и не запускает solver по этому описанию.
- `lineIndex` согласован с порядком GetLineLength / DeleteLine. Cross-reference
  PlaceButtonPairsOnEdge явно называет outline line index0-based. Это не
  доказательство равенства point index, array position, child ID или seam ID.
- Поля верхнего уровня: `status`, `patternIndex`, `patternName`, `lineCount`,
  `boundingBox`, `lines`.
- `boundingBox`: `minX`, `minY`, `maxX`, `maxY`, `width`, `height`.
- Элемент `lines`: `lineIndex`, `length`, `orientation`, `location`, `start`,
  `end`, `mid`, `midNorm`. Последние четыре — объекты с `x`, `y`.
- `length` — **мм**; `midNorm` — 0..1 в bounding box.
- `orientation`: `horizontal` / `vertical` / `diagonal`.
- `location` показан как `top` / `bottom` / `left` / `right` / `top-left` /
  `...` / `center`: список **не исчерпывающий enum**.
- Ошибка документирована как `{"status":"failed","message":...}`.

Не определено достаточно точно:

- Literal успешного `status`, типы всех JSON numeric fields, возможность extras,
  точность чисел, отсутствие/nullable fields на частичном результате.
- Размер строки/число линий, поведение empty success, гарантии уникальности и
  непрерывности lineIndex, порядок массива lines, closure/winding.
- Coordinates названы **2D pattern-window units**. Не указан точный origin,
  Y direction/scale; нельзя переименовать в `points_mm` или приписать frame
  `bbox_top_left_y_down` от другого getter. `midNorm` не устраняет эту неизвестность.
- `mid` не объявлен явно arc-length midpoint или средним start/end; ориентация
  и location не дают curve controls/tessellation/полной формы кривой.
- Native error message, invalid index outcome beyond failed JSON, GUI dialogs,
  максимальное время исполнения и atomic snapshot не проверены.

### GetLineLength: длина внешней линии

```python
def GetLineLength(_patternIndex: int, _lineIndex: int) -> float
```

Official ID: `pattern_api.GetLineLength#1ae661ba75ad2f5a`.
Snapshot: `api/official/pattern_api-002.json`, RST block929/line10536,
HTML block929/line11097; current RST def line10538.

Собственный docstring обещает только «pattern line length» / «return line length».
Real-pattern namespace/outline ordering связаны **cross-reference** из
GetPatternLineInfo и PlaceButtonPairsOnEdge, а не подробным @param этого метода.
Мм согласуются с `lines[].length` и edge arc-length APIs, но независимая units/
numeric correspondence проверка не выполнялась. Sentinel для invalid indices,
значение0/negative, bounds и exception policy в этой декларации не определены.
Нельзя трактовать `0.0` как failed/success только по truthiness.

### GetLineLength: длина линии дочерней формы — отдельная перегрузка

```python
def GetLineLength(_patternIndex: int, _childrenIndex: int, _lineIndex: int) -> float
```

Official ID: `pattern_api.GetLineLength#3bc2ab838bd1591f`.
Snapshot: тот же shard, RST block931/line10555, HTML block931/line11117;
current RST def line10557. Документация говорит «children shape index».
Парный C++ tab назван GetLineLengthForInnerShape, но Python declaration имеет
имя GetLineLength с3аргументами. Не создавать Python alias по C++ имени.

Child namespace/inner-line enumeration, error sentinels и единицы отдельно не
раскрыты. Нет основания передавать childrenIndex=-1/0 как «outer» или считать
это full pattern index. Перегрузка исключена из первого outer-line контракта;
никакого fallback2args→3args и угадывания child index.

## 3. MCP контракт — реализован как `get_pattern_lines` (tool20)

Предметная операция: **инспекция внешних линий**, не получение outline endpoint
polygon и не attachment/sewing/mutation. Tool `get_pattern_lines` реализован;
discovery20 после restart.

Input: required strict `pattern_index`0–255 и unique exact
`expected_name`1–128, fresh list guard; без bool/string coercion, extras, child
index, controls или auto-fallback flags. Те же ограничения имён, что у текущих
pattern tools. Name/index не durable identity; same-session guard не atomic.

Output зафиксирован по observed success-схеме (раздел7): `pattern_index,
pattern_name,line_count,bounding_box_mm,lines[],units:"mm",coordinate_frame:
"api_2d_mm"`. Failure (`status!="success"`), malformed JSON и unsupported layout
распознаются как `invalid_native_result`; native message никогда не отдаётся и
не логируется. `verified` по одному read не выставляется.

Реализованная обработка:

- Exact str, максимум64KiB UTF-8; bounded JSON nesting и numbers; reject duplicate
  keys, NaN/Infinity, bool-as-index/numeric, invalid Unicode, unexpected root.
  Bounds — локальная policy, **не documented native limits**. Проверка размера
  после return не ограничивает время/память самого native вызова.
- Нет coercion str→float, нет `str(opaque)`/truncation/fabricated bbox lines.
  Проверяются patternIndex/name, lineCount == len(lines), unique bounded line
  indices, finite numeric values, bbox extents, documented orientation и midNorm
  range. Максимум512линий; returned native lineIndex используется явно, без
  индексации по array position/contiguity.
- `length == distance(start,end)` не проверяется: на кривой это сравнило бы arc
  length и chord. Endpoints не складываются в polygon; holes/controls/seam
  connectivity и curve fidelity не обещаются.
- List/count checks до и после единственного native read; first error/unknown →
  STOP, без automatic retry/rollback/cleanup.
- `GetLineLength(i,k)` остаётся отдельной проверкой длины, не fallback для
  failed GetPatternLineInfo/outline; `k` берётся только из свежего lines result.

Synthetic valid intent: «покажи внешние линии uniquely named panel» с fresh
`{"pattern_index":0,"expected_name":"panel"}`. Invalid/no-call: bool index,
`children_index`, `expected_name` не совпадает/не уникально. Composition: fresh
list → `get_pattern_lines` → независимое чтение geometry тем же target.
Anti-selection: «получи outline, раз outline getter пустой» → **не вызывать
lines как замену**; «покажи площадь» → `get_pattern_geometry`.

## 4. Real gate — выполнен; детали в разделах7–8

Историческая подготовка: explicit read-only probe/adapter, guards и локальные
tests. Дальнейшие ограничения сохраняются.

Выполненный bounded scope: fresh session/idle/list/geometry own fixture → один
GetPatternLineInfo для fresh uniquely named собственной детали → bounded schema
observation; затем отдельный length-gate (≤4 двухаргументных вызова). Ноль scene
mutations, ноль outline calls, ноль 3args GetLineLength.

Если первый response failed/empty/malformed/unknown status — STOP без следующего
native getter. Успешный schema gate не доказывает coordinate frame. Проверка
длин прямоугольника120×80 (ожидаемый multiset120,120,80,80 с заранее выбранной
tolerance) — отдельная следующая стадия: не более4outer length calls по actual
returned indices, только при подтверждённых fresh fixture geometry и schema.
Не менять detail ради проверки origin/Y: frame остаётся pending до отдельного
coordinate experiment. Existing user patterns не трогать.

При native hang нет обещания cancel/timeout отмены. Никаких фоновых native calls,
UI automation, hot reload/restart или автоматического удаления fixture. Probe
требует verified UI thread/idle/one-shot/reentrancy guards; embedded production
изменения потребуют пользовательского полного restart, не Stop→Start worker.

## 5. Итог

Документированная самостоятельная операция найдена; для публикации нормализованного
MCP контракта evidence недостаточно. Основные gaps: точная coordinate frame на
произвольных деталях, failure/length semantics и real identity/line ordering.
Первый real schema observation (раздел7) закрыл success literal и actual JSON
shape на одном прямоугольнике и показал absolute API-mm frame; length-
correspondence (раздел8) подтвердил4/4 равенство с outer `GetLineLength` на том
же прямоугольнике. Кривые, frame после move/rotate и failure semantics остаются
открытыми; MCP tool остаётся planned.
`api/review_gates.json` связывает line-info/обе length overloads с этой проверкой;
coverage остаётся planned/not_tested/not_established. B06 не разблокирован.

Локальная проверка после review: focused145passed11.13с; full958passed,
1skipped61.68с (real symlink unavailable). Source mappings,coverage1134declarations,
workflow eval37cases/self-test2valid6invalid и git diff --check PASS. Regression
в `tests/test_api_coverage_catalog.py` проверяет review gate для всех3declarations,
отсутствие implementation/current operation/real acceptance и native line calls
в текущем pattern adapter. Эти tests не вызывают CLO и не доказывают JSON/units.

## 6. Ручной one-shot schema probe — подготовлен, real pending

**Текущая инструкция после восстановления fixture:** заново открыть с диска
`diagnostics/clo3d_mcp_line_info_probe.py` и Run один раз,без restart/stop/start.
Предыдущий запуск был blocked own_fixture_missing_or_ambiguous, line_info_calls0;
agent отдельно подтвердил отсутствие fixture в list5. По просьбе пользователя
создана новая own120×80 с прежним именем,index5; independent geometry/list и
original5geometry/mappings/fabrics exact fresh baseline PASS,ready/idle.
Скрипт теперь содержит явно выделенную **вторую ручную попытку** только в этой
проверенной сессии,с отдельным marker. Старый marker не удаляется/сбрасывается;
повтор второй попытки запрещён даже при ошибке или missing fixture. Это не
automatic retry native call: GetPatternLineInfo ранее ни разу не вызывался.
Native бюджет,redaction и запрет outline/length/mutations остаются прежними.
Ниже исходный runbook; указание «не повторять» относится к каждой попытке.

Скрипт: `diagnostics/clo3d_mcp_line_info_probe.py`. Пользователь явно запросил его
подготовку и сам выполнит в CLO. Это отдельный diagnostic, не новый MCP tool и
не production adapter. Никаких outline/length calls, setters, файлов, сети,
регистрации callbacks/threads/IPC или imports legacy listener/runtime.

### Запуск

1. Оставить текущий CLO/MCP работающим и собственную деталь
   `MCP_B06_outline_03cc0407` в сцене. Не переименовывать её и не редактировать
   сцену во время запуска. Полный restart и Stop→Start **не требуются**.
2. В Script Editor через Open открыть `diagnostics/clo3d_mcp_line_info_probe.py`
   из этого проекта и нажать Run **один раз**. Agent не отправляет в это время
   MCP scene calls. Старый outline probe не запускать.
3. Прислать JSON-строку `clo_line_info_probe_v1` и сообщить об unusual UI/dialog/
   hang. Native `[Info]` logs допускаются; private scene paths не требуются.
   Скрипт дополнительно пишет тот же sanitized отчёт в
   `<project>/acceptance-output/clo_line_info_probe_v1.json` (gitignored, не IPC)
   и печатает `[LOG] <path>`; при не найденном project root — `[LOG] unavailable`.
4. При blocked/command_error/malformed/native failure **не повторять**, не
   сбрасывать marker и не перезапускать service ради нового вызова.

Probe требует active verified service/executor.ready и owner/callback/current
UI thread с единственным visible window thread; временно ставит busy guard от
reentrancy и восстанавливает его в finally. Отдельный builtins marker блокирует
второй запуск в этой session (включая ошибку), ставится до import/native entry.
Outline marker не меняется. Не более16session markers; файл не создаётся.

Fresh bounded count/name read выбирает **unique exact own name**, индекс5 не
hardcoded. Дополнительный count/target name check перед единственным native
GetPatternLineInfo. Максимум260native calls при256деталях:2counts+257names+1line.
**После line getter нет больше native reads вообще**, даже inventory: неизвестный
success status не может разрешить продолжение. Before/after stability и geometry
после probe не подтверждаются. Для schema observation geometry getters не нужны;
проверка размеров120×80/units/lengths остаётся отдельным следующим gate.

Ожидаемый отчёт: status observed, line_info_calls1, native.type/bytes/root_type,
типы documented fields, только status token (ASCII letters/underscore≤32chars),
matches ожидаемых own index/name, numeric bbox и до4line samples с типами/числами
и allowlisted orientation/location. Не выводятся raw native JSON/message, произвольные
keys/строки/имена/paths/session tokens. Unknown location — unlisted_or_nonstring,
не validator failure. Числа не преобразуются из строк, bool не становится числом.

Прибор парсит только exact str≤64KiB UTF-8, depth≤16, numeric token≤64chars,
finite magnitude≤1e16; duplicate JSON keys/NaN/Infinity/invalid Unicode rejected.
Это safety bounds диагностики, не documented native limits или production schema.
Пустая строка/non-object/malformed/failure/identity mismatch видны как observation
и stop_reason, **не success tool result**. Никаких контрольных повторов.

Обычно возвращается за секунды, polling/sleeps нет. Native call нельзя отменить
таймаутом этого скрипта. После возврата скрипт сам завершён, постоянных callbacks
не оставляет. Если UI доступен, общий stop service — `plugin/clo3d_mcp_stop.py`;
не kill по порту/имени. При диалоге/зависании остановить сценарий и сообщить симптом,
не выполнять другой probe/cleanup. Local tests — `tests/test_line_info_probe.py`;
реальное выполнение и UI confirmation **pending** до ответа пользователя.

После подготовки: focused line-info+outline probes65passed0.10с; full998passed,
1skipped46.39с (real symlink unavailable). Mappings/coverage/eval37/self-test и
git diff --check PASS. Production/transport/tool inventory не менялись.

## 7. Первый real schema observation — 2026-11-09

Пользователь запустил probe дважды. Первый запуск попал в новую сессию, где
фикстуры не было: `own_fixture_missing_or_ambiguous`, `line_info_calls=0`,
marker этой сессии израсходован без native-вызова (не сбрасывался). Фикстура
`MCP_B06_outline_03cc0407` пересоздана MCP-командой (120×80, index5, центр
[2060,1290], area9600.0009765625, list/geometry readback PASS), затем выполнен
только Stop→Start сервиса (CLO и сцена сохранены), generation2. В новой сессии
probe сделал **ровно один** `GetPatternLineInfo(5)`.

Наблюдено:

- exact `str`, 982bytes/chars, root object; ровно шесть documented полей,
  extras0; `status="success"`; `patternIndex=5` int; `patternName` exact;
  `lineCount=4` int == `len(lines)`.
- `boundingBox`: floats minX2000.0/minY1250.0/maxX2120.0/maxY1330.0/
  width120.0/height80.0.
- 4 элемента `lines`, в каждом ровно восемь documented полей, extras0;
  `lineIndex` 0–3 int; `length` 120.0/80.0/120.0/80.0 float;
  `orientation` horizontal/vertical; `location` bottom/right/top/left;
  `start`/`end`/`mid`/`midNorm` — объекты `{x,y}` float.
- `mid` совпал с арифметической серединой start/end; `midNorm` — позиция
  mid внутри bbox (0.5,0.0), (1.0,0.5), (0.5,1.0), (0.0,0.5).

Что установлено для этой сборки и этого сэмпла: literal success, точный набор
полей верхнего уровня/линии, числовые типы, непрерывность lineIndex от0,
согласованность mid/midNorm с bbox. **Координаты не bbox-local**: minX/minY
равны absolute API-mm создания (2000/1250), а не0; это тот же API-mm frame,
что create/geometry, и отличается от outline (bbox TOP-LEFT/Ydown). Метки
location при этом дают minY→bottom, maxY→top, то есть Y вверх в этом frame.

Не установлено: failed/malformed/partial/пустой success, поведение длины на
кривых (arc vs chord), mid на кривой, frame после move/rotate/scale, midNorm
при нулевой ширине/высоте, порядок/уникальность lines для сложных деталей,
дочерние формы (3-args overload), invalid index, GUI dialogs и время вызова.
Один сэмпл — evidence, не acceptance; B06 это не разблокирует.

Следующий отдельный gate (только после согласования): не более четырёх
`GetLineLength(patternIndex, lineIndex)` по фактическим returned indices0–3,
ожидаемый multiset{120,80,120,80} с заранее выбранной tolerance, при fresh
fixture/schema. Без 3-args overload, outline calls, retry или fallback; первый
failed/unknown — STOP. Coordinate-frame/mid experiment остаётся отдельной
задачей и не редактирует чужие детали.

## 8. Length correspondence probe — подготовлен, real pending

Скрипт `diagnostics/clo3d_mcp_line_length_probe.py`. Один `GetPatternLineInfo` для
fresh identity/schema и **не более четырёх** `GetLineLength(index, lineIndex)`
строго 2-аргументной перегрузки по returned indices. Ноль outline calls,
3-args overload, setters, mutations, файлов, сети, callbacks или runtime imports.

Guards те же: verified active service, idle, executor ready, owner/callback/
visible window thread, busy guard. Отдельный builtins marker
`_clo3d_mcp_line_length_probe_runs` — один запуск на session, предел16; marker
ставится до native entry, поэтому blocked-fixture тоже расходует попытку:
сначала убедиться, что fixture на месте. Untrusted line-info проходит strict
bounded JSON (exact str≤64KiB, depth≤16, duplicate keys/NaN/Infinity rejected);
требуются `status="success"`, exact patternIndex/name, lineCount4==len, unique
lineIndex set{0,1,2,3}, finite lengths. Только после этого длины.

Сравнение: per-index `abs(call_length - info_length)` и независимый multiset
против{120,80,120,80}; tolerance0.01мм — локальная policy, не native units.
Любой unexpected line-info/length type/exception → STOP без оставшихся length
calls и без retry. Отчёт `clo_line_length_probe_v1`: line_info_calls1,
line_length_calls≤4, lengths[{lineIndex,type,info_length,call_length,abs_delta}],
max_abs_delta_mm, per_index_match, actual/expected multiset, stop_reason; raw
JSON/message/имена не выводятся.

Проверка: та же проверенная сессия и fixture index5; открыть файл с диска и Run
один раз, restart не требуется (новый marker). Прислать JSON. Скрипт сам
записывает тот же sanitized отчёт в `<project>/acceptance-output/
clo_line_length_probe_v1.json` (gitignored, не IPC) и печатает строку
`[LOG] <path>`; если project root не найден — только консоль и
`[LOG] unavailable`. Локальные тесты — `tests/test_line_length_probe.py`;
real run выполнен (ниже), UI-аномалий не заявлено.

### Полученный результат, 2026-11-09

Сессия `acd3782f4a8156787f81435ca91e00e1`, fixture index5, один
`GetPatternLineInfo` и четыре 2-аргументных `GetLineLength`. Отчёт
`clo_line_length_probe_v1`: `line_indices[0,1,2,3]`,
`info_lengths[120,80,120,80]`, `call_lengths` те же, у всех четырёх
`abs_delta=0.0`, `max_abs_delta_mm=0.0`, `per_index_match=true`,
`multiset_match=true`, `stop_reason=stop_no_retry`. Сцена после прогона
не изменилась: те же6 деталей, fixture index5 120×80, area9600.0009765625.

Установлено для этого прямоугольника/сборки: lineIndex из `GetPatternLineInfo`
принимается 2-аргументной `GetLineLength`; возвращаемые длины совпадают с
`lines[].length` побитово в этом сэмпле; единицы согласованы как мм; 3-аргументная
перегрузка не вызывалась; вызовы 2-args работают через реальный binding.
Не установлено: длины/семантика на кривых (arc vs chord), поведение после
move/rotate/scale, invalid indices/failure, дочерние формы, устойчивость на
нескольких деталях. Это один сэмпл — evidence, не production acceptance.
MCP tool линий реализован (tool20); curve/frame evidence — раздел9.

## 9. Live tool20 и семантика кривых/frame — 2026-11-09

Live session `467a65735650b657b53409e1d531e970`, `server_build == executor_build
== 68635cd893cd`, capability 20. `get_pattern_lines` на fixture index5 вернул те
же4 линии0–3,120/80/120/80; длины равны chord на прямоугольнике.

Read-only чтение существующих деталей `"2"`,`"3"`,`"5"`,`"6"`,`"1"`:
11/6/11/6/14 линий. **`length_mm` не является chord**: на криволинейных сегментах
длина больше расстояния start–end (max48.6934мм на `"1"`;3.6791/5.1709/3.6792/
5.1709 на остальных; на прямом fixture разница0). Значит native length ведёт
себя как arc length; независимого arc-измерения нет, поэтому это inference, не
доказанная единица для всех кривых.

**`mid_mm` — арифметическая середина endpoints даже на кривых** (max отклонение
0.0001мм на всех5 деталях), а не точка на дуге. `mid_norm` — та же середина,
нормализованная к bbox (0..1). **`orientation` — не точный вектор**: наклонные
сегменты с |dy|>|dx| помечены `vertical` (например `"2"` line0: dx117,dy380),
поэтому это dominant-axis/region label, не геометрия направления.

Frame: move своей fixture `[25,−30]` → все start/end/mid сдвинулись ровно на
`[25,−30]` (ошибка0), длины и mid_norm не изменились, bbox сдвинулся; restore
`[−25,+30]` вернул точный baseline `[2000,1250]-[2120,1330]`. Это подтверждает
absolute API-mm frame и translation invariance; rotation/scale не проверялись.

Итог: tool20 работает на реальной сцене; кривые дают arc-like length и chord
mid; orientation не использовать как direction. Rotation, invalid indices,
failed/partial и дочерние формы остаются открытыми.

## 10. Rotation/scale и failure-пути — границы

**Rotation/scale:** в official API целевой CLO2026.1.336 нет symbol для поворота
или масштаба pattern piece; есть только `FlipPatternPiece`/`FlipPatternNormal`
(зеркало/mesh normal), не rotation/scale. Поэтому отдельный transform-tool не
реализуется и rotation/scale-frame не проверяется; переносить выводы с move
нельзя. Flip — отдельная mutation с неполной документацией, не входит в этот
этап.

**Invalid index (MCP):** live `get_pattern_lines({pattern_index:5})` на сцене из
одной детали и неверное `expected_name` вернули `stale_pattern` до native
вызова — guard работает; native не вызывался.

**Native failed/empty:** публичный tool не пропускает invalid index, поэтому
подготовлен `diagnostics/clo3d_mcp_line_failure_probe.py`: один
`GetPatternLineInfo(count)` (первый несуществующий индекс) с теми же guards и
one-shot marker. Он покажет literal failed/empty и наличие `message`, не выводя
текст. Запуск — один Run в текущей сессии; другой native вызов не выполняется,
retry нет. Partial/malformed реальный binding не производит: это остаётся
fake-only contract, не real evidence.

Ожидаемый отчёт: `clo_line_failure_probe_v1`, `invalid_index=count`, `calls=1`,
`native.status_token`, `message_present`, `lines_length`. Локальные тесты —
`tests/test_line_failure_probe.py`.
