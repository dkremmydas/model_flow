import os
import re

class Task:
    """
    Represents a task with its associated annotations, including file metadata,
    task details, and input/output/config variables as direct attributes.
    """

    def __init__(self, file_path):
        """
        Initialize the Task object with the provided file path.

        Parameters:
            file_path (str): The path to the task's script file.
        """
        # File metadata
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.filetype = os.path.splitext(file_path)[1].lower()

        # Task-specific attributes
        self.name = False
        self.module = False
        self.previous = False
        self.description = ""
        self.config = []

        # Parse the file for annotations
        self._parse_file()

    def _parse_file(self):
        """
        Parse the file to extract annotations and populate the task metadata.
        """
        
        # Initialize lines as an empty list in case of failure
        lines = []
    
        #open the file
        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
        except UnicodeDecodeError as e:
            # Log the file and error details, then continue
            print(f"Error reading file {self.file_path}: {e}. Skipping this file.")
        
        # Determine the annotation pattern based on the file extension
        if self.filetype in (".r", ".rmd"):
            self._parse_file_R(lines)            
        elif self.filetype == ".gms":
            annotation_pattern = r'^\*\s*@IFMCAP_(\w+):\s*(.*)$'
        else:
            return  # Unsupported file type


    def _parse_file_R(self,lines):
        """
        Parses annotations from an R file
        """
        
        # Determine the annotation pattern based on the file extension
        annotation_pattern = r'^\s*#@IFMCAP_(\w+)\s*(.*)$'
                    
        isDescriptionLine = 0    

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()
            
            match = re.search(annotation_pattern, line)
            
            if match:            
                key, value = match.groups()
                key = key.strip()
                value = value.strip()

                
                if key == "task":
                    task_attributes = {key: val for key, val in re.findall(r'(\w+)="([^"]+)"', value)}
                    self.name = task_attributes.get("name", False)  # Default to False if "name" is not found
                    self.module = task_attributes.get("module", False)  # Default to False if "module" is not found
                    self.previous = task_attributes.get("previous", False)  # Default to False if "previous" is not found

                elif key == "config":
                    config_attributes = {key: val for key, val in re.findall(r'(\w+)="([^"]+)"', value)}

                    # Read the next line for the script values
                    if line_number < len(lines):
                        next_line = lines[line_number].strip()
                        
                        if self.filetype == '.r':
                            default_match = re.match(r'^(\w+)\s*=\s*(.*?)(?:,)?$', next_line)

                        elif self.filetype == '.rmd':
                            default_match = re.match(r'^(\w+)\s*:\s*(.*)$', next_line)
                            
                        if default_match:
                            config_attributes['script_name'] = default_match.group(1).strip().replace('"', '')
                            config_attributes['script_value'] = default_match.group(2).strip().replace('"', '')

                    # Append the annotation entry to the relevant list
                    getattr(self, key).append(config_attributes)
                    
                elif key == "description_start":
                    isDescriptionLine = 1
                    
                elif key == "description_end":
                    isDescriptionLine = 0
                
                
            else:
                if isDescriptionLine == 1:
                    if line and any(char.isalpha() for char in line):
                        self.description += f"\n{line}"
                        
                                        

   
    def __repr__(self):
        """
        String representation of the Task object for debugging.

        Returns:
            str: The string representation of the Task object.
        """
        
        if not self.name:
            return f"<Task {self.filename} - No Tasks>"
        
        def format_list(name, items):
            """
            Format a list with proper indentation for nicer representation.
            """
            if not items:
                return f"{name}: []"
            formatted_items = "\n    ".join(str(item) for item in items)
            return f"{name}:\n    {formatted_items}"

        # Format attributes
        attributes = [
            f"file: {self.filename}",
            f"file_path: {self.file_path}",
            f"filetype: {self.filetype}",
            f"module: {getattr(self, 'module', None)}",
            f"name: {self.name}",
            f"description: {self.description}",
            format_list("config", self.config)
        ]
        
        return f"<Task\n{chr(10).join(attributes)}\n>"
