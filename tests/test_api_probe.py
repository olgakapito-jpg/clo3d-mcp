"""Fake metadata only. Passing these tests is not evidence about real CLO."""

import ast
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


SPEC = importlib.util.spec_from_file_location(
    "a0_api_probe", Path(__file__).parents[1] / "diagnostics" / "clo3d_mcp_api_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.fixture
def module(monkeypatch):
    value = types.ModuleType("pattern_api", "Static API documentation")
    monkeypatch.setitem(sys.modules, "pattern_api", value)
    return value


def entries(report):
    return {item["name"]: item for item in report["entries"]}


def test_import_does_not_run_or_import_native(capsys):
    before = set(sys.modules)
    another = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(another)
    assert capsys.readouterr().out == ""
    assert set(sys.modules) == before


@pytest.mark.parametrize("name", probe.ALLOWED_MODULES)
def test_missing_is_not_loaded_not_absent(name, monkeypatch):
    monkeypatch.delitem(sys.modules, name, raising=False)
    result = probe.collect_metadata(name)
    assert result["status"] == "not_loaded"
    assert result["import_status"] == "pending_joint_review_no_import"


@pytest.mark.parametrize("args", [
    {"module_name": "os"}, {"module_name": "*"}, {"module_name": "pattern_api.Get"},
    {"module_name": 4}, {"cursor": True}, {"cursor": -1},
    {"cursor": probe.MAX_NAMESPACE_SCAN}, {"cursor": 1.0},
    {"type_name": "_private"}, {"type_name": "Thing.member"},
    {"type_name": "Thing()"}, {"type_name": "A" * 129},
])
def test_invalid_selections_do_nothing(args):
    assert probe.collect_metadata(**args)["status"] == "invalid_selection"


def test_static_function_shape_without_defaults_annotations_or_signature(module):
    calls = []

    class Poison:
        def __repr__(self):
            calls.append("repr")
            raise AssertionError

    def GetData(index, /, mode=Poison(), *args, flag=True, **kwargs):
        """GetData(index: int, mode: int) -> bool"""
        calls.append("native")

    GetData.__signature__ = Poison()
    GetData.__annotations__ = {"return": Poison()}
    module.GetData = GetData
    result = entries(probe.collect_metadata())["GetData"]
    assert result["kind"] == "python_function"
    signature = result["signature"]
    assert signature["status"] == "python_code_shape_only"
    assert [item["kind"] for item in signature["parameters"]] == [
        "positional_only", "positional_or_keyword", "keyword_only",
        "var_positional", "var_keyword"]
    assert signature["parameters"][1]["default"] == "present_value_withheld"
    assert not calls


def test_builtin_doc_and_signature_without_call(module):
    module.GetLength = len
    result = entries(probe.collect_metadata())["GetLength"]
    assert result["kind"] == "builtin_callable"
    assert "number of items" in result["doc"]["text"]
    assert result["signature"]["status"] == "present"
    assert result["callable_present"] is True


def test_evil_module_getattr_and_dir_are_not_called(module):
    def fail(*args):
        raise AssertionError("dynamic module access")

    module.__getattr__ = fail
    module.__dir__ = fail
    module.GetName = lambda: None
    assert "GetName" in entries(probe.collect_metadata())


def test_hostile_metaclass_and_all_descriptors_never_execute(module):
    calls = []

    class EvilMeta(type):
        def __getattribute__(self, name):
            calls.append("getattribute")
            raise AssertionError

        @property
        def __dict__(self):
            calls.append("meta_dict_descriptor")
            raise AssertionError

        @property
        def __mro__(self):
            calls.append("meta_mro_descriptor")
            raise AssertionError

        def __call__(self, *args, **kwargs):
            calls.append("constructor")
            raise AssertionError

    class EvilDescriptor:
        def __get__(self, *args):
            calls.append("descriptor")
            raise AssertionError

        def __getattribute__(self, name):
            calls.append("object_getattribute")
            raise AssertionError

    class Options(metaclass=EvilMeta):
        """Options metadata only."""
        Mode = EvilDescriptor()

        @property
        def Width(self):
            calls.append("property")
            raise AssertionError

        @staticmethod
        def Factory():
            calls.append("staticmethod")
            raise AssertionError

        @classmethod
        def Create(cls):
            calls.append("classmethod")
            raise AssertionError

    module.Options = Options
    module.Opaque = EvilDescriptor()
    top = entries(probe.collect_metadata())
    assert top["Options"]["kind"] == "class"
    members = entries(probe.collect_metadata(type_name="Options"))
    assert members["Width"]["kind"] == "property"
    assert members["Mode"]["metadata"] == "not_followed"
    assert members["Factory"]["kind"] == "descriptor"
    assert members["Create"]["kind"] == "descriptor"
    assert calls == []


def test_callable_object_is_presence_only(module):
    class NativeLike:
        def __call__(self):
            raise AssertionError("native invocation")

        def __getattribute__(self, name):
            raise AssertionError("dynamic attribute")

        def __repr__(self):
            raise AssertionError("repr")

    module.GetThing = NativeLike()
    result = entries(probe.collect_metadata())["GetThing"]
    assert result["kind"] == "opaque_callable"
    assert result["signature"]["status"] == "unavailable_without_dynamic_access"


def test_own_members_only_no_inheritance_or_instance_construction(module):
    class Base:
        Inherited = 1

    class Options(Base):
        OWN = 2

        def __new__(cls):
            raise AssertionError("construction")

    module.Options = Options
    result = probe.collect_metadata(type_name="Options")
    assert "Inherited" not in entries(result)
    assert entries(result)["OWN"]["constant"]["value"] == 2
    assert result["type_identity"]["source"] == "own_class_dictionary_only"


def test_constants_only_exact_small_numeric_nonsecret_names(module):
    module.COUNT = 3
    module.ENABLED = True
    module.NONE = None
    module.RATIO = 0.5
    module.HUGE = 1 << 10000
    module.NAN = float("nan")
    module.LABEL = "private freeform value"
    module.API_TOKEN = "do not output"
    module.FILE_PATH = "C:/do/not/output"
    module._private = "do not output"
    result = entries(probe.collect_metadata())
    assert result["COUNT"]["constant"]["value"] == 3
    assert result["ENABLED"]["constant"]["value"] is True
    assert result["NONE"]["constant"]["value"] is None
    assert result["RATIO"]["constant"]["value"] == 0.5
    for name in ("HUGE", "NAN", "LABEL"):
        assert result[name]["constant"]["status"] == "value_withheld"
    assert "API_TOKEN" not in result and "FILE_PATH" not in result
    assert "_private" not in result
    assert "private freeform" not in probe.render_metadata()


def test_docs_redact_paths_credentials_and_bound_surrogates(module):
    module.__doc__ = ("Safe documentation\nC:\\Users\\" + "private\\x\n"
                      "token=hidden-value\n/home/private/name\n"
                      "https://private.example\n" + "\ud800" * 100000)
    text = probe.render_metadata()
    result = json.loads(text)
    assert result["doc"]["truncated"] is True
    assert result["doc"]["redacted"] is True
    assert len(result["doc"]["text"]) <= probe.MAX_DOC_CHARS
    assert "hidden-value" not in text
    assert "Users" not in text and "private.example" not in text
    assert len(text.encode("ascii")) <= probe.MAX_REPORT_BYTES


def test_oversize_name_and_doc_do_not_break_page(module):
    module.__dict__["X" * 100000] = "hidden"
    module.__dict__["Bad\ud800Name"] = "hidden"
    module.GetData = lambda: None
    module.GetData.__doc__ = "\udfff" * 1000000
    result = json.loads(probe.render_metadata())
    assert len(result["entries"]) == 1
    assert entries(result)["GetData"]["doc"]["truncated"]


def test_pages_are_bounded_and_can_be_continued(module):
    for index in range(40):
        setattr(module, "GetItem" + str(index), len)
    seen = []
    cursor = 0
    for _ in range(5):
        result = probe.collect_metadata(cursor=cursor)
        assert len(result["entries"]) <= probe.PAGE_SIZE
        seen.extend(item["name"] for item in result["entries"])
        if result["next_cursor"] is None:
            break
        assert result["next_cursor"] > cursor
        cursor = result["next_cursor"]
    assert seen == ["GetItem" + str(index) for index in range(40)]


def test_byte_limit_is_enforced_and_continuation_retained(module, monkeypatch):
    # Artificially lower cap to exercise the same accounting branch.
    monkeypatch.setattr(probe, "MAX_REPORT_BYTES", 8000)
    for index in range(12):
        value = lambda: None
        value.__doc__ = "\ud800" * probe.MAX_DOC_CHARS
        setattr(module, "Function" + str(index), value)
    text = probe.render_metadata()
    result = json.loads(text)
    assert len(text.encode("ascii")) <= 8000
    assert result["stop_reason"] == "byte_limit"
    assert result["next_cursor"] is not None
    assert len(result["entries"]) < probe.PAGE_SIZE


def test_scan_limit_not_full_inventory(module):
    for index in range(probe.MAX_NAMESPACE_SCAN + 50):
        module.__dict__["_hidden" + str(index)] = None
    module.LateName = 3
    result = probe.collect_metadata()
    assert result["stop_reason"] == "namespace_scan_limit"
    assert result["truncated"] is True
    assert result["next_cursor"] is None
    assert result["scanned"] == probe.MAX_NAMESPACE_SCAN
    assert "LateName" not in entries(result)


def test_nonstring_hostile_namespace_keys_do_not_execute(module):
    class Key:
        def __hash__(self):
            return 7

        def __eq__(self, other):
            raise AssertionError("key equality")

        def __repr__(self):
            raise AssertionError("key repr")

    module.__dict__[Key()] = object()
    module.GetData = len
    assert probe.collect_metadata()["status"] == "metadata_only"


def test_unsafe_class_metadata_is_explicitly_unconfirmed(module):
    class Options:
        pass

    Options.__module__ = "C:/private/token=secret"
    module.Options = Options
    identity = entries(probe.collect_metadata())["Options"]["identity"]
    assert identity["module"] is None
    assert identity["missing_or_unsafe_fields"] == "null_means_metadata_not_confirmed"
    assert "C:/private" not in probe.render_metadata()


def test_custom_constant_subclasses_are_not_coerced(module):
    class EvilInt(int):
        def __int__(self):
            raise AssertionError("int coercion")

        def __repr__(self):
            raise AssertionError("repr coercion")

        def bit_length(self):
            raise AssertionError("method invocation")

    module.NUMBER = EvilInt(1)
    result = entries(probe.collect_metadata())["NUMBER"]
    assert result["constant"]["status"] == "value_withheld"


def test_oversize_python_signature_is_marked_not_traversed(module):
    # Code objects can be built in tests without executing a native callable.
    def Function():
        raise AssertionError("must not run")

    Function.__code__ = Function.__code__.replace(
        co_argcount=33, co_nlocals=33,
        co_varnames=tuple("arg" + str(index) for index in range(33)))
    module.Function = Function
    assert entries(probe.collect_metadata())["Function"]["signature"] == {
        "status": "parameter_limit"}


def test_module_subclass_is_not_traversed(monkeypatch):
    class EvilModule(types.ModuleType):
        def __getattribute__(self, name):
            raise AssertionError("module subclass")

    monkeypatch.setitem(sys.modules, "pattern_api", EvilModule("pattern_api"))
    assert probe.collect_metadata()["status"] == "unsupported_module_type"


def test_identity_mismatch_and_missing_type_are_ambiguous(module):
    assert probe.collect_metadata(type_name="Options")["status"] == (
        "type_missing_or_ambiguous_within_scan_limit")
    module.__name__ = "unrelated_module"
    assert probe.collect_metadata()["status"] == "module_identity_ambiguous"


def test_errors_do_not_reveal_exception_text(monkeypatch):
    def broken(*args):
        raise RuntimeError("C:/private token=secret")

    monkeypatch.setattr(probe, "collect_metadata", broken)
    text = probe.render_metadata()
    assert json.loads(text)["status"] == "metadata_error"
    assert "private" not in text and "secret" not in text


def test_only_explicit_apitypes_entrypoint_import_no_dynamic_import_or_disclosure():
    source = Path(SPEC.origin).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    forbidden_calls = {"eval", "exec", "open", "__import__", "dir", "getattr_static"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
    assert set(imports) == {"json", "math", "re", "sys", "time", "types", "ApiTypes"}
    native_imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import)
                      and any(alias.name == "ApiTypes" for alias in node.names)]
    entrypoint = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "run_selected_probe")
    assert len(native_imports) == 1 and native_imports[0] in list(ast.walk(entrypoint))
    assert "sys.modules.items(" not in source
    assert "sys.modules.keys(" not in source


