"""Stop/report this session's P2 only, without importing transport or legacy."""


def main():
    import builtins

    registry = getattr(builtins, "_clo3d_mcp_p2", None)
    if registry is None:
        print("[CLO P2] No diagnostic in this interpreter")
        return
    if registry.get("version") != 1:
        raise RuntimeError("Unknown P2 registry; references left untouched")
    probe = registry.get("current")
    if probe is not None:
        probe.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P2] STOP_FAILED %s" % type(exc).__name__)
