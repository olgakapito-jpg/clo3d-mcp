---
name: clo-<domain>-workflows
description: <When to use this specific domain skill and which user tasks it helps solve.>
---

# CLO <domain>: заготовка skill

Статус: TEMPLATE, НЕ установленный skill. Скопировать в отдельный каталог с
именем SKILL.md только после заполнения, review и подтверждения доступности
tools. Не создавать вложенный SKILL.md внутри другого skill.

## Read first

- Корневой AGENTS.md и clo-tool-workflows.
- <точные относительные пути к canonical tool cards и evidence>.

## Availability and scope

- Required published tools/capabilities/version:
- Native/API assumptions и известные blockers:
- Asset/permission prerequisites; не считать весь домен принятым по одному smoke:

## Tool selection

- Intent → canonical tool → отличие от похожих tools:
- Read-only vs scene/files/network/global effects:
- Identity/indices/units/face/colorway context:

## Recipes

- <один minimal сценарий со ссылкой на workflow-card>.
- <cross-domain сценарий и зависимости>.
- <read-only reconciliation сценарий>.
- <anti-example: когда ничего не вызывать/уточнить задачу>.

## Stop rules and reporting

Serial mutation/readback; no auto-retry/replay/rollback/cleanup после ошибки.
Timeout != cancellation. Completed != independently verified. Описать actual
код/схему результата, не создавать в инструкции несуществующие поля/API.

## Acceptance and maintenance

- Tool-selection evals, fault traces, real evidence и pending gates:
- Владелец; когда пересматривать skill после API/schema/build change:
