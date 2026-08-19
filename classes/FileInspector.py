import importlib
from pathlib import Path
from typing import Optional, Type, Union

from classes.Config import Config


class FileInspector:
    """
    Base class for inspecting a data file's *structure* (not its full content)
    and describing it as a human-readable string, so a GUI can show "what's
    inside this file" without needing its own per-filetype rendering logic.

    Subclasses declare which file extensions they handle via the class-level
    `extensions` tuple and implement `inspect()`. Dispatch to the right
    subclass for a given file happens through `FileInspector.get_inspector`/
    `FileInspector.inspect_path`, keyed by extension.

    Adding a new file type: write a new subclass in its own classes/*.py file
    (mirroring this repo's one-class-per-file convention), then add one entry
    to `_INSPECTOR_MODULES` below.
    """

    extensions: tuple = ()

    def __init__(self, config: Config):
        """
        Initialize the inspector.

        Parameters:
            config (Config): Config instance. Not every inspector subclass
                needs values out of it, but every subclass accepts it for a
                consistent constructor signature across the registry.
        """
        self.config = config

    def inspect(self, file_path: Union[str, Path]) -> str:
        """
        Describe the structure of the given file as a human-readable string.

        Parameters:
            file_path (str | Path): Path to the file to inspect.

        Returns:
            str: A human-readable description of the file's structure.
        """
        raise NotImplementedError

    @classmethod
    def get_inspector(cls, file_path: Union[str, Path], config: Config) -> Optional["FileInspector"]:
        """
        Look up and instantiate the inspector registered for file_path's extension.

        Parameters:
            file_path (str | Path): Path to the file to inspect.
            config (Config): Config instance passed through to the inspector.

        Returns:
            FileInspector: An instantiated inspector, or None if no inspector
            is registered for this file's extension.
        """
        inspector_cls = _resolve(Path(file_path).suffix.lower())
        return inspector_cls(config) if inspector_cls else None

    @classmethod
    def inspect_path(cls, file_path: Union[str, Path], config: Config) -> str:
        """
        Convenience entry point: describe file_path's structure as a string,
        or return a friendly explanation if no inspector supports its type.

        Parameters:
            file_path (str | Path): Path to the file to inspect.
            config (Config): Config instance passed through to the inspector.

        Returns:
            str: The inspection result, or a "not supported yet" message for
            an unregistered file extension. Real inspection failures (e.g. a
            corrupt file) are raised, not swallowed into a string.
        """
        inspector = cls.get_inspector(file_path, config)
        if inspector is None:
            extension = Path(file_path).suffix or "(no extension)"
            return f"No inspector available for '{extension}' files yet."
        return inspector.inspect(file_path)


# Extension -> (module path, class name), resolved lazily (only imported the
# first time that extension is actually requested) rather than at module load
# time -- this file is each concrete inspector's base class, so eagerly
# importing them here would create an import cycle. It also means an inspector
# module's own dependencies (e.g. GdxInspector's gamsapi/gamspy_base) only
# load when that file type is actually inspected.
#
# Adding a new file type: write classes/XyzInspector.py (subclassing
# FileInspector, setting `extensions`), then add one entry here.
_INSPECTOR_MODULES = {
    ".gdx": ("classes.GdxInspector", "GdxInspector"),
}

_resolved_cache: dict = {}


def _resolve(extension: str) -> Optional[Type[FileInspector]]:
    if extension in _resolved_cache:
        return _resolved_cache[extension]
    target = _INSPECTOR_MODULES.get(extension)
    if target is None:
        return None
    module_name, class_name = target
    inspector_cls = getattr(importlib.import_module(module_name), class_name)
    _resolved_cache[extension] = inspector_cls
    return inspector_cls
