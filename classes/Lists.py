import json
from pathlib import Path
from typing import Dict, List, Optional

from classes.Config import Config


class Lists:
    """
    Reads named value lists (e.g. NUTS0/NUTS2 region codes) so other parts of the
    code can look them up by name instead of hard-coding/duplicating the values.

    Unlike Database, the two files this reads live in different directories and
    play different roles:
      - model_flow.lists.json, at the root of Code_directory -- the shared,
        model-wide lists that ship with the model. Not discovered by scanning
        (there's no script annotation for lists), so it's a plain hand-maintained
        file, read as-is.
      - model_flow.lists_user.json, in Database_directory -- each user's own
        lists, defined without editing the shared source file.

    Both files are optional (mirrors Database's pipelines/pipelines_user
    optionality) so a config without any lists defined yet keeps working.
    """

    lists_filename = "model_flow.lists.json"
    user_lists_filename = "model_flow.lists_user.json"

    def __init__(self, config: Config):
        """
        Initialize the Lists object.

        Parameters:
            config (Config): Config instance providing Code_directory/Database_directory.
        """
        self.lists_path = Path(config.get("Code_directory"), self.lists_filename)
        self.user_lists_path = Path(config.get("Database_directory"), self.user_lists_filename)

        self.lists_data: Dict[str, Dict] = {}
        self.user_lists_data: Dict[str, Dict] = {}

        if self.lists_path.exists():
            self.load()

        if self.user_lists_path.exists():
            self.load_user()

    def load(self):
        """
        Load the shared lists file (model_flow.lists.json) from disk.
        """
        try:
            with open(self.lists_path, "r", encoding="utf-8") as lists_file:
                raw = json.load(lists_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in lists file: {self.lists_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load lists file: {str(e)}") from e

        self.lists_data = {entry["name"]: entry for entry in raw.get("lists", []) if entry.get("name")}

    def save(self):
        """
        Persist the shared lists (model_flow.lists.json) to disk. Not called
        automatically by add_list/delete_list when user=False -- mirrors
        Database.save_pipelines' non-auto-persist contract for source data.
        """
        try:
            self.lists_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.lists_path, "w", encoding="utf-8") as lists_file:
                json.dump({"lists": list(self.lists_data.values())}, lists_file, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save lists file: {str(e)}") from e

    def load_user(self):
        """
        Load the user-authored lists file (model_flow.lists_user.json) from disk.
        """
        try:
            with open(self.user_lists_path, "r", encoding="utf-8") as user_lists_file:
                raw = json.load(user_lists_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in user lists file: {self.user_lists_path}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load user lists file: {str(e)}") from e

        self.user_lists_data = {entry["name"]: entry for entry in raw.get("lists", []) if entry.get("name")}

    def _save_user(self):
        """
        Persist the user-authored lists (model_flow.lists_user.json) to disk.
        """
        try:
            self.user_lists_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.user_lists_path, "w", encoding="utf-8") as user_lists_file:
                json.dump({"lists": list(self.user_lists_data.values())}, user_lists_file, indent=4)
        except Exception as e:
            raise RuntimeError(f"Failed to save user lists file: {str(e)}") from e

    def list_names(self) -> List[str]:
        """
        Return the names of all lists, merging shared (model_flow.lists.json) and
        user-authored (model_flow.lists_user.json) lists. On a name collision, the
        shared list wins (mirrors Database.list_pipelines).

        Returns:
            List[str]: All list names.
        """
        names = list(self.lists_data.keys())
        names += [name for name in self.user_lists_data if name not in self.lists_data]
        return names

    def get_list(self, name: str) -> Optional[Dict]:
        """
        Get a specific list's full entry by name. The shared list (model_flow.lists.json)
        takes precedence over a user-authored one (model_flow.lists_user.json) on a
        name collision.

        Parameters:
            name (str): The list's name.

        Returns:
            Dict: The list entry ({name, type, elements, description?}), or None if
            no list with that name exists.
        """
        if name in self.lists_data:
            return self.lists_data[name]
        return self.user_lists_data.get(name)

    def get_elements(self, name: str) -> Optional[List]:
        """
        Get a specific list's elements by name.

        Parameters:
            name (str): The list's name.

        Returns:
            List: The list's elements, or None if no list with that name exists.
        """
        entry = self.get_list(name)
        return entry.get("elements") if entry else None

    def add_list(self, list_entry: Dict, user: bool = True):
        """
        Add (or replace) a list.

        Parameters:
            list_entry (Dict): The list metadata to add (e.g. {"name", "type", "elements", "description"}).
            user (bool): If True (default), adds to the user-authored lists file and
                persists immediately (mirrors Database.add_user_value's auto-persist
                contract). If False, adds to the shared lists file in-memory only --
                caller must call save().

        Raises:
            ValueError: If list_entry has no 'name'.
        """
        name = list_entry.get("name")
        if not name:
            raise ValueError("list_entry requires a 'name'")

        if user:
            self.user_lists_data[name] = list_entry
            self._save_user()
        else:
            self.lists_data[name] = list_entry

    def delete_list(self, name: str, user: bool = True) -> bool:
        """
        Delete a specific list by name.

        Parameters:
            name (str): The list's name.
            user (bool): If True (default), deletes from the user-authored lists file
                and persists immediately. If False, deletes from the shared lists file
                in-memory only -- caller must call save().

        Returns:
            bool: True if a list with that name was found and deleted, False otherwise.
        """
        store = self.user_lists_data if user else self.lists_data
        if name not in store:
            return False

        del store[name]
        if user:
            self._save_user()
        return True

    def __str__(self):
        """
        Return a human-readable string representation of the lists.
        """
        return f"Lists:\n{json.dumps({'lists': list(self.lists_data.values())}, indent=4)}"

    def __repr__(self):
        """
        Return a developer-friendly string representation of the lists.
        """
        return f"Lists(lists_path='{self.lists_path}', names={self.list_names()})"
