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
        "Temporary_directory": "Enter the path to the Temporary directory: ",
        "Rscript_exe": "Enter the path to the Rscript executable: ",
        "GAMS_exe": "Enter the path to the gams executable: "
    }
    
    DIRECTORY_KEYS = ["Code_directory", "Database_directory"]  # Keys that must be valid directories
    
    DIRECTORY_CREATE = ["Temporary_directory"]  # Keys that must be created if not exist
    
    

    def __init__(self, config_source: str = None):
        """
        Initialize the Config object.

        Parameters:
            config_source (str): Path to the configuration JSON file or a JSON string.
        """
        self.data = None
        
        if not config_source:
            print("Error: The 'config_source' parameter must be provided.")
            return

        print(config_source)
        
        

        try:
            # Check if the provided config_source is a valid JSON string
            self.data = json.loads(config_source)
            self.config_path = None
        except json.JSONDecodeError:
            # If not a JSON string, assume it's a file path
            self.config_path = Path(config_source)
            if self.config_path.exists():
                try:
                    self.load()
                except Exception as e:
                    print(f"Error loading configuration: {e}")
                    self.data = None
            else:
                print(f"Error: Configuration file not found at {self.config_path}.")
                self.data = None
        except Exception as e:
            print(f"Error initializing configuration: {e}")
            self.data = None
            
        # Validate the required keys
        try:
            self.validate_required_keys()
        except ValueError as e:
            print(f"Validation error: {e}")
            self.data = None
    
        

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
    
    
    def validate_required_keys(self):
        """
        Validate that all required keys exist in the configuration.

        Raises:
            ValueError: If any required key is missing from the configuration.
        """
        missing_keys = [key for key in self.REQUIRED_KEYS if key not in self.data]
        if missing_keys:
            raise ValueError(f"The configuration file is missing required keys: {', '.join(missing_keys)}")


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
            if key in Config.DIRECTORY_KEYS:
                path = Path(value)
                if not path.is_dir():
                    raise ValueError(f"The provided path for '{key}' is not a valid directory: {value}")
            elif key in Config.DIRECTORY_CREATE:
                path = Path(value)
                if not path.exists():
                    print(f"The directory for '{key}' does not exist. Creating it at: {value}")
                    path.mkdir(parents=True, exist_ok=True)
                path = Path(value)
                if not path.is_dir():
                    raise ValueError(f"The provided path for '{key}' is not a valid directory: {value}")
            data[key] = value

        json_string = json.dumps(data)
        config = Config(config_source=json_string)
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
        
        
    def is_empty(self):
        """
        Check if the configuration is empty.

        Returns:
            bool: True if the configuration is empty, False otherwise.
        """
        return not bool(self.data)