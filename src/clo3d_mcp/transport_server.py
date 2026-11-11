"""Official FastMCP Streamable HTTP, one CLO-bound process and external FIFO."""

import asyncio
from contextlib import suppress
import os
import json
from pathlib import Path
import socket
import time
from typing import Any
from pydantic import StrictBool, StrictFloat, StrictInt, StrictStr

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
import uvicorn

from clo3d_mcp import BUILD
from clo3d_mcp.async_jobs import AsyncJobQueue
from clo3d_mcp.jobs import QueueError
from clo3d_mcp.lessons import LESSON_ID, LessonError, LessonRunner, catalog as lesson_catalog
from clo3d_mcp.protocol import SERVICE_CAPABILITIES, PATTERN_CAPABILITIES, ProtocolError, message
from clo3d_mcp.pattern_contract import PATTERN_COMMANDS, CommandError, validate_params
from clo3d_mcp.queue_session import QueueSession
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe
from clo3d_mcp.transport.winprocess import ProcessHandle


def tool_error(code):
    data = {"ok": False, "error": code}
    if code in ("scene_change_unverified", "outcome_unknown", "executor_release_timeout", "executor_release_unavailable"):
        data["scene_may_have_changed"] = True
    return CallToolResult(isError=True, structuredContent=data,
                          content=[TextContent(type="text", text=json.dumps(data))])


def image_content(path):
    """Return bounded PNG/JPEG MCP content for one validated screenshot file."""
    try:
        data = path.read_bytes()
    except OSError:
        return tool_error("invalid_native_result")
    if not 0 < len(data) <= MAX_SCREENSHOT_BYTES:
        return tool_error("invalid_native_result")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return Image(data=data, format="png")
    if data.startswith(b"\xff\xd8"):
        return Image(data=data, format="jpeg")
    return tool_error("invalid_native_result")


# Tools without parameters: the raw payload must be exactly {} (or omitted).
# PATTERN_COMMANDS get the same exact-key check through validate_params.
NO_ARG_COMMANDS = frozenset({"ping", "get_pattern_count", "transport_status",
                             "get_session_info", "create_test_rectangle",
                             "get_arrangement_list", "get_seamline_pairs",
                             "get_pattern_avatar_attachments", "export_pattern_json"})
LESSON_ACTIONS = frozenset({"list", "start", "state", "check", "reset"})
SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "acceptance-output" / "screenshots"
PATTERN_JSON_DIR = Path(__file__).resolve().parents[2] / "acceptance-output" / "pattern_json"
MAX_SCREENSHOT_BYTES = 16777216


class SessionMCP(FastMCP):
    async def call_tool(self, name, arguments):
        # Official SDK 1.26 defaults to ignoring extra arguments and pre-parses
        # JSON strings. Validate the RAW payload before either happens.
        if name in NO_ARG_COMMANDS and arguments not in (None, {}):
            return tool_error("invalid_parameters")
        if name == "lesson":
            if not isinstance(arguments, dict) or arguments.get("action") not in LESSON_ACTIONS:
                return tool_error("invalid_parameters")
            action = arguments["action"]
            if action == "start":
                lesson_id = arguments.get("lesson_id")
                if (set(arguments) != {"action", "lesson_id"}
                        or not isinstance(lesson_id, str)
                        or not LESSON_ID.fullmatch(lesson_id)):
                    return tool_error("invalid_parameters")
            elif set(arguments) != {"action"}:
                return tool_error("invalid_parameters")
        server_generated = {"get_3d_screenshot", "export_view_image", "export_snapshot_2d",
                            "export_pattern_json"}
        if name in PATTERN_COMMANDS and name not in server_generated:
            try:
                validate_params(name, arguments)
            except CommandError:
                return tool_error("invalid_parameters")
        return await super().call_tool(name, arguments)


class Service:
    def __init__(self, name, session_id, key, client_pid, parent, port=8765, pattern_package=False):
        self.name, self.key, self.client_pid = name, key, client_pid
        self.parent, self.port = parent, port
        self.queue = AsyncJobQueue(session_id)
        self.pattern_package = pattern_package
        self.lessons = LessonRunner()
        self.capabilities = PATTERN_CAPABILITIES if pattern_package else SERVICE_CAPABILITIES
        self.session = QueueSession(self.queue, key, client_pid, self.capabilities)
        self.http_serving = False
        self.executor_verified = False
        self.ready_announced = False
        self.ready_acknowledged = False
        self.failure = None
        self.stop_requested = False

    def status(self):
        queue = self.queue.status()
        return dict(queue, http_serving=self.http_serving,
                    executor_verified=self.executor_verified,
                    executor_build=self.session.executor_build,
                    ready=self.http_serving and self.executor_verified and self.ready_acknowledged
                    and queue["connected"] and not queue["closed"]
                    and not queue["quarantined"] and not self.stop_requested,
                    endpoint="http://127.0.0.1:%d/mcp" % self.port, error=self.failure)

    async def call(self, command, params=None):
        try:
            if not self.status()["ready"]:
                raise QueueError("executor_unavailable")
            if params is not None:
                validate_params(command, params)
            # RESULT is not READY. Observe release of exactly our completed job,
            # outside CLO's UI callback, before returning a composable success.
            return {"ok": True, **(await self.queue.call(command, params=params, release_timeout=2.0))}
        except (QueueError, CommandError, ProtocolError) as exc:
            code = exc.code if isinstance(exc, (QueueError, CommandError)) else "invalid_parameters"
            return tool_error(code)


