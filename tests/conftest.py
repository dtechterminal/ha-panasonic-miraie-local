"""Load protocol/client modules without importing HA's integration initializer."""

from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
for name, path in [
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.ac_mitm", ROOT / "custom_components/ac_mitm"),
]:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
