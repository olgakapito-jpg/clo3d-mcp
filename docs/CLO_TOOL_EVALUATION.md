# Offline evaluation: выбор tools и порядок workflow

Дата: 2026-11-09. **Исполняемый offline contract pack, не результат выбора LLM,
не real-CLO приёмка и не новый MCP tool.** Ничего не отправляет в CLO/MCP,
не использует сеть, не запускает launcher/server и не меняет сцену.

## Состав и запуск

- `scripts/evaluate_tool_workflows.py`: stdlib CLI, AST inventory, строгий dataset
  validator и deterministic validator предоставленных plans/traces.
- `tests/evals/clo_tool_selection.json`: 34 русских намерения с ожидаемыми и
  запрещёнными выборами, аргументами, effects, blockers и stop conditions.
- `tests/test_tool_workflow_evals.py`: synthetic positive/negative проверки.

Из корня checkout, PowerShell:

```powershell
python scripts/evaluate_tool_workflows.py --check --self-test
uv run --frozen --with pytest pytest -q tests/test_tool_workflow_evals.py
```

`--check` сверяет dataset с AST **исходного** `transport_server.py`: 18 decorated
tools, обязательные параметры и literal mappings `service.call`. Capabilities
получает ограниченным AST-разбором list/concatenation в `protocol.py`, без exec.
Внешние `get_session_info`/`transport_status` — tools, но не executor capabilities.
Есть текущий `current18`, исторические `current16`/`current14` и `diagnostic5`. Это не запрос
`tools/list` работающего сервера и не доказательство включённого live profile.
При дрейфе current18 или неожиданной AST форме runner отказывает, а не подбирает
новый контракт автоматически.

`--self-test` проверяет два корректных trace (move и два serial delete с
обновлением списка) и шесть намеренно некорректных trace. Числа accepted/rejected
относятся **только к synthetic fixtures**, не к ответам модели. Pytest отдельно
покрывает всю цепочку create → copy → move → rename → delete и injected
error/unknown/schema/session faults на каждом mutating шаге.

## Dataset schema v1

Exact top-level keys: `schema_version:1`,
`evidence:"synthetic_contract_not_llm_or_live"`, `unavailable_tools`, `cases`.

Каждый case имеет ровно следующие поля:

- `id`: уникальный lowercase ASCII identifier, максимум 64 символа.
- `intent`: русский естественный запрос (10–2000 символов).
- `profile`: `current18`, исторические `current16`/`current14` либо `diagnostic5`; `scope`: `read_only`, `scene` либо
  `diagnostic`. Diagnostic square нельзя выбирать для production scope.
- `fixture`: `{ready:<strict bool>,patterns:[<unique synthetic names>]}`.
  Это исходное ожидаемое состояние, не данные настоящей сцены. Первый status
  и первый list trace должны ему соответствовать, если они присутствуют.
- `expected_tools`: минимально необходимые зарегистрированные инструменты.
  Пустой список означает **no-call**, а не «любой ответ подходит».
- `forbidden_tools`: current names либо names из явного `unavailable_tools`.
  Unavailable names никогда не допустимы в expected или исполняемых шагах.
- `forbidden_effects`: enum категорий `read`, `scene_mutation`,
  `diagnostic_mutation`, `filesystem_write`, `external_effect`, `global_mutation`,
  `unknown`. Effects выводятся runner из известного текущего inventory,
  не принимаются на веру от submitter. Будущие effects не включают будущие tools.
- `required_args`: tool → **полный** valid args object; хотя бы один вызов
  соответствующего tool должен совпасть точно, без extras/default coercion.
- `decision`: `complete`, `blocked`, `clarify`, `stopped`; `blockers`: enum
  причин, например `tool_unavailable`, `scope_missing`, `privacy`,
  `unsupported_geometry`, `capability_missing`. Complete требует пустой blockers.
- `stop_conditions`: все пять `error`, `outcome_unknown`, `schema_mismatch`,
  `session_change`, `stale_target`, без duplicates/неизвестных значений.

Границы: файл ≤200000 bytes, 20–128 cases, ≤128 steps, bounded JSON depth и
node budget. Duplicate JSON keys/IDs, bogus fields/schema, неизвестные tools,
недоступные expected tools, bool-as-number, NaN/Infinity, неверные polygons,
неизвестные effects/decisions/blockers и противоречащие scope ожидания отклоняются.
Pattern inputs/results проверяются реальным stdlib-only `pattern_contract.py`,
загруженным изолированно по пути. **Production validators не переписаны в eval.**
Server/native/legacy modules не импортируются.

Покрыты: status vs FIFO ping vs count/list/geometry; introspection != tool;
fabric/avatar/project import/simulation unavailable; straight polygons vs
curves/holes; whole-piece move vs point edit; relative copy; rename; stale
index/session; два delete с refresh; timeout без retry/rollback/finally cleanup;
diagnostics != готовая одежда; file scope/overwrite, privacy, global settings,
REST unknown effects; readiness и distinction capabilities/tools.

## Предоставленный plan или trace

