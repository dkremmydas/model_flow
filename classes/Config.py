import json
from pathlib import Path


class Config:
    """
    A class to manage the configuration for the Model Flow application.
    """

    # Static dictionary of key parameters
    REQUIRED_KEYS = {
        "Code_directory": "Enter the path to the Code directory: ",
        "Database_directory": "Enter the path to the Database directory: ",
        "Rscript_exe": "Enter the path to the Rscript executable: ",
        "GAMS_exe": "Enter the path to the gams executable: "
    }

    def __init__(self, config_path: str = None, json_string: str = None):
        """
        Initialize the Config object.

        Parameters:
            config_path (str): Path to the configuration JSON file.
            json_string (str): JSON string to initialize the configuration.
        """
        self.data = {}

        if config_path and json_string:
            raise ValueError("Only one of 'config_path' or 'json_string' should be provided.")

        if config_path:
            self.config_path = Path(config_path)
            # Load the configuration file if it exists
            if self.config_path.exists():
                self.load()
            else:
                print(f"Configuration file not found at {self.config_path}. A new one will be created.")
        elif json_string:
            self.config_path = None
            try:
                self.data = json.loads(json_string)
            except json.JSONDecodeError as e:
                raise ValueError("Invalid JSON string provided.") from e
        else:
            raise ValueError("Either 'config_path' or 'json_string' must be provided.")

        if config_path:
            self.config_path = Path(config_path)
            self.data = {}

            # Load the configuration file if it exists
            if self.config_path.exists():
                self.load()
            else:
                print(f"Configuration file not found at {self.config_path}. A new one will be created.")
        else:
            self.config_path = None

    def load(self):
        """
        Load the configuration from the JSON file.
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                self.data = json.load(config_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {self.config_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {str(e)}") from e

    def save(self):
        """
        Save the current configuration to the JSON file.
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
            with open(self.config_path, "w", encoding="utf-8") as config_file:
                json.dump(self.data, config_file, indent=4)
            print(f"Configuration saved to {self.config_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to save configuration: {str(e)}") from e

    def get(self, key: str, default=None):
        """
        Get a configuration value.

        Parameters:
            key (str): The key to retrieve.
            default: The default value to return if the key is not found.

        Returns:
            The value associated with the key, or the default value if the key is not found.
        """
        return self.data.get(key, default)

    def set(self, key: str, value):
        """
        Set a configuration value.

        Parameters:
            key (str): The key to set.
            value: The value to associate with the key.
        """
        self.data[key] = value

    def __str__(self):
        """
        Return a human-readable string representation of the configuration.
        """
        return f"Configuration:\n{json.dumps(self.data, indent=4)}"

    def __repr__(self):
        """
        Return a developer-friendly string representation of the configuration.
        """
        return f"Config(config_path='{self.config_path}', data={json.dumps(self.data, indent=4)})"

    @staticmethod
    def create_from_user_input():
        """
        Create a new Config instance by asking the user for required parameters and save it to a JSON file.

        Returns:
            Config: A new Config instance with user-provided values.
        """
        print("Creating a new configuration...")
        data = {}
        for key, prompt in Config.REQUIRED_KEYS.items():
            value = input(prompt).strip()
            data[key] = value
            
        json_string = json.dumps(data)
        config = Config(json_string=json_string)
        return config

    @staticmethod
    def save_to_file(config_instance, file_path: str):
        """
        Save a Config instance to a JSON file.

        Parameters:
            config_instance (Config): The Config instance to save.
            file_path (str): The path to the JSON file.
        """
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists
            with open(file_path, "w", encoding="utf-8") as config_file:
                json.dump(config_instance.data, config_file, indent=4)
            print(f"Configuration saved to {file_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to save configuration: {str(e)}") from e