import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from classes.Task import Task
import logging

logger = logging.getLogger(__name__)


class Parser:
    """
    A class to handle parsing of code files, modules, and arguments.
    """
    
    allowed_extensions = {".r", ".rmd", ".gms"}
    ignore_dirs = {".git", ".vscode", ".svn", "__pycache__", "venv"}

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