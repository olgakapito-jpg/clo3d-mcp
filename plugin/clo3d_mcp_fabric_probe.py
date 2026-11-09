"""Retired colorway diagnostic; not needed for current Object Browser scope.

Separate diagnostic, never an overload fallback for get_fabric_list. No names,
scene changes, threads, callbacks, files, IPC or retries. See inventory runbook.
Importing this source file does not import CLO or run the diagnostic.
"""

import json


def collect_counts(fabric, export):
    report = {"schema": "clo_fabric_count_probe_v1", "status": "partial",
              "observations": [], "evidence": "native_counts_only_not_list_acceptance"}
    try:
        before = export.GetCurrentColorwayIndex()
        if type(before) is not int or not 0 <= before <= 255:
            report.update(status="invalid_native_result", stop_reason="colorway")
            return report
        report["colorway_index"] = before
        # Explicit comparison, not retry after failure; first error stops all.
        for label, args in (("default", ()), ("bool_current", (True,)),
                            ("bool_all", (False,)), ("int_all", (-2,)),
                            ("int_current", (-1,)), ("int_selected", (before,))):
            value = fabric.GetFabricCount(*args)
            if type(value) is not int or not 0 <= value <= 4096:
                report.update(status="invalid_native_result", stop_reason=label)
                return report
            report["observations"].append({"selection": label, "count": value})
        after = export.GetCurrentColorwayIndex()
        if type(after) is not int or after != before:
            report.update(status="inventory_changed", stop_reason="colorway_changed")
            return report
        report.update(status="completed", stop_reason="completed")
    except Exception:
        report.update(status="command_error", stop_reason="stop_no_retry")
    return report


def run_probe():
    try:
        import fabric_api
        import export_api
    except Exception:
        return {"schema": "clo_fabric_count_probe_v1", "status": "import_failed",
                "stop_reason": "stop_no_retry"}
    return collect_counts(fabric_api, export_api)


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
