import os
import json
import argparse
from task import Task
from dask.distributed import Client, as_completed
from execution_engine import ExecutionEngine
import dask


def parse_modules(directory):
    """
    Recursively parse modules and tasks from the given directory.
    Ignores specified directories and prints the current directory being parsed.

    Parameters:
        directory (str): The root directory to parse.

    Returns:
        dict: A nested dictionary structure containing parsed modules and tasks.
    """
    allowed_extensions = {".r", ".rmd", ".gms"}  # Extensions to include
    ignore_dirs = {".git", ".vscode", ".svn", "__pycache__"}  # Directories to ignore
    modules = {}

    # Walk through the directory structure
    for root, dirs, files in os.walk(directory):
        # Filter out ignored directories in-place
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        # Print the current directory being parsed
        print(f"Parsing directory: {root}")
        
        for file in files:
            # Filter files by allowed extensions
            if os.path.splitext(file)[1].lower() in allowed_extensions:
                file_path = os.path.join(root, file)

                # Parse the task using the Task class
                task = Task(file_path)
                if not task.name:
                    continue

                # Organize tasks by module
                module_name = task.module or 'Uncategorized'
                if module_name not in modules:
                    modules[module_name] = []

                modules[module_name].append({
                    "file": task.filename,
                    "file_path": task.file_path,
                    "filetype": task.filetype,
                    "name": task.name,
                    "previous": task.previous,
                    "description": task.description.strip(),
                    "config": task.config,
                })

    return modules


def build(directory):
    """
    Build the ifmcap_flow.json.db file by parsing the provided directory.

    Parameters:
        directory (str): The root directory containing the modules and tasks.

    Raises:
        FileNotFoundError: If the directory does not exist.
    """
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"The directory '{directory}' does not exist.")

    print(f"Parsing modules and tasks in directory: {directory}")
    modules = parse_modules(directory)

    # Output file path
    output_file = os.path.join(directory, "ifmcap_flow.db.json")

    # Write the parsed data to the JSON database
    with open(output_file, "w") as json_file:
        json.dump(modules, json_file, indent=4)

    print(f"Build complete. Data written to: {output_file}")


def main():
    """
    Main entry point for the script. Parses commands and executes corresponding functions.
    """
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="IFMCAP Flow Tool")
    parser.add_argument(
        "command",
        choices=["build", "run_task"],
        help="The command to execute. Supported commands: build, run_task"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="The configuration file for ifmcap flow."
    )
    parser.add_argument(
        "--module",
        required=False,
        help="The module name of the task to execute."
    )
    parser.add_argument(
        "--task",
        required=False,
        help="The task name to execute."
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tasks in parallel."
    )

    # Parse the arguments
    args = parser.parse_args()

    # Read the configuration file
    with open(args.config, 'r') as config_file:
        config = json.load(config_file)

    # Execute the corresponding command
    if args.command == "build":
        try:
            build(config["Code_directory"])
        except Exception as e:
            print(f"Error: {e}")
    elif args.command == "run_task":
        if not args.module or not args.task:
            print("Error: --module and --task are required for the run_task command.")
        else:
            # Create the execution engine
            try:
                engine = ExecutionEngine(args.config)

                if args.parallel:
                    # Parallel execution using Dask distributed
                    client = Client()
                    future = client.submit(engine.execute_task, args.module, args.task)
                    result = future.result()
                    print(f"Parallel Result: {result}")
                    client.close()
                else:
                    # Sequential execution using Dask single-threaded scheduler
                    result = dask.compute(
                        dask.delayed(engine.execute_task)(args.module, args.task),
                        scheduler="single-threaded"
                    )
                    print(f"Sequential Result: {result[0]}")
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    main()
