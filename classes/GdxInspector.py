from pathlib import Path
from typing import Union

import gams.transfer as gt
import gamspy_base

from classes.FileInspector import FileInspector

# Friendly section headers, keyed by the gams.transfer symbol class name
# (Container.data values are instances of these). Anything not in this map
# (e.g. a future gams.transfer symbol type) falls back to its raw class name
# as the section header, so a newer gamsapi version can't silently drop data.
_SECTION_TITLES = {
    "Set": "Sets",
    "Parameter": "Parameters",
    "Variable": "Variables",
    "Equation": "Equations",
    "Alias": "Aliases",
}

# Fixed display order for the sections above; anything else (fallback raw
# class names) is appended afterward, sorted alphabetically.
_SECTION_ORDER = ["Set", "Parameter", "Variable", "Equation", "Alias"]


class GdxInspector(FileInspector):
    """
    Describes the structure of a GAMS GDX file: its symbols (sets, parameters,
    variables, equations, aliases), each one's dimension count, domain/dimension
    names, and number of elements/records.

    Reads via gamsapi's "GAMS Transfer" API (gams.transfer.Container), pointed
    at gamspy_base's bundled system directory rather than a configured GAMS_exe
    -- this deliberately works with no GAMS installation present at all (only
    `pip install gamsapi[transfer] gamspy-base`), and avoids mixing GDX library
    versions between a possibly-different local GAMS install and the pinned
    gamsapi version.
    """

    extensions = (".gdx",)

    def inspect(self, file_path: Union[str, Path]) -> dict:
        """
        Describe a GDX file's symbol structure as JSON-serializable data.

        Parameters:
            file_path (str | Path): Path to the .gdx file to inspect.

        Returns:
            dict: {"format": "gdx-symbols", "file_name", "symbol_count",
            "sections": [{"title", "symbols": [{"name", "dimension",
            "elements", "domains", "description"}, ...]}, ...]}, symbols
            grouped by type and sorted by name within each section. A file
            that exists but isn't a valid/readable GDX file (verified
            empirically: gams.transfer.Container.read() fails silently on
            invalid input rather than raising, even for a truncated real GDX
            file) comes back as a 0-symbol/empty-sections result rather than
            an exception -- there's no reliable signal from the underlying
            library to distinguish that from a genuinely empty GDX.

        Raises:
            FileNotFoundError: If file_path does not exist.
            RuntimeError: If reading raises directly (kept as a defensive
                fallback matching this codebase's file-I/O idiom, even though
                the underlying library doesn't appear to hit it in practice).
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"GDX file not found: {file_path}")

        container = gt.Container(system_directory=gamspy_base.directory)
        try:
            container.read(str(file_path))
        except Exception as e:
            raise RuntimeError(f"Failed to read GDX file '{file_path}': {e}") from e

        return self._build_data(file_path, container)

    def _build_data(self, file_path: Path, container: "gt.Container") -> dict:
        """
        Build the result dict from an already-read Container.

        Parameters:
            file_path (Path): The inspected file's path (its name is included
                in the result).
            container (gt.Container): The Container the file was read into.

        Returns:
            dict: See inspect()'s docstring for the shape.
        """
        sections: dict = {}
        for name, symbol in container.data.items():
            type_name = type(symbol).__name__
            sections.setdefault(type_name, []).append(self._build_symbol(name, symbol))

        ordered_types = [t for t in _SECTION_ORDER if t in sections]
        ordered_types += sorted(t for t in sections if t not in _SECTION_ORDER)

        return {
            "format": "gdx-symbols",
            "file_name": file_path.name,
            "symbol_count": len(container.data),
            "sections": [
                {
                    "title": _SECTION_TITLES.get(type_name, type_name),
                    "symbols": sorted(sections[type_name], key=lambda s: s["name"]),
                }
                for type_name in ordered_types
            ],
        }

    def _build_symbol(self, name: str, symbol) -> dict:
        """
        Build one symbol's entry within its section.

        Parameters:
            name (str): The symbol's name.
            symbol: A gams.transfer Set/Parameter/Variable/Equation/Alias instance.

        Returns:
            dict: {"name", "dimension", "elements", "domains", "description"}.
            "domains" is [] for a 0-dim symbol (there's nothing to name);
            otherwise the symbol's domain names, which may include "*" for a
            dimension that isn't domain-checked against a real set.
        """
        return {
            "name": name,
            "dimension": symbol.dimension,
            "elements": symbol.number_records,
            "domains": list(symbol.domain_names) if symbol.dimension else [],
            "description": getattr(symbol, "description", "") or "",
        }