def build_mcp(service):
    """No handles/tasks at import. SDK retains its own Host/Origin middleware."""
    mcp = SessionMCP(
        "CLO session", host="127.0.0.1", port=service.port,
        streamable_http_path="/mcp", json_response=True, log_level="ERROR",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:%d" % service.port], allowed_origins=[]),
        instructions="One disposable CLO scene. Never automatically retry outcome_unknown or a scene mutation.",
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @mcp.tool(annotations=read)
    async def ping() -> dict[str, Any]:
        """Round trip through FIFO to the CLO UI executor, not an HTTP health ping.

        Returns pong:true only after the executor handled it. Read-only; an
        unknown outcome is never retried automatically.
        """
        return await service.call("ping")

    @mcp.tool(annotations=read)
    async def get_pattern_count() -> dict[str, Any]:
        """Read the number of pattern pieces through the sequential CLO executor.

        Read-only, bounded to 256 pieces. Indices are positional, not durable IDs.
        """
        return await service.call("get_pattern_count")

    @mcp.tool(annotations=read)
    async def transport_status() -> dict[str, Any]:
        """External queue/HTTP state; responds even while a CLO API call is busy.

        Describes transport readiness only, never whether a specific scene
        command completed.
        """
        return service.status()

    @mcp.tool(annotations=read)
    async def get_session_info() -> dict[str, Any]:
        """CLO session identity and readiness (not the MCP HTTP session identity).

        Returns CLO/server PIDs and the executor capability list. A session
        change invalidates cached pattern indices.
        """
        return dict(service.status(), clo_pid=service.client_pid, server_pid=os.getpid(),
                    server_build=BUILD, capabilities=list(service.capabilities))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=False, openWorldHint=False))
    async def create_test_rectangle() -> dict[str, Any]:
        """Add ONE fixed 100 x 100 mm diagnostic square at the 2D origin.

        Mutates the disposable scene; no arbitrary geometry/exec. Returns
        count/geometry readback; ok:false or a timeout may still follow a scene
        effect, so never retry automatically.
        """
        return await service.call("create_test_rectangle")

    if service.pattern_package:
        add_pattern_tools(mcp, service, read)
    return mcp