def test_selected_apitypes_import_and_probe_share_run(monkeypatch):
    import builtins

    original_import = builtins.__import__
    calls = []
    value = types.ModuleType("ApiTypes")
    value.EXAMPLE = 1
    monkeypatch.delitem(sys.modules, "ApiTypes", raising=False)
    monkeypatch.setattr(probe, "SELECT_MODULE", "ApiTypes")
    monkeypatch.setattr(probe, "SELECT_TYPE", None)
    monkeypatch.setattr(probe, "SELECT_CURSOR", 0)

    def import_once(name, *args, **kwargs):
        if name == "ApiTypes":
            calls.append(name)
            monkeypatch.setitem(sys.modules, name, value)
            return value
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_once)
    report = json.loads(probe.run_selected_probe())
    assert calls == ["ApiTypes"]
    assert report["status"] == "metadata_only" and report["module"] == "ApiTypes"
    assert "EXAMPLE" in entries(report)


def test_selected_import_failure_stops_without_probe_or_secret(monkeypatch):
    import builtins

    original_import = builtins.__import__
    calls = []
    monkeypatch.setattr(probe, "SELECT_MODULE", "ApiTypes")

    def broken(name, *args, **kwargs):
        if name == "ApiTypes":
            calls.append(name)
            raise ImportError("C:/private token=secret")
        return original_import(name, *args, **kwargs)

    def no_probe(*args):
        pytest.fail("probe must not follow import failure")

    monkeypatch.setattr(builtins, "__import__", broken)
    monkeypatch.setattr(probe, "render_metadata", no_probe)
    text = probe.run_selected_probe()
    assert calls == ["ApiTypes"]
    assert json.loads(text)["status"] == "import_failed"
    assert "private" not in text and "secret" not in text


