# CLO API: первичная read-only сверка 2026-11-09

Это доказательство наличия и описания binding, **не выполнение методов**.
Реальные новые getters/setters/import/simulate не вызывались. Текущий
`get_session_info` подтвердил ready, connected, пустую очередь, error=None;
сеанс совпал с принятым пакетом. PID/session secrets/локальные пути не нужны
для долговременного реестра и здесь не фиксируются.

Выполнены существующие `list_clo_api` и три `describe_clo_api` через текущий
FIFO/UI executor. Список ограничен пятью фиксированными модулями и не является
полной инвентаризацией всех bindings CLO. Сигнатуры ниже — сокращённая запись
реальных docstrings; `argN` не даёт семантики параметра, её брать из official
описания, не угадывать. Все перечисленные методы сообщили available=true.

## fabric_api

```text
GetFabricCount(bool=True) -> int
GetFabricCount(int) -> int
GetFabricName(int) -> str; GetFabricName(int, int) -> str
GetFabricIndexForPattern(int) -> int
GetFabricIndexForPattern(int, int) -> int
GetFabricPBRMaterialBaseColor(int, int) -> Tuple[float,float,float,float]
GetFabricPBRMaterialBaseColor(int, int, int) -> Tuple[float,float,float,float]
SetFabricPBRMaterialBaseColor(int,int,float,float,float,float) -> bool
SetFabricPBRMaterialBaseColor(int,int,int,float,float,float,float) -> bool
SetFabricPBRMaterialBaseColor(int,int,str) -> bool
SetFabricPBRMaterialBaseColor(int,int,int,str) -> bool
AssignFabricToPattern(int,int,int) -> bool
AssignFabricToPattern(int,int,int,int) -> bool
AddFabric(str) -> int
ReplaceFabric(int,str) -> bool
DeleteFabric(int) -> bool; DeleteFabric(int,int) -> bool
GetFabricInfo(int) -> str
GetFabricInformation(int) -> Dict[str,str]
GetFabricInformation(int,int) -> Dict[str,str]
```

Нужны explicit current-colorway semantics и строгий bool/int выбор overload.
Не объявлять float RGBA или JSON fabric info принятыми до фактического чтения.

## utility_api

```text
IsShowAvatar(int) -> bool
SetShowHideAvatar(bool) -> None; SetShowHideAvatar(bool,int) -> None
GetAvatarProperties(int) -> Dict[str,str]
SetAvatarProperties(int,Dict[str,str]) -> None
GetAvatarMeasurements(int) -> List[Marvelous::CloApiAvatarMeasurement]
DeleteAvatar(List[int]) -> bool
GetSimulationQuality() -> Tuple[int,int]
SetSimulationQuality(int,int) -> None
Simulate(int) -> bool
GetClothPositions(List[float]) -> None
SetCurrentColorwayIndex(int) -> None
GetCurrentColorwayIndex() -> int
CopyColorway(int,int) -> int
DeleteColorwayItem(int) -> None
SetColorwayName(int,str) -> None
GetColorwayName(int) -> str
```

Видимость проверяется по аватару; setter без индекса затрагивает другой scope.
Measurement требует проверки доступности полей bound record. `GetClothPositions`
может иметь проблему передачи output-list через Python binding: метод не
подходит для обещанного readback симуляции, пока отдельно не проверен.
`Simulate` сообщает bool, а не доказательство физически правильной драпировки.

## pattern_api

```text
GetPatternOutlinePoints(int) -> List[List[float]]
GetPatternLineInfo(int) -> str
GetPatternInternalShapePoints(int,int) -> List[List[float]]
GetLineLength(int,int) -> float; GetLineLength(int,int,int) -> float
CreateInternalShapeWithPoints(int,List[Tuple[float,float,int]],bool) -> int
AddSeamlinePairGroup(int,int,int,int,bool,bool) -> bool
AddSeamlinePairGroup(int,int,int,int,int,bool,bool) -> bool
AddSeamlinePairGroup(int,int,int,int,int,int,bool,bool) -> bool
AddSeamlinePairGroupPartial(int,int,float,float,bool,int,int,float,float,bool) -> int
AddSeamlinePairGroupPartial(int,int,float,float,bool,int,int,int,float,float,bool) -> int
AddSeamlinePairGroupPartial(int,int,int,float,float,bool,int,int,int,float,float,bool) -> int
GetSeamlinePairGroupCount() -> int
GetSeamlinePairGroupListInPattern(int) -> List[int]
GetArrangementOfPattern() -> List[Dict[str,str]]
GetArrangementOfPattern(int) -> Dict[str,str]
GetArrangementOfPattern(str) -> Dict[str,str]
SetArrangement(int,int) -> None
GetMeshCountByType(int) -> Dict[str,str]
GetMeshCountByType(str) -> Dict[str,str]
GetParticleDistanceOfPattern(int) -> float
GetParticleDistanceOfPattern(str) -> float
SetParticleDistanceOfPattern(int,float) -> None
GetPatternInformation(int) -> str
GetPatternComponents(int=-1,List[str]=[]) -> str
```

Read-only outline/components/line info нужны до контрактов sewing/internal lines.
Count швов не доказывает правильную пару линий/направление; нужен независимый
критерий. Dict[str,str] в native API нельзя автоматически считать numeric JSON.

## Что ещё не проверено

- Все остальные docstrings пяти модулей, другие bindings/modules/types/options.
- Native calls этих методов, units/enum meanings и поведение ошибок/диалогов.
- Полная построчная сверка с официальной актуальной документацией.
- Эквивалентность перегрузок/aliases и корректность сторонних handlers.

Следующая обязательная задача — W0 в `docs/CLO_API_COVERAGE_PLAN.md`, не
массовая публикация этих методов в MCP. Реальный gate — совместная приёмка
выбранной волны после отдельной реализации и свежего запуска CLO.
