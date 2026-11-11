"""Guided, read-only lessons for the CLO MCP server.

A lesson is a short sequence of steps. Each step carries instructions and a pure
check over a bounded read-only snapshot (patterns, seam groups, arrangement and
avatars). The caller performs scene edits with the existing tools; this module
only verifies and advances server-local progress.

Rules:
- no scene mutation and no native command other than four read-only getters;
- no files, IPC or retries;
- progress lives in one MCP service and is lost on restart;
- failed checks do not advance the step and never trigger cleanup.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

LESSON_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
READ_COMMANDS = ("get_pattern_list", "get_seamline_pairs", "get_arrangement", "get_avatars")
COPY_PREFIX = "LESSON_"


class LessonError(ValueError):
    """A fixed public lesson error code, never a native exception."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Check:
    passed: bool
    evidence: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class Snapshot:
    patterns: tuple[dict, ...]
    seam_count: int
    seam_patterns: dict[int, tuple[int, ...]]
    arrangement_names: dict[int, str]
    arrangement_count: int
    avatars: tuple[dict, ...]

    @classmethod
    def from_results(cls, patterns, seams, arrangement, avatars):
        try:
            pattern_list = patterns["patterns"]
            seam_list = seams["patterns"]
            piece_list = arrangement["pieces"]
            avatar_list = avatars["avatars"]
            seam_count = seams["seam_count"]
            arrangement_count = arrangement["pattern_count"]
            if (type(pattern_list) is not list or type(seam_list) is not list
                    or type(piece_list) is not list or type(avatar_list) is not list
                    or type(seam_count) is not int or seam_count < 0
                    or type(arrangement_count) is not int or arrangement_count < 0
                    or len(pattern_list) > 256 or len(piece_list) > 256
                    or len(avatar_list) > 64 or seam_count > 4096):
                raise ValueError
            patterns_norm = []
            for item in pattern_list:
                if (type(item) is not dict or type(item.get("index")) is not int
                        or not 0 <= item["index"] < 256
                        or type(item.get("name")) is not str
                        or not 1 <= len(item["name"]) <= 128):
                    raise ValueError
                patterns_norm.append({"index": item["index"], "name": item["name"]})
            seam_map = {}
            for item in seam_list:
                if (type(item) is not dict or type(item.get("pattern_index")) is not int
                        or not 0 <= item["pattern_index"] < 256
                        or type(item.get("group_indices")) is not list
                        or len(item["group_indices"]) > 4096):
                    raise ValueError
                groups = tuple(item["group_indices"])
                if any(type(g) is not int or not 0 <= g < 4096 for g in groups):
                    raise ValueError
                seam_map[item["pattern_index"]] = groups
            arrangement_names = {}
            for item in piece_list:
                if (type(item) is not dict or type(item.get("pattern_index")) is not int
                        or not 0 <= item["pattern_index"] < 256
                        or type(item.get("pattern_name")) is not str
                        or type(item.get("arrangement_name")) is not str):
                    raise ValueError
                arrangement_names[item["pattern_index"]] = item["arrangement_name"]
            avatars_norm = []
            for item in avatar_list:
                if (type(item) is not dict or type(item.get("index")) is not int
                        or type(item.get("name")) is not str):
                    raise ValueError
                avatars_norm.append({"index": item["index"], "name": item["name"]})
        except (KeyError, TypeError, ValueError):
            raise LessonError("lesson_check_unavailable") from None
        return cls(
            patterns=tuple(patterns_norm),
            seam_count=seam_count,
            seam_patterns=seam_map,
            arrangement_names=arrangement_names,
            arrangement_count=arrangement_count,
            avatars=tuple(avatars_norm),
        )

    def names(self) -> set[str]:
        return {item["name"] for item in self.patterns}

    def by_name(self, name: str):
        return next((item for item in self.patterns if item["name"] == name), None)

    def copy_names(self) -> list[str]:
        return sorted(name for name in self.names() if name.startswith(COPY_PREFIX))

    def group_owners(self) -> dict[int, set[int]]:
        owners: dict[int, set[int]] = {}
        for pattern_index, groups in self.seam_patterns.items():
            for group in groups:
                owners.setdefault(group, set()).add(pattern_index)
        return owners


