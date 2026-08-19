from pathlib import Path
from typing import Union

from classes.FileInspector import FileInspector

# Cap on how many immediate children are listed -- an output folder can hold
# thousands of per-region/per-run files, and there's no need to materialize
# (or ship to the browser) all of them just to answer "did this run produce
# what I expect".
_MAX_ITEMS = 500


class FolderInspector(FileInspector):
    """
    Describes the structure of a directory used as a task's input/output: its
    immediate children (files and subfolders), each file's size and
    extension, and file counts grouped by extension.

    Deliberately not a recursive tree -- folder inputs/outputs in this
    codebase are typically flat batches of files (e.g. one file per region),
    and a flat listing is enough to answer "did this run produce what I
    expect", matching GdxInspector/RdsInspector's own "structure, not full
    content" scope. `total_size_bytes` therefore only sums immediate child
    files, not anything inside a subdirectory.
    """

    def inspect(self, file_path: Union[str, Path]) -> dict:
        """
        Describe a folder's immediate contents as JSON-serializable data.

        Parameters:
            file_path (str | Path): Path to the directory to inspect.

        Returns:
            dict: {"format": "folder-listing", "folder_name", "item_count",
            "file_count", "dir_count", "total_size_bytes",
            "extension_counts": {ext: count, ...}, "truncated", "items":
            [{"name", "type": "file"|"dir", "extension"?, "size_bytes"?}, ...]}.
            "items" is sorted directories-first, then alphabetically
            case-insensitive within each group, and capped at
            `_MAX_ITEMS` entries ("truncated" is True if it was cut off) --
            "item_count"/"file_count"/"dir_count"/"total_size_bytes"/
            "extension_counts" always reflect the *full* directory, not just
            the capped list. An entry that can't be stat'd (e.g. a
            permission-denied entry on a network drive) is still listed, just
            with "size_bytes": None, rather than aborting the whole
            inspection.

        Raises:
            NotADirectoryError: If file_path does not exist or isn't a directory.
        """
        path = Path(file_path)
        if not path.is_dir():
            raise NotADirectoryError(f"Folder not found: {path}")

        dirs = []
        files = []
        for entry in path.iterdir():
            if entry.is_dir():
                dirs.append(entry)
            else:
                files.append(entry)
        dirs.sort(key=lambda p: p.name.lower())
        files.sort(key=lambda p: p.name.lower())

        file_count = len(files)
        dir_count = len(dirs)
        total_size_bytes = 0
        extension_counts: dict = {}
        items = [{"name": entry.name, "type": "dir"} for entry in dirs]

        for entry in files:
            extension = entry.suffix.lower() or "(none)"
            extension_counts[extension] = extension_counts.get(extension, 0) + 1
            try:
                size_bytes = entry.stat().st_size
            except OSError:
                size_bytes = None
            else:
                total_size_bytes += size_bytes
            items.append({
                "name": entry.name,
                "type": "file",
                "extension": extension,
                "size_bytes": size_bytes,
            })

        truncated = len(items) > _MAX_ITEMS

        return {
            "format": "folder-listing",
            "folder_name": path.name,
            "item_count": file_count + dir_count,
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size_bytes": total_size_bytes,
            "extension_counts": extension_counts,
            "truncated": truncated,
            "items": items[:_MAX_ITEMS],
        }
