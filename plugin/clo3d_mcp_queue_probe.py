"""P2 read-only external FIFO diagnostic. See docs/P2_QUEUE_CHECK.md."""

ROOT = None  # Explicit project root only when CLO does not supply __file__.


def main():
    import importlib.util
    from pathlib import Path

    if ROOT:
        root = Path(ROOT).resolve()
    elif globals().get("__file__"):
        root = Path(__file__).resolve().parent.parent
    else:
        raise RuntimeError("CLO omitted __file__; set ROOT to the project directory")
    spec = importlib.util.spec_from_file_location("clo_p2_launcher", root / "plugin" / "clo3d_mcp_pipe_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(root)
    module.main(profile="p2")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P2] NOT_STARTED %s: %s" % (type(exc).__name__, exc))