def _fail_if_shared(snapshot: Snapshot, selected: set[int]) -> list[str]:
    """Return evidence lines for groups that connect a selected pattern to another."""
    problems = []
    owners = snapshot.group_owners()
    for pattern_index, groups in snapshot.seam_patterns.items():
        if pattern_index not in selected:
            continue
        for group in groups:
            connected = owners.get(group, set()) - {pattern_index}
            if connected:
                problems.append("group %d links pattern %d to %s" % (
                    group, pattern_index, sorted(connected)))
    return problems


def check_tee_audit(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    evidence = (
        "patterns=%d" % len(snapshot.patterns),
        "seams=%d" % snapshot.seam_count,
        "arrangements=%d" % snapshot.arrangement_count,
        "avatars=%d" % len(snapshot.avatars),
    )
    passed = (len(snapshot.patterns) == 5 and snapshot.seam_count > 0
              and snapshot.arrangement_count == 5 and len(snapshot.avatars) >= 1)
    return Check(passed, evidence, "" if passed else
                 "Нужны 5 деталей, 1+ аватар, arrangement для всех 5 и существующие швы.")


def check_tee_copies(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    copies = [item for item in snapshot.patterns if item["name"].startswith(COPY_PREFIX)]
    names = [item["name"] for item in copies]
    copy_indices = {item["index"] for item in copies}
    evidence = ["copies=%d" % len(copies), "patterns=%d" % len(snapshot.patterns)]
    problems = []
    if len(copies) != 5 or len(set(names)) != 5:
        problems.append("нужно ровно 5 уникальных копий с префиксом %s" % COPY_PREFIX)
    if len(snapshot.patterns) != 10:
        problems.append("ожидается 10 деталей: 5 оригиналов + 5 копий")
    owners = snapshot.group_owners()
    for item in copies:
        groups = snapshot.seam_patterns.get(item["index"], ())
        evidence.append("%s groups=%d" % (item["name"], len(groups)))
        for group in groups:
            connected = owners.get(group, set()) - {item["index"]}
            if connected:
                problems.append("%s: группа %d связана с %s" % (item["name"], group, sorted(connected)))
    return Check(not problems, tuple(evidence), "; ".join(problems) if problems else "Копии созданы, общих швов с оригиналами нет.")


def check_tee_originals_removed(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    names = snapshot.names()
    copies = snapshot.copy_names()
    evidence = ("patterns=%d" % len(snapshot.patterns), "copies=%d" % len(copies))
    problems = []
    if len(snapshot.patterns) != 5 or len(copies) != 5:
        problems.append("ожидается 5 деталей, все с префиксом %s" % COPY_PREFIX)
    if names != set(copies):
        problems.append("остались имена без префикса %s" % COPY_PREFIX)
    owners = snapshot.group_owners()
    shared = [group for group, items in owners.items() if len(items) > 1]
    if shared:
        problems.append("копии уже сшиты между собой: группы %s" % sorted(shared))
    return Check(not problems, tuple(evidence), "; ".join(problems) if problems else "Оригиналы убраны, копии не сшиты между собой.")


def check_tee_arranged(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    copies = [item for item in snapshot.patterns if item["name"].startswith(COPY_PREFIX)]
    evidence = ["copies=%d" % len(copies), "avatars=%d" % len(snapshot.avatars)]
    problems = []
    if len(copies) != 5:
        problems.append("нужно 5 копий")
    if not snapshot.avatars:
        problems.append("нет загруженного аватара")
    for item in copies:
        name = snapshot.arrangement_names.get(item["index"], "")
        evidence.append("%s arrangement=%s" % (item["name"], name or "<none>"))
        if not name or name == "Arrangement Point":
            problems.append("%s без назначенной точки (default)" % item["name"])
    return Check(not problems, tuple(evidence), "; ".join(problems) if problems else "Все копии имеют arrangement point.")


def check_tube_panels(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    names = snapshot.names()
    present = {"LESSON_TUBE_A", "LESSON_TUBE_B"} <= names
    evidence = ("patterns=%d" % len(snapshot.patterns), "seams=%d" % snapshot.seam_count)
    problems = [] if present else ["нужны LESSON_TUBE_A и LESSON_TUBE_B"]
    if present:
        problems.extend(_fail_if_shared(snapshot, {
            snapshot.by_name("LESSON_TUBE_A")["index"],
            snapshot.by_name("LESSON_TUBE_B")["index"],
        }))
    return Check(not problems, evidence, "; ".join(problems) if problems else "Обе панели готовы и не сшиты.")


def _tube_common(snapshot: Snapshot, baseline: Snapshot | None, target: int) -> Check:
    names = snapshot.names()
    present = {"LESSON_TUBE_A", "LESSON_TUBE_B"} <= names
    delta = snapshot.seam_count - (baseline.seam_count if baseline else snapshot.seam_count)
    evidence = ("seams=%d" % snapshot.seam_count, "delta=%d" % delta, "target=%d" % target)
    problems = [] if present else ["нужны LESSON_TUBE_A и LESSON_TUBE_B"]
    if delta != target:
        problems.append("ожидается сдвиг seam_count на %d, получено %d" % (target, delta))
    return Check(not problems, evidence, "; ".join(problems) if problems else "Шов добавлен, счётчик совпал.")


def check_tube_first_seam(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    return _tube_common(snapshot, baseline, 1)


def check_tube_second_seam(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    return _tube_common(snapshot, baseline, 2)


def check_tube_review(snapshot: Snapshot, baseline: Snapshot | None) -> Check:
    names = snapshot.names()
    present = {"LESSON_TUBE_A", "LESSON_TUBE_B"} <= names
    evidence = ("patterns=%d" % len(snapshot.patterns), "avatars=%d" % len(snapshot.avatars))
    problems = [] if present else ["нужны LESSON_TUBE_A и LESSON_TUBE_B"]
    if not snapshot.avatars:
        problems.append("нет загруженного аватара")
    if baseline and snapshot.seam_count != baseline.seam_count + 2:
        problems.append("ожидается ровно два новых шва; сейчас %d" % (snapshot.seam_count - baseline.seam_count))
    return Check(not problems, evidence, "; ".join(problems) if problems else "Труба собрана: два боковых шва, аватар загружен.")


@dataclass(frozen=True)
class LessonStep:
    id: str
    title: str
    instructions: str
    tools: tuple[str, ...]
    check: Callable[[Snapshot, Snapshot | None], Check]


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    summary: str
    steps: tuple[LessonStep, ...]


TEE_TITLE = "Копия кроя без швов и посадка по arrangement points"
TUBE_TITLE = "Труба из двух панелей: два боковых шва"

LESSONS = (
    Lesson(
        id="tee_copy_place",
        title=TEE_TITLE,
        summary="Скопировать 5 деталей футболки, убрать оригиналы и посадить копии на аватар по arrangement points. Без сшивания и simulation.",
        steps=(
            LessonStep(
                id="audit",
                title="Аудит сцены",
                instructions=(
                    "Прочитай сцену без изменений: `get_pattern_list`, `get_seamline_pairs`, "
                    "`get_arrangement`, `get_avatars`. Ожидается 5 деталей, 1+ аватар, "
                    "arrangement у всех 5 и существующие швы. Сделай 2D/3D скриншот как baseline."
                ),
                tools=("get_pattern_list", "get_seamline_pairs", "get_arrangement",
                       "get_avatars", "get_3d_screenshot", "export_snapshot_2d"),
                check=check_tee_audit,
            ),
            LessonStep(
                id="copy",
                title="Копии без garment-швов",
                instructions=(
                    "Скопируй каждую из 5 деталей через `copy_pattern_with_offset`: имя "
                    "`LESSON_<исходное>`, смещение в свободную 2D-зону, по одной детали. "
                    "После каждой копии читай `get_seamline_pairs`. Ожидается: боди/спинка — "
                    "0 групп, рукава/воротник — 1 внутренняя группа. Если группа общая с "
                    "оригиналом — STOP, не удаляй оригиналы. Оригиналы пока не трогай."
                ),
                tools=("get_pattern_list", "copy_pattern_with_offset", "get_seamline_pairs",
                       "get_arrangement"),
                check=check_tee_copies,
            ),
            LessonStep(
                id="remove_originals",
                title="Убрать оригиналы",
                instructions=(
                    "Сначала проверь, что все 5 копий на месте и не имеют общих швов с "
                    "оригиналами. Затем удаляй оригиналы по одному через `delete_pattern` "
                    "с fresh `get_pattern_list`; копии `LESSON_*` не удаляй. После каждого "
                    "удаления читай список заново: индексы сдвигаются. Ожидается 5 деталей, "
                    "все с префиксом LESSON_. Удаление необратимо: только расходная сцена "
                    "или сохранённый проект; без auto-retry и cleanup."
                ),
                tools=("get_pattern_list", "delete_pattern", "get_seamline_pairs"),
                check=check_tee_originals_removed,
            ),
            LessonStep(
                id="place",
                title="Посадка по arrangement points",
                instructions=(
                    "Проверь `get_arrangement`: копии наследуют точки. Если точку нужно "
                    "сменить, возьми `arrangement_index` из `get_arrangement_list` и вызови "
                    "`set_arrangement` со свежими index/name. `set_arrangement_orientation` "
                    "и `set_arrangement_position` не двигают деталь визуально — не используй "
                    "их для посадки. Сделай front/back/side скриншоты. Без швов simulation "
                    "уронит детали, поэтому на этом шаге её не запускай."
                ),
                tools=("get_arrangement", "get_arrangement_list", "set_arrangement",
                       "export_view_image", "get_3d_screenshot"),
                check=check_tee_arranged,
            ),
        ),
    ),
    Lesson(
        id="two_panel_tube",
        title=TUBE_TITLE,
        summary="Создать две панели 120x80, сшить левую и правую боковые кромки, проверить seam_count и направление без перекрёста.",
        steps=(
            LessonStep(
                id="panels",
                title="Две панели",
                instructions=(
                    "Создай `LESSON_TUBE_A` в [1500,0] и `LESSON_TUBE_B` в [1500,200] "
                    "через `create_pattern` (120x80 мм, прямые точки). Прочитай "
                    "`get_pattern_lines` для обеих и определи физические концы кромок по "
                    "`start_mm`/`end_mm`; не полагайся только на `location`."
                ),
                tools=("create_pattern", "get_pattern_list", "get_pattern_lines"),
                check=check_tube_panels,
            ),
            LessonStep(
                id="left_seam",
                title="Левый боковой шов",
                instructions=(
                    "Сшей левую кромку A с левой кромкой B одним `add_seamline_pair`. "
                    "Направления выбери по физическим концам (верх↔верх, низ↔низ), не "
                    "предполагай True/True. Проверь `verified:true` и рост seam_count на 1; "
                    "сделай 3D-скриншот."
                ),
                tools=("get_pattern_lines", "add_seamline_pair", "get_3d_screenshot"),
                check=check_tube_first_seam,
            ),
            LessonStep(
                id="right_seam",
                title="Правый боковой шов",
                instructions=(
                    "Сшей правую кромку A с правой кромкой B вторым `add_seamline_pair`. "
                    "Проверь seam_count +2 от baseline и отсутствие перекрёста на 3D-скриншоте. "
                    "Если виден перекрёст — STOP, не добавляй третий шов; разбери направления."
                ),
                tools=("get_pattern_lines", "add_seamline_pair", "get_3d_screenshot"),
                check=check_tube_second_seam,
            ),
            LessonStep(
                id="review",
                title="Проверка трубы",
                instructions=(
                    "Запусти `simulate(60)` при наличии аватара и сделай 3D-скриншот. "
                    "Проверь, что труба не перекручена и держится; это visual-only, не fit "
                    "acceptance. Не добавляй швы и не делай cleanup после ошибки."
                ),
                tools=("simulate", "get_3d_screenshot", "get_pattern_list"),
                check=check_tube_review,
            ),
        ),
    ),
)

LESSON_BY_ID = {lesson.id: lesson for lesson in LESSONS}


def catalog() -> list[dict]:
    return [
        {
            "id": lesson.id,
            "title": lesson.title,
            "summary": lesson.summary,
            "steps": [{"id": step.id, "title": step.title} for step in lesson.steps],
        }
        for lesson in LESSONS
    ]


def _step_view(lesson: Lesson, index: int):
    step = lesson.steps[index]
    return {
        "index": index,
        "id": step.id,
        "title": step.title,
        "instructions": step.instructions,
        "tools": list(step.tools),
    }


class LessonRunner:
    """One current lesson and its progress; owned by one MCP service."""

    def __init__(self):
        self._lesson: Lesson | None = None
        self._step = 0
        self._completed: list[str] = []
        self._last_check: dict | None = None
        self._baseline: Snapshot | None = None

    def start(self, lesson_id: str) -> dict:
        lesson = LESSON_BY_ID.get(lesson_id)
        if lesson is None:
            raise LessonError("lesson_not_found")
        self._lesson = lesson
        self._step = 0
        self._completed = []
        self._last_check = None
        self._baseline = None
        return self.state()

    def reset(self) -> dict:
        had_lesson = self._lesson is not None
        self.__init__()
        return {"ok": True, "reset": had_lesson, "status": "not_started"}

    def state(self) -> dict:
        if self._lesson is None:
            return {"ok": True, "status": "not_started", "lesson": None,
                    "progress": {"completed": 0, "total": 0},
                    "current_step": None, "last_check": None}
        total = len(self._lesson.steps)
        completed = len(self._completed)
        status = "completed" if completed >= total else "in_progress"
        return {
            "ok": True,
            "status": status,
            "lesson": {"id": self._lesson.id, "title": self._lesson.title,
                       "summary": self._lesson.summary},
            "progress": {"completed": completed, "total": total},
            "current_step": None if status == "completed" else _step_view(self._lesson, self._step),
            "last_check": self._last_check,
        }

    async def check(self, service) -> dict:
        if self._lesson is None:
            raise LessonError("lesson_not_started")
        if self._step >= len(self._lesson.steps):
            return {**self.state(), "passed": True, "evidence": [],
                    "message": "Урок уже завершён."}
        snapshot = await collect_snapshot(service)
        if self._baseline is None:
            self._baseline = snapshot
        step = self._lesson.steps[self._step]
        result = step.check(snapshot, self._baseline)
        self._last_check = {"step_id": step.id, "passed": result.passed,
                            "evidence": list(result.evidence),
                            "message": result.message}
        if result.passed:
            self._completed.append(step.id)
            self._step += 1
        return {**self.state(), "passed": result.passed,
                "evidence": list(result.evidence), "message": result.message}


async def collect_snapshot(service) -> Snapshot:
    """Four bounded read-only getters; never a mutation."""
    results = {}
    for command in READ_COMMANDS:
        result = await service.call(command, {})
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise LessonError("lesson_check_unavailable")
        results[command] = result
    return Snapshot.from_results(
        results["get_pattern_list"], results["get_seamline_pairs"],
        results["get_arrangement"], results["get_avatars"],
    )
