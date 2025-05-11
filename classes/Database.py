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

        self.data = {}

        # Load the database if it exists
        if self.db_path.exists():
            self.load()
        else:
            raise FileNotFoundError(f"Database file not found at {self.db_path}. Please ensure the file exists.")

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