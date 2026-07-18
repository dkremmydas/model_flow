import os
import re

class Task:
    """
    Represents a task with its associated annotations, including file metadata,
    task details, and input/output/config variables as direct attributes.
    """

    # Annotation-line patterns, per filetype. Hoisted to named constants (rather
    # than inline literals in each _parse_file_* method) so they can be verified,
    # via test/test_annotation_spec_matches_task_py.py, to stay in sync with
    # annotation-spec.json -- the same patterns the vscode-extension/ helper
    # reimplements in TypeScript for live in-editor diagnostics. Keep these two
    # in sync: a change here without updating the spec fails that test.
    ANNOTATION_PATTERN_R = r'^\s*#@MODELFLOW_(\w+)\s*(.*)$'
    ANNOTATION_PATTERN_GAMS = r'^\*\s*@MODELFLOW_(\w+):?\s*(.*)$'
    ANNOTATION_PATTERN_BAT = r'^::\s*@MODELFLOW_(\w+):?\s*(.*)$'

    # Config annotation "next line" value patterns, per filetype.
    CONFIG_VALUE_PATTERN_R = r'^(\w+)\s*=\s*(.*?)(?:,)?$'
    CONFIG_VALUE_PATTERN_RMD = r'^(\w+)\s*:\s*(.*)$'
    CONFIG_VALUE_PATTERN_GAMS = r'^\$\s*SET\s+(\w+)\s+(.*?)\s*$'
    CONFIG_VALUE_PATTERN_BAT = r'^if\s+not\s+defined\s+(\w+)\s+set\s+"(\w+)=(.*?)"\s*$'

    # Attribute key="value" pairs inside a task/config annotation line, shared
    # across all filetypes.
    ATTRIBUTE_PATTERN = r'(\w+)="([^"]+)"'

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
            self._parse_file_GAMS(lines)
        elif self.filetype == ".bat":
            self._parse_file_BAT(lines)
        else:
            return  # Unsupported file type
        
    
    def _parse_file_GAMS(self, lines):
        """
        Parses annotations from a GAMS (.gms) file
        """

        # Annotation pattern for GAMS
        annotation_pattern = self.ANNOTATION_PATTERN_GAMS

        isDescriptionLine = False

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            match = re.search(annotation_pattern, line)

            if match:
                key, value = match.groups()
                key = key.strip()
                value = value.strip()

                if key == "task":
                    task_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}
                    self.name = task_attributes.get("name", False)
                    self.module = task_attributes.get("module", False)

                elif key == "config":
                    config_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}

                    # Read the next line for the script values
                    if line_number < len(lines):
                        next_line = lines[line_number].strip()

                        # Match assignment in GAMS syntax
                        default_match = re.match(self.CONFIG_VALUE_PATTERN_GAMS, next_line, re.IGNORECASE)

                        if default_match:
                            config_attributes['script_name'] = default_match.group(1).strip()
                            config_attributes['script_value'] = default_match.group(2).strip().replace('"', '')

                    self.config.append(config_attributes)

                elif key == "description_start":
                    isDescriptionLine = True

                elif key == "description_end":
                    isDescriptionLine = False

            else:
                if isDescriptionLine:
                    if line and any(char.isalpha() for char in line):
                        self.description += f"\n{line}"

        # Assign task details if available
        if self.name and self.module:
            print(f"Parsed task: {self.name} from module: {self.module}")



    def _parse_file_BAT(self, lines):
        """
        Parses annotations from a Windows batch (.bat) file
        """

        # Annotation pattern for batch files (:: is the standard "comment" idiom;
        # cmd.exe always ignores it, unlike REM which needs a trailing space)
        annotation_pattern = self.ANNOTATION_PATTERN_BAT

        isDescriptionLine = False

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            match = re.search(annotation_pattern, line)

            if match:
                key, value = match.groups()
                key = key.strip()
                value = value.strip()

                if key == "task":
                    task_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}
                    self.name = task_attributes.get("name", False)
                    self.module = task_attributes.get("module", False)

                elif key == "config":
                    config_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}

                    # The only valid parameter definition is the guarded, quoted form:
                    #   IF NOT DEFINED VAR SET "VAR=value"
                    # The guard means the SET only fires when the variable hasn't already been
                    # supplied via the environment, so an externally-injected override (--set/GUI)
                    # actually survives the script running -- unlike a bare unconditional SET.
                    # A bare/unquoted "set VAR=value", the old unguarded "SET \"VAR=value\"", or a
                    # guard/SET referring to different variable names are all rejected: warn and
                    # skip this parameter entirely rather than recording a malformed entry.
                    next_line = lines[line_number].strip() if line_number < len(lines) else ""

                    default_match = re.match(
                        self.CONFIG_VALUE_PATTERN_BAT,
                        next_line,
                        re.IGNORECASE,
                    )

                    if default_match and default_match.group(1).lower() == default_match.group(2).lower():
                        config_attributes['script_name'] = default_match.group(2).strip()
                        config_attributes['script_value'] = default_match.group(3).strip()
                        self.config.append(config_attributes)
                    else:
                        print(
                            f"Warning: invalid MODELFLOW_config parameter in {self.file_path} "
                            f'at line {line_number + 1}: expected IF NOT DEFINED VAR SET "VAR=value", got: {next_line!r}'
                        )

                elif key == "description_start":
                    isDescriptionLine = True

                elif key == "description_end":
                    isDescriptionLine = False

            else:
                if isDescriptionLine:
                    if line and any(char.isalpha() for char in line):
                        self.description += f"\n{line}"

        # Assign task details if available
        if self.name and self.module:
            print(f"Parsed task: {self.name} from module: {self.module}")

    def _parse_file_R(self,lines):
        """
        Parses annotations from an R file
        """
        
        # Determine the annotation pattern based on the file extension
        annotation_pattern = self.ANNOTATION_PATTERN_R

        isDescriptionLine = 0

        for line_number, line in enumerate(lines, start=1):
            line = line.strip()

            match = re.search(annotation_pattern, line)

            if match:
                key, value = match.groups()
                key = key.strip()
                value = value.strip()


                if key == "task":
                    task_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}
                    self.name = task_attributes.get("name", False)  # Default to False if "name" is not found
                    self.module = task_attributes.get("module", False)  # Default to False if "module" is not found

                elif key == "config":
                    config_attributes = {key: val for key, val in re.findall(self.ATTRIBUTE_PATTERN, value)}

                    # Read the next line for the script values
                    if line_number < len(lines):
                        next_line = lines[line_number].strip()

                        if self.filetype == '.r':
                            default_match = re.match(self.CONFIG_VALUE_PATTERN_R, next_line)

                        elif self.filetype == '.rmd':
                            default_match = re.match(self.CONFIG_VALUE_PATTERN_RMD, next_line)
                            
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
