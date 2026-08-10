"""Détecte les noms globaux référencés mais jamais importés dans les modules d'interface.

Ce test existe parce que `frontend/pages/weak_points.py` a utilisé `ui` et `local_store`
pendant des semaines sans les importer : la fonction « Créer une lacune » levait un
NameError au premier clic, depuis la palette comme depuis le bouton de /lacunes, et aucun
test ne s'en apercevait — les tests existants importaient le module sans jamais exécuter
la fonction.

Une simple vérification d'import ne suffit donc pas. On inspecte le bytecode pour lister
les globaux que chaque fonction cherchera à résoudre à l'exécution, y compris dans ses
fonctions imbriquées, et on vérifie qu'ils existent dans l'espace de noms où la fonction
les cherchera réellement — c'est-à-dire `func.__globals__`, pas le module qui l'expose.
"""

from __future__ import annotations

import builtins
import dis
import importlib
import types
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).parents[1] / "frontend"

# Un import différé dans le corps d'une fonction n'est pas visible au niveau module :
# on le retrouve en collectant aussi les noms liés localement.
_BIND_OPS = {"STORE_FAST", "STORE_NAME", "STORE_GLOBAL", "STORE_DEREF"}


def _walk_codes(code: types.CodeType):
    """Parcourt un objet code et tous ceux qu'il contient (fonctions imbriquées, lambdas)."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _walk_codes(const)


def _functions(module: types.ModuleType):
    """Fonctions définies dans ce module, y compris les méthodes de ses classes.

    On filtre sur `__globals__` et non sur `__module__` : `functools.wraps` recopie
    `__module__` depuis la fonction décorée, si bien qu'un `@contextmanager` ferait
    passer du code de la bibliothèque standard pour du code local.
    """
    seen: set[int] = set()
    namespaces = [vars(module)]
    namespaces += [vars(value) for value in vars(module).values() if isinstance(value, type)]
    for namespace in namespaces:
        for value in list(namespace.values()):
            func = getattr(value, "__func__", value)
            code = getattr(func, "__code__", None)
            if code is None or id(code) in seen:
                continue
            if getattr(func, "__globals__", None) is not vars(module):
                continue
            seen.add(id(code))
            yield func


def _unresolved_globals(module: types.ModuleType) -> set[str]:
    """Noms globaux qu'une fonction du module cherchera sans les trouver."""
    missing: set[str] = set()
    for func in _functions(module):
        for sub in _walk_codes(func.__code__):
            instructions = list(dis.get_instructions(sub))
            bound_locally = {
                instruction.argval
                for instruction in instructions
                if instruction.opname in _BIND_OPS
            }
            for instruction in instructions:
                if instruction.opname != "LOAD_GLOBAL":
                    continue
                name = instruction.argval
                if name in bound_locally or hasattr(builtins, name):
                    continue
                if name not in vars(module):
                    missing.add(name)
    return missing


def _frontend_modules() -> list[str]:
    names = []
    for path in sorted(_FRONTEND.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = path.relative_to(_FRONTEND.parent).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            names.append(".".join(parts))
    return sorted(set(names))


@pytest.mark.parametrize("module_name", _frontend_modules())
def test_frontend_module_has_no_unresolved_global(module_name: str) -> None:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - dépend de l'environnement local
        pytest.skip(f"module non importable dans cet environnement : {exc}")

    missing = _unresolved_globals(module)

    assert not missing, (
        f"{module_name} référence des noms jamais importés : {sorted(missing)}. "
        "Ils lèveront NameError à l'exécution de la fonction concernée."
    )
