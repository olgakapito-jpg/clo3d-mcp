# CLO3D MCP — Python / Windows Named Pipe

Один скрипт внутри CLO запускает отдельный MCP HTTP-процесс для текущего
сеанса. Ассистент подключается по `http://127.0.0.1:8765/mcp`.
Обмен с CLO — Named Pipe, **без файлов запросов, ответов и heartbeat**.

Это транспортный MVP: **пять диагностических инструментов**, не полный набор
построения одежды. Проверенная среда: Windows, CLO 2026.1, встроенный Python
3.11.8 x64, внешний CPython 3.11.9, официальный MCP SDK 1.26.0.
P0–P3 приняты реальными проверками; P4 (нагрузка/длительная работа) выполняется.

## Подготовка

- Один экземпляр CLO с Python Script Editor и действующей лицензией.
- Установленные `uv` и CPython 3.11. Исходники должны оставаться доступны CLO.
- Из корня checkout выполнить во внешнем PowerShell, **не внутри CLO**:

```powershell
uv sync --frozen --python 3.11
```

Launcher ожидает `.venv/Scripts/python.exe`. Никаких установок пакетов в
встроенный Python CLO, собственного C++, CLO SDK или Qt не требуется.
Python-пакет декларирует 3.10+, но новый runtime проверен только на указанной
выше среде; совместимость с другими версиями не обещается.

## Запуск

1. Открыть CLO, для диагностики — расходную тестовую сцену.
2. В **Script → Script Editor** открыть `plugin/clo3d_mcp_start.py` и нажать Run.
3. Закрыть Script Editor. Launcher возвращает управление, callback обслуживается
   UI CLO. STARTED — ещё не готовность; ожидается READY и/или `ready=True` в MCP.
4. Если CLO не задаёт `__file__`, указать абсолютный путь к корню checkout
   в `ROOT` в начале launcher. Не подменять внешний Python на `sys.executable` CLO.

Повторный запуск в **том же CLO** даёт ALREADY_STARTED, не второй процесс.
Второй экземпляр CLO на том же порту не поддерживается: занятый порт — ошибка,
чужой сервер не завершается. После изменения runtime-модулей открыть свежий CLO,
не перезагружать модули с сохранёнными native callbacks на месте.

## Текущий проект OpenCode / OpenChamber

`opencode.json` уже содержит project-local remote `clo`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "clo": {
        "type": "remote",
        "url": "http://127.0.0.1:8765/mcp",
        "protocol": "legacy"
      }
    }
  }
}
```

`legacy` здесь — classic MCP initialize официального SDK 1.26, **не файловый IPC**.
В другом checkout добавить project-local remote через
`opencode mcp add clo --url http://127.0.0.1:8765/mcp`.
Проверить `opencode mcp list` или панель MCP / `/mcps`. Конфигурация
перечитывается без перезапуска OpenCode. До запуска CLO или после его закрытия
ECONNREFUSED нормально. Глобальные настройки проекта не требуются.

## Инструменты нового пути

- `ping`: реальный round trip через FIFO в UI executor CLO.
- `get_pattern_count`: последовательное чтение числа лекал.
- `transport_status`: внешняя очередь/HTTP; доступен и при занятом CLO.
- `get_session_info`: CLO session ID, PID и readiness (не MCP HTTP session ID).
- `create_test_rectangle`: **один** квадрат 100×100 в координатах API (мм)
  в начале 2D. Изменяет сцену; запускать осознанно, не повторять после timeout.

Новый путь не загружает extensions и не публикует legacy-команды импорта,
экспорта, симуляции, произвольной геометрии или exec.

## Остановка

Внутри того же CLO запустить `plugin/clo3d_mcp_stop.py`, закрыть редактор
на несколько секунд. FINISHED должен показать stopped, exit code0,
оба cleanup_pending=False и error=None. Повторный stop выводит отчёт.
После обычного закрытия CLO его MCP завершается сам по pinned process handle.
Управляется только принадлежащий сеансу child, не процессы по имени/порту.

## Гарантии и ограничения

- Один выполняемый CLO job, внешняя FIFO32, bounded history128/waiters128.
- Раздельные deadlines очереди/dispatch. Timeout и отмена после dispatch
  **не останавливают CLO API**. Следующий job не идёт поверх незавершённого.
- Отправленные команды автоматически не повторяются. `outcome_unknown` означает
  необходимость сверить сцену; exactly-once через падение процесса не обещается.
- Долгий синхронный CLO API может блокировать UI. Пауза callback или модальное
  окно не считаются смертью CLO. Readiness подтверждает только текущий сеанс.
- HTTP только loopback, строгие Host/Origin checks. **HTTP без отдельной
  аутентификации**: доверяем локальным процессам машины. Не открывать порт
  наружу, не ставить proxy; loopback не защита от вредоносного локального ПО.
- Pipe — ACL текущего пользователя, peer PID и HMAC. Секрет в памяти, не в логах.
- До 16 удерживаемых поколений callback за жизнь CLO, затем нужен его перезапуск.
- Поддержка не-Windows и нескольких CLO не входит в новый путь.

## Диагностика и тесты

`http_bind_failed`: порт занят, не убивать владельца порта. NOT_STARTED:
проверить корень проекта и подготовленную `.venv`. Нет строки READY:
проверить `get_session_info` — в принятом CLO callback работал, хотя вывод
READY не появился. Не запускать launcher бесконечно и не скрывать сбои retries.

```powershell
uv run --frozen --with pytest pytest -q
```

Windows CI запускает эту же suite, включая actual pipe/process тесты без CLO.
Локальные fake API и HTTP/pipe проверки **не заменяют** ручную приёмку CLO.
Реальные результаты и инструкции:

- [План и границы этапов](docs/PYTHON_TRANSPORT_PLAN.md)
- [Принятый P3](docs/P3_MCP_CHECK.md)
- [P4: ограниченная нагрузка и ручные проверки](docs/P4_TRANSPORT_CHECK.md)

## Legacy и происхождение

Upstream: [Ubani-Studio/clo3d-mcp](https://github.com/Ubani-Studio/clo3d-mcp),
автор исходного проекта Alabo MacPepple-Jaja. Исходные handlers и тесты сохранены.
Историческая инструкция с каталогом бизнес-инструментов сохранена в
[docs/LEGACY_README.md](docs/LEGACY_README.md); это **не** инструкция нового пути.
`uv run clo3d-mcp` / `src/clo3d_mcp/server.py` и
`plugin/clo3d_mcp_plugin.py` остаются отдельным stdio/file legacy-режимом.
Новый launcher никогда не переключается на него автоматически.

MIT, см. [LICENSE](LICENSE). SDK/сцены CLO в репозиторий не включены;
нужна собственная лицензия CLO.
