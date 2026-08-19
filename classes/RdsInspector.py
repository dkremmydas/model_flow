import json
import subprocess
from pathlib import Path
from typing import Union

from classes.FileInspector import FileInspector


class RdsInspector(FileInspector):
    """
    Describes the structure of an R .rds file (a single serialized R object):
    its class chain, and for data.frame/data.table (including tibbles and sf,
    which are also data.frames) row/column detail, for matrix/array its
    dimensions and element type, and for a plain list its length/names/each
    element's class one level deep. Any other class still reports its class
    chain, just with no further structural detail.

    Reads by shelling out to Rscript (classes/inspect_rds.R does the actual
    introspection via R's own class()/readRDS(), the same way
    ExecutionEngine.py already shells out to Rscript_exe for R tasks) rather
    than a third-party RDS-parsing library -- unlike GDX, Rscript_exe is
    already a mandatory config value for every Model Flow project, so there's
    no "avoid an extra dependency" win available, and R inspecting its own
    deserialized object is correct by construction for any object class,
    where a reimplemented parser would carry residual edge-case risk.
    """

    extensions = (".rds",)

    _SCRIPT_PATH = Path(__file__).parent / "inspect_rds.R"

    def inspect(self, file_path: Union[str, Path]) -> dict:
        """
        Describe an RDS file's top-level object as JSON-serializable data.

        Parameters:
            file_path (str | Path): Path to the .rds file to inspect.

        Returns:
            dict: {"format": "rds-object", "classes": [...], "primary_class":
            str, "detail": {...} | None}. See inspect_rds.R for the possible
            "detail" shapes ("data_frame", "matrix", "list", or absent).

        Raises:
            FileNotFoundError: If file_path does not exist.
            ValueError: If 'Rscript_exe' is not set in the configuration.
            RuntimeError: If Rscript exits non-zero, or its output can't be
                parsed as JSON (e.g. jsonlite missing on the R side -- the
                script's own stop() message ends up in stderr either way).
        """
        file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"RDS file not found: {file_path}")

        rscript_exe = self.config.get("Rscript_exe")
        if not rscript_exe:
            raise ValueError("'Rscript_exe' is not set in the configuration file.")

        try:
            result = subprocess.run(
                [str(rscript_exe), str(self._SCRIPT_PATH), str(file_path)],
                capture_output=True, text=True,
            )
        except OSError as e:
            raise RuntimeError(f"Failed to launch Rscript ('{rscript_exe}'): {e}") from e

        if result.returncode != 0:
            raise RuntimeError(f"Failed to inspect RDS file '{file_path}': {result.stderr.strip()}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Unexpected output inspecting RDS file '{file_path}': {result.stdout!r}"
            ) from e

        return {
            "format": "rds-object",
            "classes": data.get("classes", []),
            "primary_class": data.get("primary_class"),
            "detail": data.get("detail"),
        }
