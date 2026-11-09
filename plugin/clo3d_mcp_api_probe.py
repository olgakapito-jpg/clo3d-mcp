"""A0: bounded static metadata, not a native API test or an MCP tool.

Run explicitly in CLO Script Editor. Importing this file does not run a probe.
No native imports, object construction, API calls, callbacks, files or IPC.
Only exact stdlib structural accessors are used; user descriptors are not read.
See docs/CLO_API_PROBE_CHECK.md before running or sharing the output.
"""

import json
import math
import re
import sys
import types


# Edit only these three selections for one explicit Script Editor run.
SELECT_MODULE = "pattern_api"
SELECT_TYPE = None
SELECT_CURSOR = 0

ALLOWED_MODULES = (
    "pattern_api", "export_api", "fabric_api", "import_api", "utility_api",
    "rest_api", "gui_api", "ApiTypes",
)
PAGE_SIZE = 12
MAX_NAMESPACE_SCAN = 4096
MAX_DOC_CHARS = 512
MAX_NAME_CHARS = 128
MAX_SIGNATURE_PARAMETERS = 32
MAX_REPORT_BYTES = 24576

# These are the known CPython structural descriptors, not descriptors obtained
# from an inspected class/metaclass. type.__getattribute__(cls, '__dict__')
# would NOT be safe: a hostile metaclass may shadow that name with a property.
_CLASS_DICT = type.__dict__["__dict__"]
_CLASS_MRO = type.__dict__["__mro__"]
_MODULE_DICT = types.ModuleType.__dict__["__dict__"]
_BUILTIN_CALLABLE_TYPES = (
    types.BuiltinFunctionType, types.MethodDescriptorType,
    types.WrapperDescriptorType,
)
_SENSITIVE_WORDS = (
    "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION", "API_KEY",
    "APIKEY", "PRIVATE", "SESSION", "PATH", "DIRECTORY", "FILENAME",
)
_UNSAFE_TEXT = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\|(?:^|[\s\"'=(:])/(?:[^\s/]+/)|"
    r"https?://|token|secret|password|credential|authorization|api[_ -]?key|"
    r"(?:sk-|gh[pousr]_|github_pat_|xox[baprs]-)[a-z0-9_-]+|"
    r"eyJ[a-z0-9_-]{12,}\.)"
)


def _field(namespace, name):
    """Bounded raw items traversal: never key-lookup through hostile keys."""
    for index, (key, value) in enumerate(namespace.items()):
        if index >= MAX_NAMESPACE_SCAN:
            break
        if type(key) is str and key == name:
            return value
    return None


def _class_namespace(value):
    return _CLASS_DICT.__get__(value)


def _is_class(value):
    # isinstance(value, type) can consult value.__class__; avoid that hook.
    for index, base in enumerate(_CLASS_MRO.__get__(type(value))):
        if index >= 32:
            break
        if base is type:
            return True
    return False


def _public_name(value):
    return (
        type(value) is str and 0 < len(value) <= MAX_NAME_CHARS
        and not value.startswith("_") and value.isidentifier()
        and all(ord(char) < 128 for char in value)
        and not any(word in value.upper() for word in _SENSITIVE_WORDS)
    )


def _namespace_name(value):
    if type(value) is not str or len(value) > MAX_NAME_CHARS:
        return None
    return value if all(_public_name(part) for part in value.split(".")) else None


def _text(value):
    if type(value) is not str:
        return {"status": "missing_or_non_text"}
    # Truncate BEFORE scanning. Split only the bounded prefix, never the full doc.
    prefix = value[:MAX_DOC_CHARS]
    lines = ["[redacted]" if _UNSAFE_TEXT.search(line) else line
             for line in prefix.splitlines()]
    result = "\n".join(lines)[:MAX_DOC_CHARS]
    return {"status": "present", "text": result,
            "truncated": len(value) > MAX_DOC_CHARS,
            "redacted": any(line == "[redacted]" for line in lines)}


def _identity(value):
    namespace = _class_namespace(value)
    return {"name": _namespace_name(_field(namespace, "__qualname__")),
            "module": _namespace_name(_field(namespace, "__module__")),
            "source": "own_class_dictionary_only",
            "missing_or_unsafe_fields": "null_means_metadata_not_confirmed"}


def _constant(value, name):
    # Never serialize arbitrary strings, repr(), objects or container contents.
    # Only visibly constant public numeric names; no enum conversion/int(obj).
    if not name.isupper():
        return {"status": "value_withheld"}
    if value is None or type(value) is bool:
        return {"status": "numeric_or_null", "value": value}
    if type(value) is int and value.bit_length() <= 64:
        return {"status": "numeric_or_null", "value": value}
    if type(value) is float and math.isfinite(value):
        return {"status": "numeric_or_null", "value": value}
    return {"status": "value_withheld"}


def _python_signature(value):
    # Exact function type only: these are fixed CPython accessors, never
    # inspect.signature(), annotations, __signature__ or user-defined wrappers.
    code = object.__getattribute__(value, "__code__")
    count = code.co_argcount + code.co_kwonlyargcount
    if count > MAX_SIGNATURE_PARAMETERS:
        return {"status": "parameter_limit"}
    positional_only = getattr(code, "co_posonlyargcount", 0)
    names = code.co_varnames
    parameters = []
    defaults = object.__getattribute__(value, "__defaults__")
    default_start = code.co_argcount - (len(defaults) if defaults else 0)
    for index in range(count):
        name = names[index]
        if not _public_name(name):
            return {"status": "unsafe_or_ambiguous_parameter_name"}
        kind = ("positional_only" if index < positional_only else
                "positional_or_keyword" if index < code.co_argcount else
                "keyword_only")
        parameters.append({"name": name, "kind": kind,
                           "default": ("present_value_withheld"
                                       if default_start <= index < code.co_argcount
                                       else "not_inspected" if kind == "keyword_only"
                                       else "absent")})
    next_index = count
    for flag, kind in ((4, "var_positional"), (8, "var_keyword")):
        if code.co_flags & flag:
            name = names[next_index]
            if not _public_name(name):
                return {"status": "unsafe_or_ambiguous_parameter_name"}
            parameters.append({"name": name, "kind": kind})
            next_index += 1
    return {"status": "python_code_shape_only", "parameters": parameters,
            "annotations": "not_inspected", "default_values": "withheld"}


def _metadata(name, value):
    result = {"name": name}
    value_type = type(value)
    if _is_class(value):
        result.update(kind="class", identity=_identity(value),
                      doc=_text(_field(_class_namespace(value), "__doc__")),
                      signature={"status": "constructor_not_inspected"})
    elif value_type is types.FunctionType:
        result.update(kind="python_function", callable_present=True,
                      doc=_text(object.__getattribute__(value, "__doc__")),
                      signature=_python_signature(value))
    elif any(value_type is item for item in _BUILTIN_CALLABLE_TYPES):
        # Only exact known stdlib types: no arbitrary getattr/property execution.
        doc = object.__getattribute__(value, "__doc__")
        try:
            signature = object.__getattribute__(value, "__text_signature__")
        except AttributeError:
            signature = None
        result.update(kind="builtin_callable", callable_present=True,
                      doc=_text(doc), signature=_text(signature),
                      signature_source="builtin_text_signature_or_doc_only")
    elif value_type is staticmethod or value_type is classmethod:
        result.update(kind="descriptor", metadata="not_followed",
                      signature={"status": "descriptor_not_invoked"})
    elif value_type is property:
        result.update(kind="property", metadata="not_followed",
                      signature={"status": "descriptor_not_invoked"})
    else:
        result.update(kind="opaque_callable" if callable(value) else "opaque_or_constant",
                      metadata="not_followed", constant=_constant(value, name),
                      signature={"status": "unavailable_without_dynamic_access"})
    return result


def _encode(report):
    # ASCII escaping also makes lone surrogates safe on Script Editor stdout.
    return json.dumps(report, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, indent=2)


def collect_metadata(module_name=SELECT_MODULE, type_name=SELECT_TYPE,
                     cursor=SELECT_CURSOR):
    """Inspect one loaded allowlisted module or one own-class-member page.

    cursor is a raw dictionary position, NOT a public-name index. Continue only
    with next_cursor from the previous report in an unchanged runtime. No import
    option exists: missing bindings remain pending joint import review.
    """
    report = {"schema": "clo_api_static_probe_v1", "status": "invalid_selection",
              "evidence": "metadata_only_not_native_test", "entries": [],
              "limits": {"page_size": PAGE_SIZE, "namespace_scan": MAX_NAMESPACE_SCAN,
                         "doc_chars": MAX_DOC_CHARS, "report_bytes": MAX_REPORT_BYTES},
              "next_cursor": None}
    if (type(module_name) is not str or module_name not in ALLOWED_MODULES
            or type(cursor) is not int or not 0 <= cursor < MAX_NAMESPACE_SCAN
            or (type_name is not None and not _public_name(type_name))):
        return report
    report.update(module=module_name, selected_type=type_name, cursor=cursor)
    if type(sys.modules) is not dict:
        report["status"] = "unsupported_module_registry"
        return report
    # One exact allowlist key; no enumeration/disclosure of sys.modules.
    module = dict.get(sys.modules, module_name)
    if module is None:
        report.update(status="not_loaded", import_status="pending_joint_review_no_import")
        return report
    if type(module) is not types.ModuleType:
        report["status"] = "unsupported_module_type"
        return report
    namespace = _MODULE_DICT.__get__(module)
    declared_name = _field(namespace, "__name__")
    if type(declared_name) is not str or declared_name != module_name:
        report["status"] = "module_identity_ambiguous"
        return report
    report["identity"] = {"registry_name": module_name, "declared_name": module_name}
    if type_name is not None:
        value = _field(namespace, type_name)
        if not _is_class(value):
            report["status"] = "type_missing_or_ambiguous_within_scan_limit"
            return report
        report["type_identity"] = _identity(value)
        namespace = _class_namespace(value)
        report["scope"] = "own_members_only_no_inherited_or_instance_access"
    else:
        report["scope"] = "module_dictionary_only"
        report["doc"] = _text(_field(namespace, "__doc__"))
    report.update(status="metadata_only", scanned=0, truncated=False)
    for index, (name, value) in enumerate(namespace.items()):
        if index >= MAX_NAMESPACE_SCAN:
            report.update(truncated=True, stop_reason="namespace_scan_limit")
            break
        report["scanned"] = index + 1
        if index < cursor:
            continue
        if len(report["entries"]) >= PAGE_SIZE:
            report.update(next_cursor=index, truncated=True, stop_reason="page_limit")
            break
        if not _public_name(name):
            continue
        entry = _metadata(name, value)
        report["entries"].append(entry)
        if len(_encode(report).encode("ascii")) > MAX_REPORT_BYTES - 1024:
            report["entries"].pop()
            report.update(next_cursor=index, truncated=True, stop_reason="byte_limit")
            break
    return report


def render_metadata(module_name=SELECT_MODULE, type_name=SELECT_TYPE,
                    cursor=SELECT_CURSOR):
    """Return one bounded ASCII JSON document; errors contain no exception text."""
    try:
        report = collect_metadata(module_name, type_name, cursor)
        text = _encode(report)
        if len(text.encode("ascii")) <= MAX_REPORT_BYTES:
            return text
        return _encode({"schema": "clo_api_static_probe_v1", "status": "report_byte_limit"})
    except Exception:
        # Do not print repr(exception): it may expose paths or runtime secrets.
        return _encode({"schema": "clo_api_static_probe_v1", "status": "metadata_error",
                        "next_action": "stop_and_review_no_dynamic_fallback"})


if __name__ == "__main__":
    print(render_metadata())
