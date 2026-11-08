"""Run in the same CLO Script Editor to stop P0, without importing its source."""

import builtins


def main():
    registry = getattr(builtins, "_clo3d_mcp_p0", None)
    if registry is None:
        print("[CLO P0] No probe in this interpreter")
        return
    if registry.get("version") != 1:
        raise RuntimeError("Unknown P0 registry; references left untouched")
    probe = registry.get("current")
    if probe is None:
        print("[CLO P0] No active probe")
        return
    probe.stop()
    # Do not clear builtins: native callback addresses may still be queued.


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P0] STOP_FAILED %s: %s" % (type(exc).__name__, exc))