def test_other_selection_does_not_import_apitypes(module, monkeypatch):
    monkeypatch.delitem(sys.modules, "ApiTypes", raising=False)
    monkeypatch.setattr(probe, "SELECT_MODULE", "pattern_api")
    monkeypatch.setattr(probe, "SELECT_TYPE", None)
    monkeypatch.setattr(probe, "SELECT_CURSOR", 0)
    assert json.loads(probe.run_selected_probe())["status"] == "metadata_only"
    assert "ApiTypes" not in sys.modules


@pytest.fixture
def batch_module(monkeypatch):
    value = types.ModuleType("ApiTypes")
    monkeypatch.setitem(sys.modules, "ApiTypes", value)
    return value


def test_batch_traverses_module_and_class_pages_without_constructing(batch_module):
    class Options:
        def __new__(cls):
            raise AssertionError("constructor")

        @property
        def Property(self):
            raise AssertionError("descriptor")

    for index in range(30):
        setattr(Options, "Field" + str(index), property(lambda self: 1 / 0))
        setattr(batch_module, "CONSTANT" + str(index), index)
    batch_module.Options = Options
    report = json.loads(probe.render_batch_metadata())
    assert report["complete"] and report["stop_reason"] == "completed"
    assert report["classes_discovered"] == ["Options"]
    assert report["classes_completed"] == 1
    pages = report["pages"]
    assert len([p for p in pages if p["selected_type"] is None]) == 3
    class_pages = [p for p in pages if p["selected_type"] == "Options"]
    assert len(class_pages) == 3
    members = {e["name"]: e for p in class_pages for e in p["entries"]}
    assert members["Property"]["metadata"] == "not_followed"
    assert "__new__" not in members
    assert report["entries_collected"] == sum(len(p["entries"]) for p in pages)


