"""The screenshot tool returns MCP image content from a bounded PNG file."""

import asyncio
from pathlib import Path

import clo3d_mcp.transport_server as ts

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def fake_service(tmp_path):
    service = ts.Service("unused", "s", b"k" * 32, 123, None, pattern_package=True)

    async def call(command, params=None):
        assert command == "get_3d_screenshot"
        path = Path(params["output_path"])
        path.write_bytes(PNG)
        return {"ok": True, "verified": True, "bytes": len(PNG)}

    service.call = call
    return service


def test_screenshot_returns_image_content(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SCREENSHOT_DIR", tmp_path)

    async def scenario():
        result = await ts.build_mcp(fake_service(tmp_path)).call_tool("get_3d_screenshot", {})
        assert isinstance(result, list) and len(result) == 1
        image = result[0]
        assert image.type == "image" and image.mimeType == "image/png"
        return image

    image = asyncio.run(scenario())
    assert image.data and len(image.data) > 0


def test_standard_view_and_2d_snapshot_return_images(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SCREENSHOT_DIR", tmp_path)
    service = ts.Service("unused", "s", b"k" * 32, 123, None, pattern_package=True)

    async def call(command, params=None):
        name = {"export_view_image": "native_view.png",
                "export_snapshot_2d": "native_flat.png"}[command]
        (tmp_path / name).write_bytes(PNG)
        return {"ok": True, "verified": True, "file_name": name, "bytes": len(PNG)}

    service.call = call

    async def scenario():
        mcp = ts.build_mcp(service)
        view = await mcp.call_tool("export_view_image", {
            "view": 2, "width": 800, "height": 600, "fit_all_objects": True})
        flat = await mcp.call_tool("export_snapshot_2d", {})
        return view, flat

    view, flat = asyncio.run(scenario())
    assert view[0].mimeType == "image/png" and flat[0].mimeType == "image/png"


def test_screenshot_rejects_non_image_output(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SCREENSHOT_DIR", tmp_path)
    service = fake_service(tmp_path)

    async def call(command, params=None):
        Path(params["output_path"]).write_bytes(b"not an image")
        return {"ok": True, "verified": True, "bytes": 12}

    service.call = call

    async def scenario():
        return await ts.build_mcp(service).call_tool("get_3d_screenshot", {})

    result = asyncio.run(scenario())
    assert getattr(result, "isError", False) is True