Runner **не генерирует** план, не вызывает модель и не исполняет шаги. Чтобы
проверить заранее подготовленный synthetic JSON:

```powershell
python scripts/evaluate_tool_workflows.py --submission synthetic-trace.json --case whole_piece_move
```

`synthetic-trace.json` здесь — созданный вами входной fixture, не output/IPC
файл от CLO. Готовые Python fixtures доступны в `synthetic_examples(inventory())`
в runner; они не создают файлов автоматически.

Минимальный корректный **план** для `busy_status`:

```json
{
  "kind": "plan",
  "execution": "serial",
  "steps": [{"tool": "transport_status", "args": {}}],
  "decision": "complete",
  "blockers": []
}
```

Plan step имеет exact `{tool,args}`. Trace step имеет exact
`{tool,args,session,result}`. `session` допускает только synthetic identifiers,
например `synthetic-a`, не реальные session IDs. Общий envelope имеет exact
`kind`, `execution`, `steps`, `decision`, `blockers`. Parallel/batched execution,
retry/cleanup metadata и неизвестные команды не поддерживаются.

Trace status/info — **санитизированная synthetic projection**, не raw response:

```json
{
  "session_id": "synthetic-a",
  "ready": true,
  "connected": true,
  "quarantined": false,
  "error": null,
  "capabilities": ["ping", "get_pattern_count", "create_test_rectangle"]
}
```

`capabilities` обязательно у info и отсутствует у transport_status. Raw status
с endpoint/PIDs/внутренними путями намеренно не принимается. Queue results имеют
`ok:true` плюс текущие command-specific поля из каталога. Error — `ok:false`,
fixed `error`, optional `isError:true` и `scene_may_have_changed:true`.

Проверки trace:

1. Session/info и фактически разрешённые capabilities перед executor calls;
   ready/connected/quarantined/error, scope и свежий target list.
2. Для mutation — single serial шаг, fresh session preflight после предыдущей
   mutation, unique index/expected_name guard, исходная geometry для move/copy/
   rename. Для diagnostic — исходный count вместо target geometry.
3. Command-specific success schema и invariants count/name/index/area/relative
   position; возвращённый copy index, а не предположение «последний».
4. Перед любым следующим native шагом — отдельный geometry readback (delete →
   list, diagnostic → count), сверка identity и значений. Result `verified:true`
   сам по себе не заменяет independent readback. После delete list обновляет
   индексы и запрещает использование прежнего второго индекса.
5. Error/unknown/schema mismatch/session change прекращает trace. Завершающий
   fault допустим только с `decision:"stopped"`; **любой** следующий call в том
   же trace запрещён, включая retry, rollback и finally cleanup. Read-only
   reconciliation оформляется отдельным bounded submission, не resume.

Например, move → move без independent geometry или timeout → create/delete —
некорректны. Несовпадение fresh identity/geometry/invariants консервативно
отклоняет submission; это не повод автоматически чинить или повторять план.
No-call case требует пустые steps и точные decision/blockers.

## Privacy, результат и ограничения

- Не передавать реальные tokens, session snapshots, private scene data или
  машинные пути. Фильтр блокирует secret/path поля, drive/UNC/типовые private
  absolute paths, URL и некоторые token patterns. Это **не универсальный DLP**:
  входы должны быть заведомо synthetic и предварительно отредактированы.
- Runner выводит только summary counts/evidence и фиксированную ошибку; не
  печатает supplied values, traceback, пути или содержимое exception.
- Exit 0 означает, что предоставленный contract/dataset/trace прошёл эти
  проверки; exit 1 — отказ. Ни один exit не означает real-CLO success.
- Plan evidence — `static_plan_only`: нет результатов, невозможно доказать
  identity, эффект, корректность readback или отсутствие изменения пользователем.
- Trace evidence — `synthetic_trace_contract`: schema/invariants проверены на
  supplied observations, но **не доказана правдивость этих observations**.
- Expected tools — минимальный set, не точная полная последовательность:
  дополнительные безопасные reads возможны, если не запрещены case; no-call
  является строгим исключением. Нет semantics evaluator свободного текста
  ответа/качества готовой одежды и нет вероятностной метрики LLM selection.
- Это не полная scene simulator: полная топология, native bbox semantics,
  ownership, sewing/fabric relations, real session atomicity не доказываются.
  Fixture имена намеренно уникальны; duplicate live names требуют отдельного
  blocker, не auto-delete. Bounds/count/schema не гарантируют качество одежды.
- Этот runner не дублирует `scripts/verify_domains.py`: здесь static selection
  и supplied synthetic workflow contracts, не доменная или live acceptance.

Следующие независимые gates: при необходимости отдельный model-backed offline
evaluation с зафиксированной моделью/промптами и сохранёнными санитизированными
ответами; затем согласованный короткий real-CLO пакет после перезапуска
пользователем. Ни то ни другое этим pack не запускается и не объявляется пройденным.

Источники контрактов: `CLO_MCP_TOOLS.md`, `CLO_MCP_TOOL_AUTHORING.md`,
`CLO_MCP_WORKFLOWS.md`, live-source `transport_server.py`/`pattern_contract.py`.
