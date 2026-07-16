import os
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
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
    def parse_modules(directory: str) -> Dict:
        """
        Recursively parse modules and tasks from the given directory.

        Args:
            directory: The root directory to parse.

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
    def parse_pipelines(directory: str, modules: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """
        Recursively scan `directory` for per-module model_flow.pipelines.json files,
        validate each declared pipeline's task list against `modules` (the dict
        already produced by parse_modules(directory)), and return the aggregated
        pipelines dict.

        Args:
            directory: same root directory passed to parse_modules.
            modules: output of parse_modules(directory) -- used to validate that
                every task name referenced by a pipeline exists in that same module.

        Returns:
            Dict[str, List[Dict]]: {module_name: [{"name", "description", "tasks"}, ...]}

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        ignore_dirs = Parser.ignore_dirs
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

            known_tasks = {t["name"] for t in modules.get(module_name, [])}
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
                if not tasks or not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks):
                    logger.warning(f"Skipping pipeline '{name}' in {file_path}: 'tasks' missing/empty/malformed")
                    continue
                missing = [t for t in tasks if t not in known_tasks]
                if missing:
                    logger.warning(f"Skipping pipeline '{name}' in {file_path}: unknown task(s) {missing}")
                    continue

                pipelines.setdefault(module_name, []).append({
                    "name": name,
                    "description": (entry.get("description") or "").strip(),
                    "tasks": tasks,
                })
                module_names.add(name)

        logger.info(f"Found {sum(len(v) for v in pipelines.values())} pipelines across {len(pipelines)} modules")
        return pipelines