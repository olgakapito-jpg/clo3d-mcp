"""Stop/report only this CLO session's P1 diagnostic; no imports of runtime."""


def main(profile="p1"):
    import builtins

    if profile not in ("p1", "p2"):
        raise RuntimeError("Unknown diagnostic profile")
    registry = getattr(builtins, "_clo3d_mcp_" + profile, None)
    if registry is None:
        print("[CLO %s] No diagnostic in this interpreter" % profile.upper())
        return
    if registry.get("version") != 1:
        raise RuntimeError("Unknown P1 registry; references left untouched")
    probe = registry.get("current")
    if probe is not None:
        probe.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P1] STOP_FAILED %s" % type(exc).__name__)
