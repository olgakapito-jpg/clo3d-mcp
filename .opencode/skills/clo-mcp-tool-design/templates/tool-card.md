# Tool card: <exact_tool_name>

Статус: proposed / implemented / local-tested / real-accepted / blocked.
Карточка — описание, не регистрация MCP tool и не разрешение вызова.

## Намерение и выбор

- Одна фраза: <action + target + bounded outcome>.
- Использовать когда: <пользовательская задача>.
- НЕ использовать когда: <границы; соседний canonical tool>.
- Availability: <enabled profile, prerequisites, target version/build>.

## Контракт и источник

- MCP name / wire command / qualified native symbol + overload:
- Official URL, SDK/docs version, checked date:
- Runtime signature/types evidence, pending mismatches:
- Coverage IDs и donor revision/handler при наличии:
- Native units, axes/origin, index namespace, face/colorway scope:

## Server-visible description (проект)

> <Короткое действие. Ключевой scope/units/guards. Что проверяет результат.
> Существенные ограничения. Mutation: never automatically retry after dispatch.>

## Inputs

Для КАЖДОГО поля: exact name, type, required/default, units, bounds/enum meanings,
пример, rejects. Отдельно extras, bool/int, finite values, Unicode и collections.
Для targets: свежесть индекса, expected identity, неоднозначные имена, scene scope.
Для paths: input/output policy, format, overwrite, побочные файлы и privacy.

## Outputs и evidence

- Success envelope + exact schema/example; какие поля реально существуют:
- Значение каждого поля, units, tolerances; не только type=dict:
- Что доказывает return; чего НЕ доказывает:
- Readback getter/artifact/visual criteria и независимый следующий вызов:
- Native/API time vs executor time vs client latency:

## Effects и ограничения

- read / scene mutation / filesystem / network / lifecycle / unknown:
- Добавление/замена/удаление, затронутые unrelated entities и indices:
- Может открыть dialog/блокировать UI? Что означает client timeout:
- Preconditions до эффекта; лимит work/result; отсутствующие prerequisites:
- Реальные annotations и rationale; не считать их security enforcement:

## Errors и безопасный следующий шаг

Для КАЖДОГО фактического error code: stage, possible effect, read-only
reconciliation, stop rule. Никогда auto-retry dispatched mutation/unknown.
Не обещать job lookup/cancellation/recovery, которых текущий HTTP API не имеет.

## Примеры и композиция

- Valid call и ожидаемый bounded результат (synthetic, не live instruction):
- Invalid/no-call пример с причиной:
- Before: какие reads нужны и какие поля передать:
- After: readback, refreshed target list, разрешённые dependent steps:
- Anti-example: ошибочный tool/units/scope и правильная альтернатива:

## Проверки и публикация

- Contract/API fault/HTTP schema/whitelist tests:
- tools/list description/inputs/outputs/annotations consistency:
- Tool-selection eval и workflow test (в fake среде):
- Real acceptance path/scope/remaining gate:
- Docs/catalog/workflow/skill updates; owner/reviewer:
