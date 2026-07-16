import json
from pathlib import Path
from typing import Dict, List, Optional
from classes.Config import Config  

class Database:
    """
    A class to manage the tasks database (model_flow.db.json).
    """

    def __init__(self, config: Config):
        """
        Initialize the Database object.

        Parameters:
            db_path (str): Path to the database JSON file.
        """
        self.db_path = Path(config.get("Database_directory"), "model_flow.db.json")
        self.user_db_path = Path(config.get("Database_directory"), "model_flow.db_user.json")
        self.pipelines_path = Path(config.get("Database_directory"), "model_flow.pipelines.json")
        self.user_pipelines_path = Path(config.get("Database_directory"), "model_flow.pipelines_user.json")

        self.data = {}
        self.user_data = {}
        self.pipelines_data = {}
        self.user_pipelines_data = {}

        # Load the database if it exists
        if self.db_path.exists():
            self.load()
        else:
            raise FileNotFoundError(f"Database file not found at {self.db_path}. Please ensure the file exists.")

        # The user-override database is optional; it is created lazily on first save.
        if self.user_db_path.exists():
            self._load_user_data()

        # The pipelines database (and its user-override sibling) are both optional --
        # a config still built before pipelines support existed must keep working for
        # task-only workflows (run_task, run_gui) without a forced rebuild.
        if self.pipelines_path.exists():
            self.load_pipelines()

        if self.user_pipelines_path.exists():
            self._load_user_pipelines()

    def load(self):
        """
        Load the database from the JSON file.
        """
        try:
            with open(self.db_path, "r", encoding="utf-8") as db_file:
                self.data = json.load(db_file)
            print(f"Database loaded successfully from {self.db_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in database file: {self.db_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load database: {str(e)}") from e

    def save(self):
        """
        Save the current database to the JSON file.
        """
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
            with open(self.db_path, "w", encoding="utf-8") as db_file:
                json.dump(self.data, db_file, indent=4)
            print(f"Database saved to {self.db_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to save database: {str(e)}") from e

    def load_pipelines(self):
        """
        Load the pipelines database (model_flow.pipelines.json) from disk.
        """
        try:
            with open(self.pipelines_path, "r", encoding="utf-8") as pipelines_file:
                self.pipelines_data = json.load(pipelines_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in pipelines file: {self.pipelines_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load pipelines database: {str(e)}") from e

    def save_pipelines(self):
        """
        Save the current pipelines database to the JSON file.
        """
        try:
            self.pipelines_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.pipelines_path, "w", encoding="utf-8") as pipelines_file:
                json.dump(self.pipelines_data, pipelines_file, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save pipelines database: {str(e)}") from e

    def _load_user_pipelines(self):
        """
        Load the user-authored pipelines database (model_flow.pipelines_user.json) from disk.
        """
        try:
            with open(self.user_pipelines_path, "r", encoding="utf-8") as user_pipelines_file:
                self.user_pipelines_data = json.load(user_pipelines_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in user pipelines file: {self.user_pipelines_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load user pipelines database: {str(e)}") from e

    def _save_user_pipelines(self):
        """
        Save the user-authored pipelines database (model_flow.pipelines_user.json) to disk.
        """
        try:
            self.user_pipelines_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.user_pipelines_path, "w", encoding="utf-8") as user_pipelines_file:
                json.dump(self.user_pipelines_data, user_pipelines_file, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save user pipelines database: {str(e)}") from e

    def list_pipelines(self, module_name: str) -> List[str]:
        """
        Return the names of all pipelines for a module, merging source-declared
        (model_flow.pipelines.json) and user-authored (model_flow.pipelines_user.json)
        pipelines. On a name collision, the source-declared pipeline wins.

        Parameters:
            module_name (str): The name of the module.

        Returns:
            List[str]: Pipeline names for the module.
        """
        source_names = [p["name"] for p in self.pipelines_data.get(module_name, [])]
        user_names = [
            p["name"] for p in self.user_pipelines_data.get(module_name, [])
            if p["name"] not in source_names
        ]
        return source_names + user_names

    def get_pipeline(self, module_name: str, pipeline_name: str) -> Optional[Dict]:
        """
        Get a specific pipeline by module and pipeline name. Source-declared
        pipelines (model_flow.pipelines.json) take precedence over user-authored
        ones (model_flow.pipelines_user.json) on a name collision.

        Parameters:
            module_name (str): The name of the module.
            pipeline_name (str): The name of the pipeline.

        Returns:
            Dict: The pipeline metadata, or None if the pipeline doesn't exist.
        """
        for pipeline in self.pipelines_data.get(module_name, []):
            if pipeline.get("name") == pipeline_name:
                return pipeline
        for pipeline in self.user_pipelines_data.get(module_name, []):
            if pipeline.get("name") == pipeline_name:
                return pipeline
        return None

    def add_pipeline(self, module_name: str, pipeline: Dict, user: bool = False):
        """
        Add a new pipeline to a module.

        Parameters:
            module_name (str): The name of the module.
            pipeline (Dict): The pipeline metadata to add (e.g. {"name", "tasks", "description"}).
            user (bool): If True, adds to the user-authored pipelines database and
                persists immediately. If False (default), adds to the source-declared
                pipelines database in-memory only -- caller must call save_pipelines()
                (mirrors add_task's contract, since source data is build-regenerated anyway).
        """
        if user:
            self.user_pipelines_data.setdefault(module_name, []).append(pipeline)
            self._save_user_pipelines()
        else:
            self.pipelines_data.setdefault(module_name, []).append(pipeline)

    def delete_pipeline(self, module_name: str, pipeline_name: str, user: bool = False):
        """
        Delete a specific pipeline from a module.

        Parameters:
            module_name (str): The name of the module.
            pipeline_name (str): The name of the pipeline to delete.
            user (bool): If True, deletes from the user-authored pipelines database
                and persists immediately. If False (default), deletes from the
                source-declared pipelines database in-memory only.
        """
        if user:
            module_pipelines = self.user_pipelines_data.get(module_name)
            if module_pipelines:
                self.user_pipelines_data[module_name] = [
                    p for p in module_pipelines if p.get("name") != pipeline_name
                ]
                self._save_user_pipelines()
        else:
            module_pipelines = self.pipelines_data.get(module_name)
            if module_pipelines:
                self.pipelines_data[module_name] = [
                    p for p in module_pipelines if p.get("name") != pipeline_name
                ]

    def _load_user_data(self):
        """
        Load the user-override database (model_flow.db_user.json) from disk.
        """
        try:
            with open(self.user_db_path, "r", encoding="utf-8") as user_db_file:
                self.user_data = json.load(user_db_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in user database file: {self.user_db_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load user database: {str(e)}") from e

    def _save_user_data(self):
        """
        Save the user-override database (model_flow.db_user.json) to disk.
        """
        try:
            self.user_db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.user_db_path, "w", encoding="utf-8") as user_db_file:
                json.dump(self.user_data, user_db_file, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save user database: {str(e)}") from e

    def get_user_values(self, module_name: str, task_name: str) -> Dict[str, List[str]]:
        """
        Return the user-defined value history for a task's parameters.

        Parameters:
            module_name (str): The name of the module.
            task_name (str): The name of the task.

        Returns:
            Dict[str, List[str]]: A mapping of script_name to its history of user-entered
            values (most recent last), or an empty dict if none have been recorded.
        """
        for task in self.user_data.get(module_name, []):
            if task.get("name") == task_name:
                return {c["name"]: c.get("script_value", []) for c in task.get("config", [])}
        return {}

    def add_user_value(self, module_name: str, task_name: str, script_name: str, value: str):
        """
        Record a user-entered value for a task parameter, appending it to the parameter's
        history (most recent last) and persisting the user-override database.

        Parameters:
            module_name (str): The name of the module.
            task_name (str): The name of the task.
            script_name (str): The name of the parameter as defined in the script.
            value (str): The value to record.
        """
        module_tasks = self.user_data.setdefault(module_name, [])

        task = next((t for t in module_tasks if t.get("name") == task_name), None)
        if task is None:
            task = {"name": task_name, "config": []}
            module_tasks.append(task)

        param = next((c for c in task["config"] if c.get("name") == script_name), None)
        if param is None:
            param = {"name": script_name, "script_value": []}
            task["config"].append(param)

        if not param["script_value"] or param["script_value"][-1] != value:
            param["script_value"].append(value)

        self._save_user_data()

    def list_module_tasks(self, module_name: str) -> List[Dict]:
        """
        Return a list of tasks for a specific module.

        Parameters:
            module_name (str): The name of the module.

        Returns:
            List[Dict]: A list of tasks in the module, or an empty list if the module doesn't exist.
        """
        module_tasks = self.get_module(module_name) or []
        return [f"{task['name']}" for task in module_tasks]

    def list_modules(self) -> List[str]:
        """
        Return a list of all module names in the database.

        Returns:
            List[str]: A list of module names.
        """
        return list(self.data.keys())

    def get_module(self, module_name: str) -> Optional[List[Dict]]:
        """
        Get all tasks for a specific module.

        Parameters:
            module_name (str): The name of the module.

        Returns:
            List[Dict]: A list of tasks in the module, or None if the module doesn't exist.
        """
        return self.data.get(module_name)

    def get_task(self, module_name: str, task_name: str) -> Optional[Dict]:
        """
        Get a specific task by module and task name.

        Parameters:
            module_name (str): The name of the module.
            task_name (str): The name of the task.

        Returns:
            Dict: The task metadata, or None if the task doesn't exist.
        """
        module = self.get_module(module_name)
        if module:
            for task in module:
                if task.get("name") == task_name:
                    return task
        return None

    def add_module(self, module_name: str):
        """
        Add a new module to the database.

        Parameters:
            module_name (str): The name of the module to add.
        """
        if module_name not in self.data:
            self.data[module_name] = []

    def add_task(self, module_name: str, task: Dict):
        """
        Add a new task to a module.

        Parameters:
            module_name (str): The name of the module.
            task (Dict): The task metadata to add.
        """
        self.add_module(module_name)
        self.data[module_name].append(task)

    def delete_task(self, module_name: str, task_name: str):
        """
        Delete a specific task from a module.

        Parameters:
            module_name (str): The name of the module.
            task_name (str): The name of the task to delete.
        """
        module = self.get_module(module_name)
        if module:
            self.data[module_name] = [task for task in module if task.get("name") != task_name]

    def __str__(self):
        """
        Return a human-readable string representation of the database.
        """
        return f"Database:\n{json.dumps(self.data, indent=4)}"

    def __repr__(self):
        """
        Return a developer-friendly string representation of the database.
        """
        return f"Database(db_path='{self.db_path}', data={json.dumps(self.data, indent=4)})"