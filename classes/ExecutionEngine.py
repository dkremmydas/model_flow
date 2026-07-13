import os
import json
import copy
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional
from classes.Database import Database
from classes.Config import Config
from classes.Task import Task


@dataclass
class ExecutionResult:
    """Result of a task execution with captured output (capture_output=True)."""
    returncode: int
    stdout: Optional[str]
    stderr: Optional[str]


class ExecutionEngine:
    """
    Execution engine to run tasks based on their metadata from model_flow.db.json.
    Uses a configuration file to locate executables and set default parameters.
    """

    def __init__(self, config: Config):
        """
        Initialize the execution engine with the provided configuration.

        Parameters:
            config (dict): A dictionary containing configuration details such as paths to executables,
                   directories, and other necessary settings.

        Raises:
            ValueError: If the configuration is missing required fields or the database directory is invalid.
            Exception: If any other error occurs during initialization.
        """
        self.logger = logging.getLogger(__name__)
        
        try:
            # Use provided configuration
            self.config = config
            self.database = Database(config)
            
            self.logger.info("Initialized ExecutionEngine with provided database instance.")

        except Exception as e:
            self.logger.error(f"Failed to initialize ExecutionEngine: {str(e)}")
            raise

    
    def execute_task(self, module: str, task_name: str, output_dir: Optional[str] = None,
                      overrides: Optional[Dict[str, str]] = None, capture_output: bool = False):
        """
        Execute the given task based on its metadata.

        Parameters:
            module (str): The module name.
            task_name (str): The task name.
            output_dir (str, optional): Directory for output files. Defaults to config's Temporary_directory.
            overrides (dict, optional): Mapping of script_name -> value to override the task's
                default config values for this run only (does not mutate the underlying database).
            capture_output (bool): If True, capture stdout/stderr instead of inheriting the
                parent process's stdio and return an ExecutionResult. Needed by front ends
                (like the Textual GUI) whose own terminal rendering would otherwise be corrupted
                by an inherited child process stdio. Defaults to False (CLI behavior: live-streamed
                output to the console, returns an int return code) so existing CLI behavior is unchanged.

        Returns:
            int: The return code of the executed process (capture_output=False).
            ExecutionResult: The captured result (capture_output=True).

        Raises:
            ValueError: If required task metadata is missing
            RuntimeError: If execution fails
        """
        try:
            task = self.database.get_task(module, task_name)

            self.logger.info(f"Executing task: {module}/{task_name}")

            if overrides:
                task = copy.deepcopy(task)
                for param in task.get("config", []):
                    if param.get("script_name") in overrides:
                        param["script_value"] = overrides[param["script_name"]]

            filetype = task['filetype'].lower()

            # Determine output directory (parameter > config > None)
            final_output_dir = output_dir or self.config.get("Temporary_directory")

            # Execute based on file type
            if filetype == ".r":
                return self._execute_r_task(task, capture_output=capture_output)
            elif filetype == ".rmd":
                return self._execute_rmd_task(task, final_output_dir, capture_output=capture_output)
            elif filetype == ".gms":
                return self._execute_gams_task(task, capture_output=capture_output)
            else:
                raise ValueError(f"Unsupported file type: {filetype}")

        except Exception as e:
            self.logger.error(f"Task execution failed: {str(e)}")
            raise RuntimeError(f"Failed to execute task {module}/{task_name}: {str(e)}") from e
    
    
    def _config_path(self, key: str) -> Path:
        """
        Fetch a config value expected to be a filesystem path, raising a clear,
        actionable error instead of a cryptic TypeError from Path(None) if the
        key is missing or empty (e.g. an optional key like Pandoc_dir that
        Config does not enforce as required).
        """
        value = self.config.get(key)
        if not value:
            raise ValueError(f"'{key}' is not set in the configuration file.")
        return Path(value)

    def _run(self, command, capture_output: bool):
        """
        Run a command, either inheriting the parent process's stdio (CLI default,
        live-streamed output, returns an int) or capturing stdout/stderr (GUI use,
        returns an ExecutionResult) so a Textual TUI's own rendering isn't corrupted
        by an inherited child process stdio.
        """
        if capture_output:
            result = subprocess.run(command, capture_output=True, text=True)
            return ExecutionResult(result.returncode, result.stdout, result.stderr)
        return subprocess.call(command)

    def _execute_r_task(self, task: Task, capture_output: bool = False):
        """Execute an R script task."""

        try:
            rscript_path = self._config_path("Rscript_exe")
            task_file = Path(task["file_path"])

            # Convert Windows paths to R-friendly format
            def r_path(path):
                return str(path).replace('\\', '/')

            args_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    # Escape backslashes in parameter values too
                    value = str(param['script_value']).replace('\\', '/')
                    args_list.append(f"{param['script_name']}={value}")

            command = [str(rscript_path), r_path(task_file)] + args_list
            self.logger.info(f"Executing R script: {' '.join(command)}")

            return self._run(command, capture_output)

        except Exception as e:
            self.logger.error(f"R task execution failed: {str(e)}")
            raise

    def _execute_rmd_task(self, task: Task, output_dir=None, capture_output: bool = False):
        """Execute an R Markdown task with output directory support and strict type handling."""
        try:
            # Get required paths from config
            rscript_path = self._config_path("Rscript_exe")
            pandoc_dir = self._config_path("Pandoc_dir")
            gams_dir = self._config_path("GAMS_exe").parent
            task_file = Path(task["file_path"])

            # Set output directory (default to config's Temporary_directory or current dir)
            output_dir = Path(output_dir or self.config.get("Temporary_directory", "."))
            if not output_dir.exists():
                raise FileNotFoundError(f"Output directory does not exist: {output_dir}")
            if not output_dir.is_dir():
                raise NotADirectoryError(f"Path is not a directory: {output_dir}")

            # Generate output filename
            task_name = task.get('name', 'output').replace(' ', '_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output_file = output_dir / f"{task_name}_{timestamp}.html"

            def r_path(path):
                """Convert Windows paths to R-friendly format"""
                return str(path).replace('\\', '/')
            
            def format_param_value(param):
                """Format parameter value according to its type"""
                value = param['script_value']
                
                # Handle numeric parameters
                if param.get('type') == 'number':
                    try:
                        if isinstance(value, (int, float)):
                            return str(value)
                        # Convert string to number if needed
                        return str(float(value) if '.' in str(value) else int(value))
                    except (ValueError, TypeError):
                        self.logger.warning(
                            f"Couldn't convert {param['script_name']} value '{value}' to number"
                        )
                
                # Default string handling
                return f"'{str(value).replace('\\', '/')}'"
            
            # Set environment variables
            env_script = (
                f"Sys.setenv(RSTUDIO_PANDOC='{r_path(pandoc_dir)}'); "
                f"Sys.setenv(PATH=paste('{r_path(gams_dir)}', Sys.getenv('PATH'), sep=';')); "
            )
            
            # Prepare parameters with type handling
            params_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    params_list.append(f"{param['script_name']}={format_param_value(param)}")

            # Build render command with output control
            render_script = (
                f"{env_script}"
                f"rmarkdown::render("
                f"input = '{r_path(task_file)}', "
                f"output_file = '{r_path(output_file)}', "
                f"params = list({', '.join(params_list)}), "
                f"intermediates_dir = '{r_path(output_dir)}', "
                f"knit_root_dir = '{r_path(output_dir)}'"
                f")"
            )

            command = [str(rscript_path), "-e", render_script]
            self.logger.info(f"Running {command}")
            self.logger.info(f"Rendering to {output_file}")

            result = self._run(command, capture_output)
            returncode = result.returncode if isinstance(result, ExecutionResult) else result
            if returncode == 0:
                self.logger.info(f"Successfully created: {output_file}")
            return result

        except Exception as e:
            self.logger.error(f"R Markdown execution failed: {str(e)}")
            raise

    def _execute_gams_task(self, task: Task, capture_output: bool = False):
        """Execute a GAMS task."""
        try:
            gams_exe = self._config_path("GAMS_exe")
            task_file = Path(task["file_path"])

            args_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    args_list.append(f"{param['script_name']}={param['script_value']}")

            command = [str(gams_exe), str(task_file)] + args_list
            self.logger.info(f"Executing GAMS script: {' '.join(command)}")

            return self._run(command, capture_output)

        except Exception as e:
            self.logger.error(f"GAMS task execution failed: {str(e)}")
            raise