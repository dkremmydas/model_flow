import os
import json
import subprocess


class ExecutionEngine:
    """
    Execution engine to run tasks based on their metadata from ifmcap_flow.json.db.
    Uses a configuration file to locate executables and set default parameters.
    """

    def __init__(self, config_path):
        """
        Initialize the execution engine.

        Parameters:
            config_path (str): Path to the configuration JSON file.
        """
        # Load configuration
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, 'r') as config_file:
            self.config = json.load(config_file)

        # Load flow database
        flow_db_path = os.path.join(self.config["Code_directory"], "ifmcap_flow.db.json")
        if not os.path.exists(flow_db_path):
            raise FileNotFoundError(f"IFMCAP flow database not found: {flow_db_path}")
        with open(flow_db_path, 'r') as db_file:
            self.flow_db = json.load(db_file)

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
        if module not in self.flow_db:
            raise ValueError(f"Module '{module}' not found in flow database.")

        tasks = self.flow_db[module]
        for task in tasks:
            if task.get("name") == task_name:
                return task

        raise ValueError(f"Task '{task_name}' not found in module '{module}'.")

    def execute_task(self, module, task_name):
        """
        Execute the given task based on its metadata.

        Parameters:
            module (str): The module name.
            task_name (str): The task name.

        Returns:
            int: The return code of the executed process.
        """
        # Find the task in the flow database
        task_metadata = self.find_task(module, task_name)

        # Extract required fields
        task_file = task_metadata.get("file_path")
        filetype = task_metadata.get("filetype")

        if not task_file or not filetype:
            raise ValueError(f"Task '{task_name}' is missing required fields ('file_path', 'filetype').")

        # Normalize the filetype
        filetype = filetype.lower()

        # Execute based on file type
        if filetype == ".r":
            return self._execute_r_task(task_metadata)
        elif filetype == ".rmd":
            return self._execute_rmd_task(task_metadata)
        elif filetype == ".gms":
            return self._execute_gams_task(task_metadata)
        else:
            raise ValueError(f"Unsupported file type: {filetype}")

    def _execute_r_task(self, task_metadata):
        """
        Execute an R script task.

        Parameters:
            task_metadata (dict): Metadata of the R task.

        Returns:
            int: The return code of the process.
        """
        rscript_path = os.path.normpath(self.config.get("Rscript_exe"))
        task_file = os.path.normpath(task_metadata["file_path"])
        print(task_metadata["file_path"])
        print(task_file)
        
        # Construct key=value arguments
        args_list = []
        if "config" in task_metadata:
            for param in task_metadata["config"]:
                script_name = param.get("script_name")
                script_value = param.get("script_value")
                if script_name and script_value:
                    args_list.append(f'{script_name}={script_value}')

        # Construct the command
        command = [rscript_path] +  [task_file] + args_list
        print(f"Executing R script: {' '.join(command)}")

        # Execute the command
        return subprocess.call(command)

    def _execute_rmd_task(self, task_metadata):
        """
        Execute an R Markdown file by rendering it with rmarkdown::render().

        Parameters:
            task_metadata (dict): Metadata of the R Markdown task.

        Returns:
            int: The return code of the process.
        """
        rscript_path = os.path.normpath(self.config.get("Rscript_exe"))
        pandoc_dir = repr(os.path.normpath(self.config.get("Pandoc_dir")))
        task_file = repr(os.path.normpath(task_metadata["file_path"]))
       

        # Build params dynamically from task config
        params_list = []
        if "config" in task_metadata:
            for param in task_metadata["config"]:
                script_name = param.get("script_name")
                script_value = param.get("script_value")
                if script_name and script_value:
                    params_list.append(f"{script_name}='{script_value}'")

        params_string = ", ".join(params_list)

        # Construct the render command
        render_script = (
            f"Sys.setenv(RSTUDIO_PANDOC={pandoc_dir}); "
            f"rmarkdown::render({task_file}, params=list({params_string}))"
        )
        command = [rscript_path, "-e", render_script]
        print(f"Rendering R Markdown file: {' '.join(command)}")

        # Execute the command
        return subprocess.call(command)

    def _execute_gams_task(self, task_metadata):
        """
        Execute a GAMS task.

        Parameters:
            task_metadata (dict): Metadata of the GAMS task.

        Returns:
            int: The return code of the process.
        """
        gams_exe = os.path.join(self.config["GAMS_path"], "gams.exe")
        default_args = self.config.get("GAMS_default_args", [])
        task_file = task_metadata["file_path"]

        # Construct the command
        command = [gams_exe] + default_args + [task_file]
        print(f"Executing GAMS script: {' '.join(command)}")

        # Execute the command
        return subprocess.call(command)
