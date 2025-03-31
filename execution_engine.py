import os
import json
import subprocess
import logging
from pathlib import Path


class ExecutionEngine:
    """
    Execution engine to run tasks based on their metadata from ifmcap_flow.db.json.
    Uses a configuration file to locate executables and set default parameters.
    """

    def __init__(self, config_path):
        """
        Initialize the execution engine.

        Parameters:
            config_path (str): Path to the configuration JSON file.

        Raises:
            FileNotFoundError: If config or database file doesn't exist
            KeyError: If required config keys are missing
            json.JSONDecodeError: If config or database file is malformed
        """
        self.logger = logging.getLogger(__name__)
        
        try:
            # Load configuration
            with open(config_path, 'r') as config_file:
                self.config = json.load(config_file)
            
            # Validate required config keys
            required_keys = ['Database_directory', 'Rscript_exe', 'GAMS_exe', 'Pandoc_dir']
            for key in required_keys:
                if key not in self.config:
                    raise KeyError(f"Missing required config key: {key}")

            # Load flow database from configured Database_directory
            db_path = Path(self.config["Database_directory"]) / "ifmcap_flow.db.json"
            if not db_path.exists():
                raise FileNotFoundError(f"IFMCAP flow database not found: {db_path}")
            
            with open(db_path, 'r') as db_file:
                self.flow_db = json.load(db_file)
                
            self.logger.info(f"Initialized ExecutionEngine with database at {db_path}")

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {config_path}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize ExecutionEngine: {str(e)}")
            raise

    def find_task(self, module, task_name):
        """
        Find task metadata by module and task name.

        Parameters:
            module (str): The module name.
            task_name (str): The task name.

        Returns:
            dict: The metadata of the task.

        Raises:
            ValueError: If the task or module is not found.
        """
        try:
            if module not in self.flow_db:
                raise ValueError(f"Module '{module}' not found in flow database.")

            for task in self.flow_db[module]:
                if task.get("name") == task_name:
                    return task

            raise ValueError(f"Task '{task_name}' not found in module '{module}'.")

        except Exception as e:
            self.logger.error(f"Task lookup failed: {str(e)}")
            raise

    def execute_task(self, module, task_name):
        """
        Execute the given task based on its metadata.

        Parameters:
            module (str): The module name.
            task_name (str): The task name.

        Returns:
            int: The return code of the executed process.

        Raises:
            ValueError: If required task metadata is missing
            RuntimeError: If execution fails
        """
        try:
            task_metadata = self.find_task(module, task_name)
            self.logger.info(f"Executing task: {module}/{task_name}")

            # Validate required fields
            if not all(key in task_metadata for key in ['file_path', 'filetype']):
                raise ValueError(f"Task metadata missing required fields: {task_metadata}")

            filetype = task_metadata['filetype'].lower()
            task_file = Path(task_metadata['file_path'])

            if not task_file.exists():
                raise FileNotFoundError(f"Task file not found: {task_file}")

            # Execute based on file type
            if filetype == ".r":
                return self._execute_r_task(task_metadata)
            elif filetype == ".rmd":
                return self._execute_rmd_task(task_metadata)
            elif filetype == ".gms":
                return self._execute_gams_task(task_metadata)
            else:
                raise ValueError(f"Unsupported file type: {filetype}")

        except Exception as e:
            self.logger.error(f"Task execution failed: {str(e)}")
            raise RuntimeError(f"Failed to execute task {module}/{task_name}: {str(e)}") from e

    def _execute_r_task(self, task_metadata):
        """Execute an R script task."""
        try:
            rscript_path = Path(self.config["Rscript_exe"])
            task_file = Path(task_metadata["file_path"])
            
            # Convert Windows paths to R-friendly format
            def r_path(path):
                return str(path).replace('\\', '/')
            
            args_list = []
            for param in task_metadata.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    # Escape backslashes in parameter values too
                    value = str(param['script_value']).replace('\\', '/')
                    args_list.append(f"{param['script_name']}={value}")

            command = [str(rscript_path), r_path(task_file)] + args_list
            self.logger.info(f"Executing R script: {' '.join(command)}")
            
            return subprocess.call(command)
            
        except Exception as e:
            self.logger.error(f"R task execution failed: {str(e)}")
            raise

    def _execute_rmd_task(self, task_metadata):
        """Execute an R Markdown task."""
        try:
            rscript_path = Path(self.config["Rscript_exe"])
            pandoc_dir = Path(self.config["Pandoc_dir"])
            task_file = Path(task_metadata["file_path"])

            # Convert Windows paths to R-friendly format
            def r_path(path):
                return str(path).replace('\\', '/')
            
            params_list = []
            for param in task_metadata.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    # Escape backslashes in parameter values
                    value = str(param['script_value']).replace('\\', '/')
                    params_list.append(f"{param['script_name']}='{value}'")

            render_script = (
                f"Sys.setenv(RSTUDIO_PANDOC='{r_path(pandoc_dir)}'); "
                f"rmarkdown::render('{r_path(task_file)}', params=list({', '.join(params_list)}))"
            )
            command = [str(rscript_path), "-e", render_script]
            self.logger.info(f"Rendering R Markdown: {' '.join(command)}")
            
            return subprocess.call(command)
            
        except Exception as e:
            self.logger.error(f"R Markdown task execution failed: {str(e)}")
            raise

    def _execute_gams_task(self, task_metadata):
        """Execute a GAMS task."""
        try:
            gams_exe = Path(self.config["GAMS_exe"])
            task_file = Path(task_metadata["file_path"])

            args_list = []
            for param in task_metadata.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    args_list.append(f"{param['script_name']}={param['script_value']}")

            command = [str(gams_exe), str(task_file)] + args_list
            self.logger.info(f"Executing GAMS script: {' '.join(command)}")
            
            return subprocess.call(command)
            
        except Exception as e:
            self.logger.error(f"GAMS task execution failed: {str(e)}")
            raise