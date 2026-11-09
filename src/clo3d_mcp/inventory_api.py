"""Read-only CLO inventories, invoked only by the verified UI executor.

No native imports, overload fallback, coercion, construction or retry. Repeated
reads are a bounded consistency check, not an atomic scene snapshot.
"""

from clo3d_mcp.pattern_contract import (
    CommandError, MAX_AVATARS, MAX_FABRICS,
    inventory_name, validate_params, validate_result,
)


class InventoryAPI:
    def __init__(self, modules):
        self.modules = dict(modules)

    def _require(self, module, names):
        value = self.modules.get(module)
        if any(not callable(getattr(value, name, None)) for name in names):
            raise CommandError("api_unavailable")
        return value

    @staticmethod
    def _count(value, maximum):
        if type(value) is not int or value < 0:
            raise CommandError("invalid_native_result")
        if value > maximum:
            raise CommandError("inventory_limit")
        return value

    @staticmethod
    def _name(value):
        if not inventory_name(value):
            raise CommandError("invalid_native_result")
        return value

    def _fabrics(self):
        # Object Browser namespace. The documented keyword selects the bool
        # overload explicitly; False disables filtering to the current colorway.
        # No default/integer/count fallback and no colorway API dependency.
        fabric_api = self._require("fabric_api", ("GetFabricCount", "GetFabricName"))
        count = self._count(fabric_api.GetFabricCount(_bCurrentColorway=False), MAX_FABRICS)
        names = [self._name(fabric_api.GetFabricName(i)) for i in range(count)]
        if self._count(fabric_api.GetFabricCount(_bCurrentColorway=False), MAX_FABRICS) != count:
            raise CommandError("inventory_changed")
        for i, expected in enumerate(names):
            if self._name(fabric_api.GetFabricName(i)) != expected:
                raise CommandError("inventory_changed")
        if self._count(fabric_api.GetFabricCount(_bCurrentColorway=False), MAX_FABRICS) != count:
            raise CommandError("inventory_changed")
        return {"fabric_count": count,
                "fabrics": [{"index": i, "name": name} for i, name in enumerate(names)]}

    def _avatars(self):
        export_api = self._require("export_api", ("GetAvatarCount", "GetAvatarNameList"))
        count = self._count(export_api.GetAvatarCount(), MAX_AVATARS)
        names = export_api.GetAvatarNameList()
        if (type(names) is not list or len(names) != count
                or any(not inventory_name(name) for name in names)):
            raise CommandError("invalid_native_result")
        names = list(names)
        if self._count(export_api.GetAvatarCount(), MAX_AVATARS) != count:
            raise CommandError("inventory_changed")
        observed = export_api.GetAvatarNameList()
        if (type(observed) is not list or len(observed) > MAX_AVATARS
                or any(not inventory_name(name) for name in observed)):
            raise CommandError("invalid_native_result")
        if observed != names:
            raise CommandError("inventory_changed")
        if self._count(export_api.GetAvatarCount(), MAX_AVATARS) != count:
            raise CommandError("inventory_changed")
        return {"avatar_count": count,
                "avatars": [{"index": i, "name": name} for i, name in enumerate(names)]}

    def __call__(self, command, params):
        validate_params(command, params)
        if command not in ("get_fabric_list", "get_avatars"):
            raise CommandError("invalid_parameters")
        try:
            result = self._fabrics() if command == "get_fabric_list" else self._avatars()
        except CommandError:
            raise
        except Exception:
            raise CommandError("command_error") from None
        validate_result(command, result)
        return result
