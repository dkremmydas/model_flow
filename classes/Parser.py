import os
import json
import itertools
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from classes.Task import Task
import logging

logger = logging.getLogger(__name__)


class Parser:
    """
    A class to handle parsing of code files, modules, and arguments.
    """
    
    allowed_extensions = {".r", ".rmd", ".gms", ".bat"}
    ignore_dirs = {".git", ".vscode", ".svn", "__pycache__", "venv"}
    pipelines_filename = "model_flow.pipelines.json"
    lists_filename = "model_flow.lists.json"

    @staticmethod
    def parse_range_args(range_args: Optional[List[List[str]]]) -> Dict[str, List[float]]:
        """
        Convert range arguments to value lists.

        Args:
            range_args: A list of range arguments in the format [var, start, end, step].

        Returns:
            A dictionary where keys are variable names and values are lists of floats.
        """
        ranges = {}
        for var, start, end, step in (range_args or []):
            ranges[var] = list(np.arange(float(start), float(end), float(step)))
        return ranges

    @staticmethod
    def parse_value_args(value_args: Optional[List[List[str]]]) -> Dict[str, List[str]]:
        """
        Convert value arguments to lists.

        Args:
            value_args: A list of value arguments in the format [var, value1, value2, ...].

        Returns:
            A dictionary where keys are variable names and values are lists of strings.
        """
        values = {}
        for args in (value_args or []):
            var = args[0]
            values[var] = args[1:]
        return values

    @staticmethod
    def parse_modules(directory: str, on_file=None) -> Dict:
        """
        Recursively parse modules and tasks from the given directory.

        Args:
            directory: The root directory to parse.
            on_file: Optional callback invoked with the path of each candidate
                script file (matching allowed_extensions) as it's scanned, for
                surfacing verbose progress to a caller (e.g. the GUI's rebuild
                action) -- independent of the `logging` calls below, which go
                to the log handlers configured by the CLI, not the GUI.

        Returns:
            A dictionary containing parsed modules and tasks.

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        allowed_extensions = Parser.allowed_extensions
        ignore_dirs = Parser.ignore_dirs
        modules = {}
        total_tasks = 0  # Counter for total tasks found

        try:
            root_path = Path(directory).resolve()
            if not root_path.is_dir():
                raise FileNotFoundError(f"Directory not found: {directory}")

            logger.info(f"Starting module parsing in: {root_path}")

            for root, dirs, files in os.walk(root_path):
                # Filter ignored directories
                dirs[:] = [d for d in dirs if d not in ignore_dirs]

                for file in files:
                    file_ext = os.path.splitext(file)[1].lower()
                    if file_ext in allowed_extensions:
                        file_path = Path(root) / file
                        if on_file:
                            on_file(str(file_path))

                        try:
                            task = Task(str(file_path))
                            if not task.name:
                                continue

                            module_name = task.module or 'Uncategorized'
                            module_data = {
                                "module": module_name,
                                "file": file,
                                "file_path": str(file_path),
                                "filetype": file_ext,
                                "name": task.name,
                                "description": task.description.strip(),
                                "config": task.config,
                            }

                            if module_name not in modules:
                                modules[module_name] = []
                            modules[module_name].append(module_data)
                            total_tasks += 1  # Increment task counter

                        except Exception as e:
                            logger.warning(f"Error parsing {file_path}: {str(e)}")
                            continue

            # Enhanced logging with both module and task counts
            logger.info(f"Found {len(modules)} modules containing {total_tasks} total tasks")
            return modules

        except Exception as e:
            logger.error(f"Error during module parsing: {str(e)}")
            raise

    @staticmethod
    def parse_pipelines(directory: str, modules: Dict[str, List[Dict]],
                         lists: Optional[Dict[str, Dict]] = None, on_file=None) -> Dict[str, List[Dict]]:
        """
        Recursively scan `directory` for per-module model_flow.pipelines.json files,
        validate each declared pipeline's task list against `modules` (the dict
        already produced by parse_modules(directory)), and return the aggregated
        pipelines dict.

        Args:
            directory: same root directory passed to parse_modules.
            modules: output of parse_modules(directory) -- used to validate that
                every task name referenced by a pipeline exists in that same module,
                and to look up each task's config script-names for validating
                per-task overrides/loop parameters (see _normalize_pipeline_tasks).
            lists: output of parse_lists(directory), used to validate that a task's
                loop.parameters list-name references actually exist, and that a
                "zip" loop's referenced lists have equal length. Defaults to {} (no
                known lists) if omitted -- callers with no pipelines using loops
                don't need to supply it.
            on_file: Optional callback invoked with the path of each
                model_flow.pipelines.json file found, as it's scanned.

        Returns:
            Dict[str, List[Dict]]: {module_name: [{"name", "description", "tasks"}, ...]}
                where each "tasks" entry is normalized to
                {"task": name, "overrides": {script_name: value}, "loop": {...} | None}
                regardless of whether it was authored as a plain task-name string or
                an object -- so downstream consumers (Database/ExecutionEngine/GUI)
                never need to branch on the authored shape.

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        ignore_dirs = Parser.ignore_dirs
        lists = lists or {}
        pipelines: Dict[str, List[Dict]] = {}
        existing_names: Dict[str, set] = {}

        root_path = Path(directory).resolve()
        if not root_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            if Parser.pipelines_filename not in files:
                continue

            file_path = Path(root) / Parser.pipelines_filename
            if on_file:
                on_file(str(file_path))

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping malformed pipelines file {file_path}: {e}")
                continue

            module_name = raw.get("module")
            if not module_name:
                logger.warning(f"Skipping {file_path}: missing required 'module' field")
                continue

            known_tasks = {t["name"]: t for t in modules.get(module_name, [])}
            if not known_tasks:
                logger.warning(f"{file_path} declares module '{module_name}' with no known tasks")

            module_names = existing_names.setdefault(module_name, set())

            for entry in raw.get("pipelines", []):
                name = entry.get("name")
                tasks = entry.get("tasks")

                if not name:
                    logger.warning(f"Skipping unnamed pipeline in {file_path}")
                    continue
                if name in module_names:
                    logger.warning(f"Skipping duplicate pipeline '{name}' for module '{module_name}' in {file_path}")
                    continue
                if not tasks or not isinstance(tasks, list):
                    logger.warning(f"Skipping pipeline '{name}' in {file_path}: 'tasks' missing/empty/malformed")
                    continue

                normalized_tasks, error = Parser._normalize_pipeline_tasks(tasks, known_tasks, lists)
                if error:
                    logger.warning(f"Skipping pipeline '{name}' in {file_path}: {error}")
                    continue

                pipelines.setdefault(module_name, []).append({
                    "name": name,
                    "description": (entry.get("description") or "").strip(),
                    "tasks": normalized_tasks,
                })
                module_names.add(name)

        logger.info(f"Found {sum(len(v) for v in pipelines.values())} pipelines across {len(pipelines)} modules")
        return pipelines

    @staticmethod
    def _normalize_pipeline_tasks(tasks: List, known_tasks: Dict[str, Dict],
                                   lists: Dict[str, Dict]) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Validate and normalize one pipeline's "tasks" list. Every entry -- whether
        authored as a plain task-name string or an object with "task"/"overrides"/
        "loop" -- becomes {"task", "overrides", "loop"}. Returns (normalized, None)
        on success, or (None, error_message) on the first problem found -- the
        caller skips the *whole* pipeline on any error, matching the existing rule
        that a single unknown task name already invalidates the entire pipeline
        rather than silently dropping just that one step.
        """
        normalized = []

        for item in tasks:
            if isinstance(item, str):
                task_name, overrides, loop = item, {}, None
            elif isinstance(item, dict):
                task_name = item.get("task")
                overrides = item.get("overrides") or {}
                loop = item.get("loop")
                if not task_name or not isinstance(task_name, str):
                    return None, f"task entry missing required 'task' name: {item!r}"
                if not isinstance(overrides, dict):
                    return None, f"'overrides' must be an object for task '{task_name}'"
            else:
                return None, f"invalid task entry (must be a string or object): {item!r}"

            if task_name not in known_tasks:
                return None, f"unknown task '{task_name}'"

            config_names = {
                c["script_name"] for c in known_tasks[task_name].get("config", []) if "script_name" in c
            }

            unknown_overrides = sorted(set(overrides) - config_names)
            if unknown_overrides:
                return None, f"unknown override parameter(s) {unknown_overrides} for task '{task_name}'"

            if loop is not None:
                if not isinstance(loop, dict):
                    return None, f"'loop' must be an object for task '{task_name}'"

                parameters = loop.get("parameters")
                if not parameters or not isinstance(parameters, dict):
                    return None, f"'loop.parameters' missing/empty/malformed for task '{task_name}'"

                unknown_params = sorted(set(parameters) - config_names)
                if unknown_params:
                    return None, f"unknown loop parameter(s) {unknown_params} for task '{task_name}'"

                overlap = sorted(set(parameters) & set(overrides))
                if overlap:
                    return None, (
                        f"loop parameter(s) {overlap} also present in 'overrides' for task '{task_name}'"
                    )

                unknown_lists = sorted(ln for ln in parameters.values() if ln not in lists)
                if unknown_lists:
                    return None, f"unknown list(s) {unknown_lists} referenced by task '{task_name}'"

                mode = loop.get("mode", "sequential")
                if mode not in ("sequential", "parallel"):
                    return None, f"invalid loop 'mode' {mode!r} for task '{task_name}'"

                combine = loop.get("combine")
                if combine is not None and combine not in ("zip", "product"):
                    return None, f"invalid loop 'combine' {combine!r} for task '{task_name}'"
                if len(parameters) > 1:
                    if combine is None:
                        return None, (
                            f"loop 'combine' ('zip' or 'product') is required when looping over "
                            f"multiple parameters, for task '{task_name}'"
                        )
                    if combine == "zip":
                        # Only the lengths are needed to validate a "zip" loop at
                        # build time -- not the full expand_loop() expansion, which
                        # would needlessly materialize a "product" loop's full
                        # (potentially huge) cartesian combination just to check this.
                        lengths = {len(lists[ln]["elements"]) for ln in parameters.values()}
                        if len(lengths) > 1:
                            return None, f"'zip' loop lists have mismatched lengths for task '{task_name}'"

                max_workers = loop.get("max_workers")
                if max_workers is not None and (
                    not isinstance(max_workers, int) or isinstance(max_workers, bool) or max_workers < 1
                ):
                    return None, f"loop 'max_workers' must be a positive integer for task '{task_name}'"

                loop = {
                    "parameters": parameters,
                    "combine": combine,
                    "mode": mode,
                    "max_workers": max_workers,
                }

            normalized.append({"task": task_name, "overrides": overrides, "loop": loop})

        return normalized, None

    @staticmethod
    def expand_loop(loop: Dict, resolve) -> List[Dict[str, str]]:
        """
        Expand a validated pipeline-task "loop" declaration into an ordered list of
        per-iteration {script_name: value} override dicts.

        `resolve(list_name)` must return that list's elements -- a plain dict
        lookup (`lambda name: lists[name]["elements"]`) at build/validation time,
        or Lists.get_elements at run time. Run time re-resolves current list
        contents rather than trusting a build-time snapshot, since a list's
        elements can change independently of when the pipeline itself was built.
        """
        param_lists = {param: resolve(list_name) for param, list_name in loop["parameters"].items()}

        if len(param_lists) == 1:
            (param, elements), = param_lists.items()
            return [{param: value} for value in elements]

        names = list(param_lists.keys())
        values_per_name = [param_lists[name] for name in names]

        if loop.get("combine") == "zip":
            return [dict(zip(names, combo)) for combo in zip(*values_per_name)]

        return [dict(zip(names, combo)) for combo in itertools.product(*values_per_name)]

    @staticmethod
    def parse_lists(directory: str, on_file=None) -> Dict[str, Dict]:
        """
        Recursively scan `directory` for model_flow.lists.json files -- unlike
        pipelines, these aren't tied to a module, so a list-defining file can sit
        in *any* folder of `directory`, not just its root. Every list collected is
        tagged with the folder it was found in (relative to `directory`, forward
        slashes, "." for the root itself) so that provenance survives once every
        file's lists are merged into one aggregated dict.

        Args:
            directory: same root directory passed to parse_modules.
            on_file: Optional callback invoked with the path of each
                model_flow.lists.json file found, as it's scanned.

        Returns:
            Dict[str, Dict]: {list_name: {"name", "type", "elements", "description", "folder"}}

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        ignore_dirs = Parser.ignore_dirs
        lists: Dict[str, Dict] = {}

        root_path = Path(directory).resolve()
        if not root_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            if Parser.lists_filename not in files:
                continue

            file_path = Path(root) / Parser.lists_filename
            if on_file:
                on_file(str(file_path))

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping malformed lists file {file_path}: {e}")
                continue

            folder = Path(os.path.relpath(root, root_path)).as_posix()

            for entry in raw.get("lists", []):
                name = entry.get("name")
                if not name:
                    logger.warning(f"Skipping unnamed list in {file_path}")
                    continue
                if name in lists:
                    logger.warning(
                        f"Skipping duplicate list '{name}' in {file_path} "
                        f"(already declared in folder '{lists[name]['folder']}')"
                    )
                    continue

                lists[name] = {**entry, "name": name, "folder": folder}

        logger.info(f"Found {len(lists)} lists across {directory}")
        return lists