@pytest.mark.parametrize("limit,reason", [
    ("BATCH_MAX_PAGES", "page_limit"), ("BATCH_MAX_TYPES", "type_limit"),
    ("BATCH_MAX_ENTRIES", "entry_limit"),
])
def test_batch_limits_explicit_partial(batch_module, monkeypatch, limit, reason):
    batch_module.Options = type("Options", (), {})
    monkeypatch.setattr(probe, limit, 0)
    report = json.loads(probe.render_batch_metadata())
    assert not report["complete"] and report["status"] == "partial"
    assert report["stop_reason"] == reason


def test_batch_byte_bound_and_cooperative_time_bound(batch_module, monkeypatch):
    batch_module.ONE = 1
    monkeypatch.setattr(probe, "BATCH_MAX_BYTES", 33000)
    for index in range(30):
        function = lambda: None
        function.__doc__ = "description " * 100
        setattr(batch_module, "Function" + str(index), function)
    text = probe.render_batch_metadata()
    report = json.loads(text)
    assert len(text.encode("ascii")) <= 33000
    assert report["stop_reason"] == "byte_limit" and not report["complete"]
    ticks = iter([0.0, 6.0])
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(ticks))
    report = json.loads(probe.render_batch_metadata())
    assert report["stop_reason"] == "time_limit" and not report["pages"]