def add_pattern_tools(mcp, service, read):
    """Explicit tools only; no registration of arbitrary CLO functions."""
    mutation = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                               idempotentHint=False, openWorldHint=False)
    artifact = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                               idempotentHint=False, openWorldHint=False)

    @mcp.tool(annotations=read)
    async def list_clo_api() -> dict[str, Any]:
        """List public callable names in five fixed CLO modules, without invoking them.

        Presence is not proof that a native call is safe or compatible.
        """
        return await service.call("list_clo_api", {})

    @mcp.tool(annotations=read)
    async def describe_clo_api(module: StrictStr, functions: list[StrictStr]) -> dict[str, Any]:
        """Read bounded docstrings/signatures, not execute API. At most 16 public names."""
        return await service.call("describe_clo_api", {"module": module, "functions": functions})

    @mcp.tool(annotations=read)
    async def get_pattern_list() -> dict[str, Any]:
        """Read indices/names; bounded to 256 pieces. Indices can change after deletion."""
        return await service.call("get_pattern_list", {})

    @mcp.tool(annotations=read)
    async def get_fabric_list() -> dict[str, Any]:
        """Read project Fabric indices/names from Object Browser; at most 256 fabrics.

        No arguments. Returns fabric_count and fabrics[{index,name}]. No colorway
        filter or selection. Indices are zero-based Object Browser indices, not
        durable IDs. Checks repeated count/names, not an atomic
        snapshot. Empty/duplicate names are preserved; no assignment or materials.
        inventory_limit/changed/invalid_native_result: stop, no automatic retry;
        do not use a partial list. Never import assets or switch colorway to recover.
        """
        return await service.call("get_fabric_list", {})

    @mcp.tool(annotations=read)
    async def get_avatars() -> dict[str, Any]:
        """Read loaded avatar indices/names in GetAvatarNameList order; at most 64.

        No arguments. Returns avatar_count and avatars[{index,name}], zero-based
        transient indices, not durable IDs. Checks repeated count/name lists, not
        geometry, pose, sizing or an atomic snapshot. Empty/duplicate names remain.
        No import or scene change. inventory_limit/changed/invalid_native_result:
        stop, no automatic retry or fallback; never import an avatar to recover.
        """
        return await service.call("get_avatars", {})

    @mcp.tool(annotations=read)
    async def get_pattern_fabric(pattern_index: StrictInt, expected_name: str) -> dict[str, Any]:
        """Read ONE uniquely named pattern's assigned Object Browser fabric index/name.

        Required pattern_index0-255 and exact expected_name1-128chars from fresh list.
        Returns pattern_index,pattern_name,fabric_index,fabric_name (no colorway).
        Up to256patterns/256fabrics; repeated mapping/list checks, not atomic IDs.
        No assignment/import. stale_pattern/inventory_changed/invalid_native_result:
        stop, no automatic retry/fallback; no undocumented unassigned sentinel.
        """
        return await service.call("get_pattern_fabric", {
            "pattern_index": pattern_index, "expected_name": expected_name})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                        idempotentHint=False, openWorldHint=False))
    async def assign_pattern_fabric(pattern_index: StrictInt, expected_name: str,
                                    fabric_index: StrictInt, expected_fabric_name: str,
                                    expected_current_fabric_index: StrictInt) -> dict[str, Any]:
        """Assign ONE Object Browser fabric to ONE uniquely named pattern; verify readback.

        Required indices0-255, exact unique pattern name1-128chars/fabric name0-256,
        expected_current_fabric_index from fresh get_pattern_fabric. Fixed native
        option1 (current application context only), no colorway selection/linking.
        Returns verified,pattern_index/name,fabric_index/name,previous_fabric_index,
        executor_ms. Checks all <=256 pattern mappings unchanged except target,
        fabric/name lists and target position/area/bbox. Not atomic or full material
        validation. stale_fabric/pattern stop before setter; post-entry errors may
        follow effect: no automatic retry, rollback or cleanup, even on False/error.
        """
        return await service.call("assign_pattern_fabric", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "fabric_index": fabric_index, "expected_fabric_name": expected_fabric_name,
            "expected_current_fabric_index": expected_current_fabric_index})

    @mcp.tool(annotations=read)
    async def get_pattern_geometry(pattern_index: StrictInt) -> dict[str, Any]:
        """Read 2D position in mm, area in mm2 and bounding box from CLO.

        Read-only, positional index0-255 from a fresh list. Position is the
        observed piece centre, not topology or full detail geometry.
        """
        return await service.call("get_pattern_geometry", {"pattern_index": pattern_index})

    @mcp.tool(annotations=read)
    async def get_pattern_outline(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Read ONE uniquely named pattern's boundary segment endpoints, not curve controls.

        Required real-pattern-list index0-255 and exact unique expected_name1-128
        from fresh get_pattern_list. Returns pattern_index/name,point_count1-512,
        points_mm[[x,y]],units=mm,coordinate_frame=bbox_top_left_y_down: origin at
        bounding-box TOP-LEFT, Y down, NOT global2D. Finite coordinates +/-100000mm.
        Native traversal order preserved; no closure/lineIndex correspondence,
        tessellation, sewing or internal lines. Up to256patterns, two endpoint reads
        and three list checks, not atomic identity or full geometry validation.
        Known limitation on CLO2026.1.336: every tested target returned
        invalid_native_result (own fixture empty at native level; two existing
        pieces rejected by the adapter), cause unestablished.
        Read-only; stale_pattern/inventory_changed/invalid_native_result/command_error:
        stop, no automatic retry/fallback; inspect readiness and fresh list separately.
        """
        return await service.call("get_pattern_outline", {
            "pattern_index": pattern_index, "expected_name": expected_name})

    @mcp.tool(annotations=read)
    async def get_pattern_lines(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Inspect ONE uniquely named pattern's outer lines without changing the scene.

        Required fresh real-pattern-list index0-255 and exact unique
        expected_name1-128 from get_pattern_list. Returns line_count,
        bounding_box_mm and one record per native outer line: line_index,
        length_mm, orientation, location, start_mm/end_mm/mid_mm and mid_norm
        (0..1 inside the bounding box). Coordinates are native 2D millimetres;
        on the tested fixture they matched create/geometry absolute API
        coordinates, not bbox-local, while Y direction and frame after
        move/rotate are not yet established. Lengths are native line lengths in
        mm; curve arc-vs-chord semantics are not established. Do not infer
        closure, seam/lineIndex topology, tessellation or graded points, and do
        not use this as an outline fallback. Bounded one native line-info read
        plus list/count checks, 1-512 lines, not an atomic identity.
        stale_pattern/inventory_changed/invalid_native_result/command_error:
        stop, no automatic retry or fallback.
        """
        return await service.call("get_pattern_lines", {
            "pattern_index": pattern_index, "expected_name": expected_name})

    @mcp.tool(annotations=read)
    async def get_arrangement() -> dict[str, Any]:
        """Read every pattern's current arrangement preset, offsets and orientation.

        Read-only. Returns pattern_index/name, arrangement name/type, native
        string offsets parsed as finite numbers and orientation; units are NOT
        established (native_unspecified), so do not call them mm/degrees or claim
        3D fit. Empty arrangement lists are not fit acceptance; no setters,
        drape or simulation are called. stale/inventory drift stops without retry.
        """
        return await service.call("get_arrangement")

    @mcp.tool(annotations=mutation)
    async def set_arrangement(pattern_index: StrictInt, expected_name: StrictStr,
                              arrangement_index: StrictInt) -> dict[str, Any]:
        """Assign ONE avatar arrangement point to ONE uniquely named pattern and ReDrape.

        Requires fresh index/unique name and a required arrangement_index from get_arrangement's
        library (0..library-1). Calls SetArrangement then ReDrape3DArrangement
        with ApiTypes.ImportExportOption flags; verifies the assigned preset and
        returns pattern/arrangement/offset/orientation/type. Offset units remain
        native_unspecified; 3D fit is visual-only. No retry/cleanup, no other
        patterns are reassigned, and errors after SetArrangement may leave the
        assignment applied.
        """
        return await service.call("set_arrangement", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "arrangement_index": arrangement_index})

    @mcp.tool(annotations=mutation)
    async def set_arrangement_orientation(pattern_index: StrictInt, expected_name: StrictStr,
                                          orientation: StrictInt) -> dict[str, Any]:
        """Set ONE arranged pattern's native orientation value and ReDrape; verify readback.

        Requires a fresh unique name/index and an integer orientation 0..359. The
        documented 2-argument SetArrangementOrientation is called, then
        ReDrape3DArrangement with the same ApiTypes.ImportExportOption flags as
        set_arrangement. Verification requires the readback orientation to equal
        the request after ReDrape and the arrangement name/offsets/type to stay
        unchanged; result mirrors set_arrangement. The native value's units and
        3D axis are not established (units native_unspecified), so fitting remains
        visual-only; a roll around the attachment point may not remove avatar
        intersections. No retry/cleanup; errors after the setter may leave the
        orientation applied.
        """
        return await service.call("set_arrangement_orientation", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "orientation": orientation})

    @mcp.tool(annotations=mutation)
    async def set_arrangement_position(pattern_index: StrictInt, expected_name: StrictStr,
                                       position_x: StrictInt, position_y: StrictInt,
                                       offset: StrictInt) -> dict[str, Any]:
        """Set ONE arranged pattern's native arrangement position and ReDrape.

        Native signature is (patternIndex, positionX, positionY, offset), not
        world x/y/z. Requires a fresh unique name/index and integers 0..100
        (observed range; units native_unspecified). Calls SetArrangementPosition,
        then ReDrape3DArrangement with the ApiTypes flags. Readback offsets must
        equal the requested triplet and name/orientation/type must stay unchanged.
        Whether this moves the piece in 3D is visual-only and unproven; it is not
        a free gizmo transform. No retry/cleanup; errors may leave the state applied.
        """
        return await service.call("set_arrangement_position", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "position_x": position_x, "position_y": position_y, "offset": offset})

    @mcp.tool(annotations=read)
    async def get_arrangement_list() -> dict[str, Any]:
        """Read the avatar arrangement-point library with names and presets.

        Read-only. Returns index/name/type/offset{x,y,z}/orientation for up to
        4096 points; offset/orientation units remain native_unspecified. Use the
        index with set_arrangement. No setter, drape or fit validation.
        """
        return await service.call("get_arrangement_list")

    @mcp.tool(annotations=read)
    async def get_seamline_pairs() -> dict[str, Any]:
        """Read seam group count/names and per-pattern seam group membership.

        Read-only; up to 4096 groups and 256 patterns. Group names and indices
        come from native seamline pair groups; membership is read per pattern.
        No delete/merge/partial-seam inspection; list drift stops without retry.
        """
        return await service.call("get_seamline_pairs")

    @mcp.tool(annotations=read)
    async def get_avatar_measurements(avatar_index: StrictInt) -> dict[str, Any]:
        """Read one loaded avatar's measurement names, types and lengths.

        Required before attaching a pattern edge to an avatar measure. Read-only;
        up to 512 measurements. Values use the native display unit reported per
        measurement; no pose, fit or measurement editing.
        """
        return await service.call("get_avatar_measurements", {
            "avatar_index": avatar_index})

    @mcp.tool(annotations=read)
    async def get_pattern_avatar_attachments() -> dict[str, Any]:
        """Read pattern-to-avatar-measure attachments and the scene pin count.

        Read-only; up to 1024 de-duplicated pairs. Pairs are keyed by names, so
        duplicate pattern names may collapse. No attach/detach; no fit claim.
        """
        return await service.call("get_pattern_avatar_attachments")

    @mcp.tool(annotations=mutation)
    async def set_arrangement_shape_style(pattern_index: StrictInt, expected_name: StrictStr,
                                          style: StrictStr) -> dict[str, Any]:
        """Set ONE arranged pattern's native shape style to Flat or Curved.

        Requires a fresh unique name/index. Calls SetArrangementShapeStyle and
        verifies the arrangement type readback; name/offset/orientation must stay
        unchanged. Visual drape effect is not established; no ReDrape or retry.
        Errors after the setter may leave the style applied.
        """
        return await service.call("set_arrangement_shape_style", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "style": style})

    @mcp.tool(annotations=mutation)
    async def set_pattern_edge_to_avatar_measure(pattern_index: StrictInt, expected_name: StrictStr,
                                                 line_index: StrictInt, avatar_measure: StrictStr,
                                                 attach: StrictBool) -> dict[str, Any]:
        """Attach or detach ONE whole pattern edge to an avatar measure (Line Pin).

        Requires a fresh unique name/index, a line index from get_pattern_lines,
        and a measurement name from get_avatar_measurements. Calls the native
        boolean setter, which runs the cloth solver afterwards, then verifies the
        attachment readback. Does not detach other edges; visual fit is separate.
        No retry; a false/mismatched result stops mutations.
        """
        return await service.call("set_pattern_edge_to_avatar_measure", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "line_index": line_index, "avatar_measure": avatar_measure,
            "attach": attach})

    @mcp.tool(annotations=mutation)
    async def simulate(steps: StrictInt) -> dict[str, Any]:
        """Run ONE bounded cloth simulation of 1..300 steps and verify the list.

        Requires a ready avatar and scene. Calls utility_api.Simulate once; the
        native boolean and unchanged pattern list/names are verified. This is
        visual-only: it does not prove a physically correct fit, and a client
        timeout does not cancel the native call. No retry or settings changes.
        """
        return await service.call("simulate", {"steps": steps})

    @mcp.tool(annotations=artifact)
    async def get_3d_screenshot() -> Any:
        """Capture the current CLO 3D window as a PNG and return the image.

        Writes one bounded file under acceptance-output/screenshots and returns
        image content, so the caller can inspect the result directly. No dialog,
        no scene change, no arbitrary output path. Empty/non-image/oversized
        output is an error; no automatic retry.
        """
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / ("3d_%d.png" % time.time_ns())
        result = await service.call("get_3d_screenshot", {"output_path": str(path)})
        if isinstance(result, CallToolResult):
            return result
        if not isinstance(result, dict) or result.get("ok") is not True:
            return tool_error("invalid_native_result")
        return image_content(path)

    @mcp.tool(annotations=artifact)
    async def export_view_image(view: StrictInt, width: StrictInt, height: StrictInt,
                                fit_all_objects: StrictBool) -> Any:
        """Render one standard 3D view and return it as an image.

        View indexes: 0 Bottom, 1 FrontRight, 2 Front, 3 FrontLeft, 4 Right,
        5 Top, 6 Left, 7 Custom, 8 Back. Writes one bounded file under
        acceptance-output/screenshots, independent of the current camera; no
        scene change. Native may append the colorway name to the file name.
        Empty/non-image/oversized output is an error; no retry.
        """
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / ("view_%d_%d.png" % (view, time.time_ns()))
        result = await service.call("export_view_image", {
            "output_path": str(path), "view": view, "width": width,
            "height": height, "fit_all_objects": fit_all_objects})
        if isinstance(result, CallToolResult):
            return result
        file_name = result.get("file_name") if isinstance(result, dict) else None
        if (not isinstance(file_name, str) or not file_name
                or Path(file_name).name != file_name):
            return tool_error("invalid_native_result")
        return image_content(SCREENSHOT_DIR / file_name)

    @mcp.tool(annotations=artifact)
    async def export_snapshot_2d() -> Any:
        """Capture the current 2D pattern window as an image and return it.

        Writes one bounded PNG/JPEG under acceptance-output/screenshots and
        returns image content. Uses the current 2D camera/zoom exactly as shown;
        no scene change, no dialog, no arbitrary path, no retry.
        """
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / ("view2d_%d.png" % time.time_ns())
        result = await service.call("export_snapshot_2d", {"output_path": str(path)})
        if isinstance(result, CallToolResult):
            return result
        file_name = result.get("file_name") if isinstance(result, dict) else None
        if (not isinstance(file_name, str) or not file_name
                or Path(file_name).name != file_name):
            return tool_error("invalid_native_result")
        return image_content(SCREENSHOT_DIR / file_name)

    @mcp.tool(annotations=mutation)
    async def set_camera_view(view: StrictInt, zoom_to_fit: StrictBool) -> dict[str, Any]:
        """Set one standard 3D camera view and optionally zoom to fit.

        Uses SetCamViewPoint, optional SetZoomView and Refresh3DWindow. View
        indexes match export_view_image. Camera-only effect: no scene mutation,
        no readback of the camera, visual confirmation only. No retry.
        """
        return await service.call("set_camera_view", {
            "view": view, "zoom_to_fit": zoom_to_fit})

    @mcp.tool(annotations=mutation)
    async def reset_cloth_arrangement() -> dict[str, Any]:
        """Restore the cloth shape to its state when it was loaded.

        Global cloth reset; discards the current simulation shape. Verifies the
        pattern list is unchanged; visual result only. No preflight avatar/pose
        validation, no retry or automatic cleanup.
        """
        return await service.call("reset_cloth_arrangement")

    @mcp.tool(annotations=mutation)
    async def import_avatar_measurements(csv_path: StrictStr) -> dict[str, Any]:
        """Apply ONE measurement CSV to the single current avatar.

        Requires an absolute existing .csv <=16MiB and exactly one loaded avatar.
        Uses import_api.ImportMeasurement, then verifies measurement count grew;
        before/after counts are returned. No path echo, no retry, no pose/fit
        claim. CSV format is native and not validated by this tool.
        """
        return await service.call("import_avatar_measurements", {
            "csv_path": csv_path})

    @mcp.tool(annotations=read)
    async def get_pattern_body_details() -> dict[str, Any]:
        """Read native body-region and semantic labels for all patterns.

        Read-only; parses GetPatternOnBodyDetails into upperBody/lowerBody
        arrays with patternName/index, arrangementPosition, semanticLabel,
        bodyRegion and patternPosition. Bounded JSON; no garment/fit validation.
        """
        return await service.call("get_pattern_body_details")

    @mcp.tool(annotations=read)
    async def get_pattern_details(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Read ONE piece's grain direction, category and classification.

        Required fresh unique index/name. Read-only; grain is native degrees
        (0 = vertical on the tested build); category/classification are native
        values, not durable IDs. No geometry or fit claim.
        """
        return await service.call("get_pattern_details", {
            "pattern_index": pattern_index, "expected_name": expected_name})

    @mcp.tool(annotations=mutation)
    async def set_pattern_grain_direction(pattern_index: StrictInt, expected_name: StrictStr,
                                          degrees: StrictInt | StrictFloat) -> dict[str, Any]:
        """Set ONE piece's grain direction in degrees and verify readback.

        Required fresh unique index/name and finite degrees 0..359. Verifies
        native readback (mod 360) and unchanged area/position/list. No retry;
        errors after the setter may leave the grain applied.
        """
        return await service.call("set_pattern_grain_direction", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "degrees": degrees})

    @mcp.tool(annotations=read)
    async def get_mesh_counts(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Read native face/vertex text counts by mesh type for ONE piece.

        Required fresh unique index/name. Read-only; up to 16 typed entries.
        Values are native text, not parsed faces/vertices; no simulation quality
        or geometry claim.
        """
        return await service.call("get_mesh_counts", {
            "pattern_index": pattern_index, "expected_name": expected_name})

    @mcp.tool(annotations=mutation)
    async def set_particle_distance(pattern_index: StrictInt, expected_name: StrictStr,
                                    distance: StrictInt | StrictFloat) -> dict[str, Any]:
        """Set ONE piece's simulation mesh size in mm and verify readback.

        Required fresh unique index/name and finite distance 1..1000 mm.
        Verifies native readback and unchanged area/position/list. Smaller is
        finer/slower; no simulation run or fit claim. No retry.
        """
        return await service.call("set_particle_distance", {
            "pattern_index": pattern_index, "expected_name": expected_name,
            "distance": distance})

    @mcp.tool(annotations=mutation)
    async def add_seamline_pair(pattern_a_index: StrictInt, expected_name_a: StrictStr,
                                line_a_index: StrictInt, pattern_b_index: StrictInt,
                                expected_name_b: StrictStr, line_b_index: StrictInt,
                                direction_a: StrictBool, direction_b: StrictBool) -> dict[str, Any]:
        """Sew ONE whole outer line of pattern A to ONE whole outer line of pattern B.

        Required fresh real-pattern indices/unique expected names and line indices
        from get_pattern_lines; directions are native booleans (true forward).
        Calls the 6-argument AddSeamlinePairGroup only; child overloads, partial
        ratios, topstitch, buttons and delete are not included. Verifies seam group
        count +1 and unchanged line lengths/geometry/order; returns seam_count.
        Native false/exception or mismatched readback is an error, never retried;
        no automatic cleanup. Not a material/3D/sewing-quality guarantee.
        """
        return await service.call("add_seamline_pair", {
            "pattern_a_index": pattern_a_index, "expected_name_a": expected_name_a,
            "line_a_index": line_a_index, "pattern_b_index": pattern_b_index,
            "expected_name_b": expected_name_b, "line_b_index": line_b_index,
            "direction_a": direction_a, "direction_b": direction_b})

    @mcp.tool(annotations=mutation)
    async def add_seamline_pair_partial(
            pattern_a_index: StrictInt, expected_name_a: StrictStr,
            line_a_index: StrictInt, start_ratio_a: StrictFloat | StrictInt,
            end_ratio_a: StrictFloat | StrictInt,
            pattern_b_index: StrictInt, expected_name_b: StrictStr,
            line_b_index: StrictInt, start_ratio_b: StrictFloat | StrictInt,
            end_ratio_b: StrictFloat | StrictInt,
            direction_a: StrictBool, direction_b: StrictBool) -> dict[str, Any]:
        """Sew sub-segments of two whole outer lines using normalized ratios.

        Required fresh indices/unique names and line indices from
        get_pattern_lines; ratios are line-relative 0..1 with start < end on
        each side. Direction=false exports descending ratios but native
        rejects descending input. Calls
        AddSeamlinePairGroupPartial; native success is int 0, never bool
        truthiness. Verifies seam_count +1 and unchanged line lengths/geometry.
        No automatic retry/cleanup; a non-zero result is an error, not success.
        """
        return await service.call("add_seamline_pair_partial", {
            "pattern_a_index": pattern_a_index, "expected_name_a": expected_name_a,
            "line_a_index": line_a_index, "start_ratio_a": start_ratio_a,
            "end_ratio_a": end_ratio_a,
            "pattern_b_index": pattern_b_index, "expected_name_b": expected_name_b,
            "line_b_index": line_b_index, "start_ratio_b": start_ratio_b,
            "end_ratio_b": end_ratio_b,
            "direction_a": direction_a, "direction_b": direction_b})

    @mcp.tool(annotations=mutation)
    async def import_avatar(file_path: StrictStr) -> dict[str, Any]:
        """Import ONE local .avt avatar through CLO's ImportAvatar, then verify count.

        Requires an absolute existing .avt path <=128MiB; the path is used only
        for this call and is not echoed. Verifies native true and avatar count +1;
        no auto retry, fallback to another importer, pose/measurement or 3D fit.
        """
        return await service.call("import_avatar", {"file_path": file_path})

    @mcp.tool(annotations=mutation)
    async def import_avatar_size(file_path: StrictStr) -> dict[str, Any]:
        """Apply ONE local .avs avatar-size file to the current avatar.

        Requires an absolute existing .avs <=16MiB and at least one avatar.
        Calls import_api.ImportFile, then reports GetAvatarMeasurements(0)
        before/after; a zero added count is possible because .avs is a size
        file, not a measurement CSV. No retry/cleanup; a failure after the
        native call may have changed avatar size.
        """
        return await service.call("import_avatar_size", {"file_path": file_path})

    @mcp.tool(annotations=mutation)
    async def import_dxf(file_path: StrictStr) -> dict[str, Any]:
        """Append ONE local .dxf pattern file and verify the pattern list grows.

        Requires an absolute existing .dxf <=64MiB. The adapter constructs
        ApiTypes.ImportDxfOption with append=true and notch import enabled when
        the build exposes those fields. Verifies native true, pattern count
        increase and returned new names; the path is not echoed. No arbitrary
        options, auto retry, cleanup or 3D/seam acceptance. A failure after the
        native call may have changed the scene.
        """
        return await service.call("import_dxf", {"file_path": file_path})

    @mcp.tool(annotations=mutation)
    async def import_pattern_json(file_path: StrictStr) -> dict[str, Any]:
        """Replace the scene from ONE native CLO pattern JSON and read it back.

        WARNING: the imported contract replaces the current scene, not append.
        Requires an absolute existing .json <=64MiB; calls
        pattern_api.ImportPatternJSON, then returns the post-import pattern list
        and seam group count. No automatic retry, merge, backup or cleanup: a
        false/mismatched result may still have changed the scene.
        """
        return await service.call("import_pattern_json", {"file_path": file_path})

    @mcp.tool(annotations=artifact)
    async def export_pattern_json() -> dict[str, Any]:
        """Export the native CLO pattern JSON to a server-generated artifact.

        Read-only scene effect: calls pattern_api.ExportPatternJSON to
        acceptance-output/pattern_json/current.json, verifies native true and a
        bounded file, then returns the file name/size and top-level keys. No
        arbitrary path, no import, no scene mutation or retry.
        """
        PATTERN_JSON_DIR.mkdir(parents=True, exist_ok=True)
        path = PATTERN_JSON_DIR / "current.json"
        result = await service.call("export_pattern_json", {"output_path": str(path)})
        if not result.get("ok"):
            return result
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return tool_error("invalid_native_result")
        if not isinstance(data, dict) or not data:
            return tool_error("invalid_native_result")
        return {**result, "top_level_keys": sorted(data)[:64]}

    @mcp.tool(annotations=mutation)
    async def create_pattern(points: list[list[StrictInt | StrictFloat]], name: StrictStr,
                             vertex_types: list[StrictInt] | None = None) -> dict[str, Any]:
        """Create ONE closed pattern from 3-64 [x,y] points in mm with a unique name.

        Optional vertex_types (same length; 0 straight, 2 spline, 3 Bezier) is
        passed to the native CreatePatternWithPoints. Without it every point is
        straight and self-intersection is rejected. Curve shape/control-point
        semantics and area consistency remain provisional until real evidence.
        Verifies count/name/area. No automatic retry or rollback on failure.
        """
        params = {"points": points, "name": name}
        if vertex_types is not None:
            params["vertex_types"] = vertex_types
        return await service.call("create_pattern", params)

    @mcp.tool(annotations=mutation)
    async def set_pattern_name(pattern_index: StrictInt, expected_name: StrictStr,
                               name: StrictStr) -> dict[str, Any]:
        """Rename a uniquely named piece after stale-index check; verify by reading back."""
        return await service.call("set_pattern_name", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "name": name})

    @mcp.tool(annotations=mutation)
    async def copy_pattern_with_offset(pattern_index: StrictInt, expected_name: StrictStr,
                                       name: StrictStr, dx: StrictInt | StrictFloat,
                                       dy: StrictInt | StrictFloat) -> dict[str, Any]:
        """Copy ONE piece by dx/dy mm, unique new name; verify count, position and area.

        Never retry automatically: a failed readback may follow a successful copy.
        """
        return await service.call("copy_pattern_with_offset", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "name": name, "dx": dx, "dy": dy})

    @mcp.tool(annotations=mutation)
    async def move_pattern_relative(pattern_index: StrictInt, expected_name: StrictStr,
                                    dx: StrictInt | StrictFloat, dy: StrictInt | StrictFloat) -> dict[str, Any]:
        """Move whole piece by dx/dy mm; verify actual displacement and unchanged area.

        Does NOT move individual pattern points. Never retry automatically.
        """
        return await service.call("move_pattern_relative", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "dx": dx, "dy": dy})

    @mcp.tool(annotations=mutation)
    async def delete_pattern(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Delete ONE uniquely named piece after stale-index check; verify remaining list.

        Indices shift. Read the list again before further operations. No automatic retry.
        """
        return await service.call("delete_pattern", {"pattern_index": pattern_index,
                                  "expected_name": expected_name})

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                         idempotentHint=False, openWorldHint=False))
    async def lesson(action: StrictStr, lesson_id: StrictStr | None = None) -> dict[str, Any]:
        """Run a guided lesson: list, start, state, check or reset.

        Actions: list returns the catalog; start(lesson_id) starts or restarts one
        lesson; state returns progress; check performs four bounded read-only reads
        (get_pattern_list, get_seamline_pairs, get_arrangement, get_avatars), checks
        the current step and advances only on pass; reset clears this service's
        lesson. Never mutates the CLO scene and never dispatches a native mutation:
        scene steps are performed by the caller with the listed tools. State is in
        memory per MCP service and is lost on restart. A failed check leaves the
        step unchanged; no retry, rollback or scene cleanup.
        """
        try:
            if action == "list":
                return {"ok": True, "lessons": lesson_catalog()}
            if action == "start":
                if lesson_id is None:
                    return tool_error("invalid_parameters")
                return service.lessons.start(lesson_id)
            if action == "state":
                return service.lessons.state()
            if action == "check":
                return await service.lessons.check(service)
            if action == "reset":
                return service.lessons.reset()
            return tool_error("invalid_parameters")
        except LessonError as exc:
            return tool_error(exc.code)


async def pipe_loop(service):
    pipe = Pipe.listen(service.name)
    channel = None
    startup_deadline = time.monotonic() + 30
    try:
        connect = pipe.connect()
        while connect.poll() is None:
            if not service.parent.alive():
                return
            if time.monotonic() >= startup_deadline:
                raise TimeoutError("Executor connection deadline")
            await asyncio.sleep(0.01)
        service.session.connect(pipe.peer_pid())
        channel = Channel(pipe, service.queue.session_id)
        verification_id = None
        while not service.stop_requested:
            if not service.parent.alive():
                return
            service.queue.tick()
            for frame in channel.poll():
                if frame["kind"] == "STOP":
                    if service.session.state != "active":
                        raise ProtocolError("Unauthenticated STOP")
                    service.stop_requested = True
                    return
                if frame["kind"] == "SERVICE_READY":
                    if not service.ready_announced or service.ready_acknowledged:
                        raise ProtocolError("Unexpected readiness acknowledgement")
                    service.ready_acknowledged = True
                    continue
                for response in service.session.receive(frame):
                    channel.send(response)
            if verification_id is None and service.queue.status()["ready"]:
                verification_id = service.queue.submit("ping", execution_timeout=15)
            if verification_id is not None and not service.executor_verified:
                outcome = service.queue.lookup(service.queue.session_id, verification_id)
                if outcome.state == "succeeded" and service.queue.status()["ready"]:
                    service.executor_verified = True
                elif outcome.state in ("failed", "unknown", "cancelled"):
                    raise ProtocolError("Executor verification failed")
            if service.http_serving and service.executor_verified and not service.ready_announced:
                # Isolated message: do not batch SERVICE_READY with a JOB.
                channel.send(message("SERVICE_READY", service.queue.session_id))
                service.ready_announced = True
            elif service.ready_acknowledged or not service.executor_verified:
                job = service.session.dispatch()
                if job is not None:
                    channel.send(job)
            if not service.ready_acknowledged and time.monotonic() >= startup_deadline:
                raise TimeoutError("Service readiness deadline")
            await asyncio.sleep(0.01)
    finally:
        service.session.disconnect()
        service.queue.close()
        pipe.begin_close()
        deadline = time.monotonic() + 2
        while not pipe.poll_close():
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.005)


async def run(service):
    # Exclusive bind, no SO_REUSEADDR: never hijack a busy Windows port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_task = pipe_task = None
    server = None
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", service.port))
        except OSError:
            service.failure = "http_bind_failed"
            raise
        sock.listen(64)
        sock.setblocking(False)
        mcp = build_mcp(service)
        config = uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=service.port,
                                log_level="error", access_log=False, proxy_headers=False,
                                timeout_graceful_shutdown=2, ws="none")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve(sockets=[sock]))
        pipe_task = asyncio.create_task(pipe_loop(service))
        while not server_task.done() and not pipe_task.done():
            service.http_serving = server.started
            await asyncio.sleep(0.01)
        if pipe_task.done():
            pipe_task.result()
        elif not service.stop_requested:
            server_task.result()
            raise RuntimeError("HTTP stopped unexpectedly")
        return 0
    finally:
        service.stop_requested = True
        service.http_serving = False
        service.queue.close()
        if pipe_task is not None:
            if not pipe_task.done():
                pipe_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pipe_task
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            with suppress(asyncio.CancelledError, Exception):
                await server_task
        sock.close()
        service.parent.close()


def main():
    parent = None
    service = None
    try:
        name = os.environ.pop("CLO_MCP_P1_PIPE")
        session_id = os.environ.pop("CLO_MCP_P1_SESSION")
        key = bytes.fromhex(os.environ.pop("CLO_MCP_P1_KEY"))
        client_pid = int(os.environ.pop("CLO_MCP_P1_CLO_PID"))
        parent = ProcessHandle(inherited=int(os.environ.pop("CLO_MCP_PARENT_HANDLE")))
        if len(key) != 32 or parent.pid() != client_pid or not parent.alive():
            return 2
        port = int(os.environ.pop("CLO_MCP_HTTP_PORT", "8765"))
        if not 1 <= port <= 65535:
            return 2
        pattern_package = os.environ.pop("CLO_MCP_PATTERN_PACKAGE", "0") == "1"
        service = Service(name, session_id, key, client_pid, parent, port=port,
                          pattern_package=pattern_package)
        return asyncio.run(run(service))
    except Exception:
        # A fixed exit code carries a useful startup diagnosis without IPC files
        # or stdout/stderr pipes, tracebacks, environment or credentials.
        return 3 if service is not None and service.failure == "http_bind_failed" else 1
    finally:
        if parent is not None:
            parent.close()


if __name__ == "__main__":
    raise SystemExit(main())