@pytest.mark.parametrize("fault", ["namespace", "exception", "cursor", "scan"])
def test_batch_stops_at_first_fault_no_next_page(batch_module, monkeypatch, fault):
    batch_module.ONE = 1
    original = probe.collect_metadata
    calls = []

    def altered(*args):
        calls.append(args)
        page = original(*args)
        if fault == "namespace":
            batch_module.TWO = 2
        elif fault == "exception":
            raise RuntimeError("C:/private token=secret")
        elif fault == "cursor":
            page["next_cursor"] = 0
        else:
            page.update(truncated=True, next_cursor=None, stop_reason="namespace_scan_limit")
        return page

    monkeypatch.setattr(probe, "collect_metadata", altered)
    text = probe.render_batch_metadata()
    report = json.loads(text)
    assert len(calls) == 1 and not report["complete"]
    assert report["stop_reason"] == {"namespace": "namespace_changed",
                                     "exception": "metadata_error",
                                     "cursor": "invalid_continuation",
                                     "scan": "namespace_scan_limit"}[fault]
    assert "private" not in text and "secret" not in text


def test_batch_missing_module_no_import_or_fallback(monkeypatch):
    monkeypatch.delitem(sys.modules, "ApiTypes", raising=False)
    report = json.loads(probe.render_batch_metadata())
    assert not report["complete"]
    assert report["stop_reason"] == "not_loaded_or_unsupported_module"


def test_batch_entrypoint_import_once_then_traversal(monkeypatch, batch_module):
    import builtins

    original_import = builtins.__import__
    calls = []

    def observed(name, *args, **kwargs):
        if name == "ApiTypes":
            calls.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", observed)
    report = json.loads(probe.run_selected_probe(batch=True))
    assert calls == ["ApiTypes"]
    assert report["schema"] == "clo_api_static_batch_v1" and report["complete"]
