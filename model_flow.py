#!/usr/bin/env python3
"""
MODEL Flow - Main command-line interface for managing MODELFLOW workflows
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from classes.Task import Task
from classes.ExecutionEngine import ExecutionEngine
from classes.Config import Config  # Ensure the Config class is imported
from textual_gui.app import ModelFlowApp  # Import the Textual GUI application

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def build(config: Config) -> None:
    """
    Build the model_flow.json.db file by scanning Code_directory 
    and saving to Database_directory from config
    
    Args:
        config: Config instance containing configuration details
        
    Raises:
        FileNotFoundError: If directories don't exist
        PermissionError: If write access is denied
    """
    try:
        code_dir = Path(config.get("Code_directory"))
        db_dir = Path(config.get("Database_directory"))
        
        if not code_dir.exists():
            raise FileNotFoundError(f"Code directory not found: {code_dir}")

        logger.info(f"Scanning code directory: {code_dir}")
        from classes.Parser import Parser  # Import the Parser class
        modules = Parser.parse_modules(str(code_dir))  # Use the Parser's parse_modules method
        
        output_file = db_dir / "model_flow.db.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(modules, f, indent=4, ensure_ascii=False)
            
        # Detailed success message
        module_count = len(modules)
        task_count = sum(len(tasks) for tasks in modules.values())
        logger.info(
            f"Build successful! Database saved to {output_file}\n"
            f"Summary: {module_count} modules, {task_count} tasks"
        )
        
    except Exception as e:
        logger.error(f"Build failed: {str(e)}")
        raise


def list_tasks(config_path: str, module_filter: Optional[str] = None) -> None:
    """
    List all available tasks from the database in a clean tree format
    
    Args:
        config_path: Path to the configuration file
        module_filter: Optional module name to filter tasks
        
    Raises:
        FileNotFoundError: If config or database file doesn't exist
        json.JSONDecodeError: If config or database file is malformed
        KeyError: If required config keys are missing
    """
    try:
        # Load and validate configuration
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
        
        db_path = Path(config["Database_directory"]) / "model_flow.db.json"
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found at {db_path}. Run 'build' command first.")
        
        with open(db_path, 'r', encoding='utf-8') as f:
            modules = json.load(f)
        
        # Apply module filter if specified
        if module_filter:
            modules = {k: v for k, v in modules.items() if k == module_filter}
            if not modules:
                print(f"\nNo tasks found in module: {module_filter}")
                return
        
        # Clean output formatting
        print("\n┌────────────────────────────────────────┐")
        print("│        MODEL FLOW TASK DIRECTORY        │")
        print("└─────────────────────────────────────────┘")
        
        for module_idx, (module_name, tasks) in enumerate(modules.items(), 1):
            # Module header with subtle divider
            if module_idx > 1:
                print("  │")
            print(f"  ┌── {module_name}")
            
            # Task listing
            for task_idx, task in enumerate(tasks, 1):
                prefix = "  │   ├─" if task_idx < len(tasks) else "  │   └─"
                print(f"{prefix} {task.get('name', 'Unnamed Task')}")
        
        # Summary footer
        total_tasks = sum(len(tasks) for tasks in modules.values())
        print("\n  📂 Total modules:", len(modules))
        print("  📝 Total tasks:  ", total_tasks)
        print("─" * 40)
        
    except Exception as e:
        logger.error(f"Failed to list tasks: {str(e)}")
        raise

def run_task(config: Config, module: str, task_name: str, parallel: bool = False, 
             output_dir: Optional[str] = None, parameters: Optional[dict] = None) -> int:
    """
    Execute a specific task by finding it in the database and running it
    
    Args:
        config: Config instance
        module: Module name containing the task
        task_name: Name of task to execute
        parallel: Whether to run in parallel mode
        output_dir: Optional directory for output files (defaults to Temporary_directory from config)
        parameters: Optional dict of parameters to override task config (format: {param_name: value})
        
    Returns:
        Exit code from task execution
        
    Raises:
        FileNotFoundError: If database file doesn't exist
        ValueError: If module/task not found
        RuntimeError: If execution fails
    """
    try:
        # Get database path from config
        try:
            db_dir = Path(config.get("Database_directory"))
            db_path = db_dir / "model_flow.db.json"
        except KeyError:
            logger.error("Missing 'Database_directory' in config")
            raise

        # Verify database exists
        if not db_path.exists():
            logger.error(f"Database file not found at {db_path}. Run 'build' command first.")
            raise FileNotFoundError(f"Database file not found: {db_path}")

        # Load task database
        try:
            with open(db_path, 'r', encoding='utf-8') as db_file:
                task_db = json.load(db_file)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in database file: {db_path}")
            raise

        # Find the requested task
        if module not in task_db:
            raise ValueError(f"Module '{module}' not found in database.")
            
        task_found = None
        for task in task_db[module]:
            if task.get("name") == task_name:
                task_found = task
                break
        
        if not task_found:
            raise ValueError(f"Task '{task_name}' not found in module '{module}'.")
        
        # Merge command line parameters with task config
        if parameters:
            if 'config' not in task_found:
                task_found['config'] = []
            for param_name, param_value in parameters.items():
                # Update if parameter exists, otherwise add new
                param_exists = False
                for param in task_found['config']:
                    if param['script_name'] == param_name:
                        param['script_value'] = param_value
                        param_exists = True
                        break
                if not param_exists:
                    task_found['config'].append({
                        'script_name': param_name,
                        'script_value': param_value
                    })
        
        logger.info(f"Found task: {module}/{task_name}")
        logger.debug(f"Task details: {json.dumps(task_found, indent=2)}")       
        
        # Create execution engine with Config instance
        engine = ExecutionEngine(config)

        # Determine output directory (command line arg > config > default)
        final_output_dir = output_dir or config.get("Temporary_directory")
        
        # Execute based on parallel flag
        if parallel:
            with ThreadPoolExecutor() as executor:
                future = executor.submit(engine.execute_task, module, task_name, final_output_dir)
                result = future.result()
        else:
            result = engine.execute_task(module, task_name, final_output_dir, task_metadata=task_found)
        
        logger.info(f"Task '{module}/{task_name}' completed with exit code: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to execute task '{module}/{task_name}': {str(e)}")
        raise RuntimeError(f"Task execution failed: {str(e)}") from e

def run_pipeline(config: str, module: str, pipeline: str) -> None:
    """
    Execute a pipeline of tasks
    
    Args:
        config: Path to config file
        module: Module name containing pipeline
        pipeline: Pipeline name to execute
        
    Raises:
        NotImplementedError: Currently not implemented
    """
    raise NotImplementedError("Pipeline execution not yet implemented")


def show_task(config_path: str, module: str, task_name: str) -> None:
    """
    Display detailed information about a specific task from the database
    
    Args:
        config_path: Path to the configuration file
        module: Module name containing the task
        task_name: Name of task to display
        
    Raises:
        FileNotFoundError: If config or database file doesn't exist
        ValueError: If module/task not found
    """
    try:
        # Load configuration
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
        
        # Locate database file
        db_path = Path(config["Database_directory"]) / "model_flow.db.json"
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found at {db_path}. Run 'build' command first.")
        
        # Load task database
        with open(db_path, 'r', encoding='utf-8') as db_file:
            task_db = json.load(db_file)
        
        # Find the requested task
        if module not in task_db:
            raise ValueError(f"Module '{module}' not found in database.")
            
        task_found = None
        for task in task_db[module]:
            if task.get("name") == task_name:
                task_found = task
                break
        
        if not task_found:
            raise ValueError(f"Task '{task_name}' not found in module '{module}'.")
        
        # Display task information
        print(f"\nTask Details: {module}/{task_name}")
        print("=" * 50)
        print(f"File: {task_found.get('file_path', 'Unknown')}")
        print(f"Type: {task_found.get('filetype', 'Unknown')}")
        
        if 'description' in task_found:
            print("\nDescription:")
            print(task_found['description'])
        
        if 'previous' in task_found and task_found['previous']:
            print(f"\nPrevious Task: {task_found['previous']}")
        
        if 'config' in task_found and task_found['config']:
            print("\nConfiguration Parameters:")
            for param in task_found['config']:
                print(f"  {param.get('script_name', 'Unknown')}:")
                print(f"    Type: {param.get('role', 'parameter')}")
                print(f"    Default Value: {param.get('script_value', 'Not set')}")
                if 'description' in param:
                    print(f"    Description: {param['description']}")
                print()
        
        print("=" * 50)
        
    except Exception as e:
        logger.error(f"Failed to show task '{module}/{task_name}': {str(e)}")
        raise


def init():
    """Initialize the configuration file for Model Flow."""
    print("Initializing Model Flow configuration...")

    # Create a new Config instance by asking the user for input
    config = Config.create_from_user_input()
    
    print(config)

    # Get the Database_directory from the user-provided configuration
    database_directory = config.get("Database_directory")
    print(f"Database directory: {database_directory}")

    # Define the path to save the configuration file
    config_path = Path(database_directory) / "model_flow.config.json"

    # Save the configuration to the specified path
    try:
        Config.save_to_file(config, config_path)
    except Exception as e:
        print(f"Error saving configuration to {config_path}: {e}")
        sys.exit(1)


def main():
    """Main entry point for the Model Flow CLI."""
    parser = argparse.ArgumentParser(
        description="Model Flow - Modular workflow management system for simulation models",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=False
    )

    # Add a custom help option
    parser.add_argument(
        '-h', '--help',
        action='store_true',
        help='Show this help message and exit'
    )

    subparsers = parser.add_subparsers(dest='command', required=False)

    # Add init command
    init_parser = subparsers.add_parser('init', help='Initialize the configuration file')

    # Build command
    build_parser = subparsers.add_parser('build', help='Build the task database')
    build_parser.add_argument(
        '--config',
        required=True,
        help='Configuration file path'
    )
    
    # List tasks command
    list_parser = subparsers.add_parser('list_tasks', help='List available tasks')
    list_parser.add_argument(
        '--config',
        required=True,
        help='Configuration file path'
    )
    list_parser.add_argument(
        '--module',
        required=False,
        help='Filter tasks by specific module'
    )
    
    # Run task command
    run_task_parser = subparsers.add_parser('run_task', help='Execute a single task')
    run_task_parser.add_argument(
        '--config',
        required=True,
        help='Configuration file path'
    )
    run_task_parser.add_argument(
        '--module',
        required=True,
        help='Module containing the task'
    )
    run_task_parser.add_argument(
        '--task',
        required=True,
        help='Task name to execute'
    )
    run_task_parser.add_argument(
        '--set',
        action='append',
        metavar='PARAM=VALUE',
        help='Set task parameters in PARAM=VALUE format',
        type=lambda x: x.split('=', 1)  # Split on first '=' only
    )
    run_task_parser.add_argument(
        '--range',
        action='append',
        nargs=4,
        metavar=('CONFIG_VAR', 'START', 'END', 'STEP'),
        help='Execute task with a range of values (creates parallel jobs)'
    )
    run_task_parser.add_argument(
        '--values',
        action='append',
        nargs='+',
        metavar=('VAR', 'VALUES'),
        help='Execute task with specific values (first value is config var, rest are values)'
    )
    run_task_parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run task in parallel mode'
    )
    run_task_parser.add_argument(
        '--output_dir',
        type=str,
        help='Directory where log/output files will be saved (defaults to Temporary_directory from config)'
    )

    
    # Run pipeline command
    run_pipeline_parser = subparsers.add_parser('run_pipeline', help='Execute a pipeline')
    run_pipeline_parser.add_argument(
        '--config',
        required=True,
        help='Configuration file path'
    )
    run_pipeline_parser.add_argument(
        '--module',
        required=True,
        help='Module containing the pipeline'
    )
    run_pipeline_parser.add_argument(
        '--pipeline',
        required=True,
        help='Pipeline name to execute'
    )
    
    # Add show_task command parser
    show_parser = subparsers.add_parser('show_task', help='Display detailed information about a specific task')
    show_parser.add_argument(
        '--config',
        required=True,
        help='Configuration file path'
    )
    show_parser.add_argument(
        '--module',
        required=True,
        help='Module containing the task'
    )
    show_parser.add_argument(
        '--task',
        required=True,
        help='Task name to display'
    )
    
    # Add run_gui command
    gui_parser = subparsers.add_parser('run_gui', help='Launch the Textual-based GUI')
    gui_parser.add_argument(
        '--config',
        required=False,
        help='Configuration file path (optional, defaults to config.json)'
    )
    
    args = parser.parse_args()

    # Show help if no arguments or --help flag
    if len(sys.argv) == 1 or args.help:
        print("\nModel Flow - Available Commands:")
        print("=================================")
        print("1. init - Initialize the configuration file")
        print("   Usage: python model_flow.py init")
        print("\n2. build - Build the task database")
        print("   Usage: python model_flow.py build --config=<config_file>")
        
        print("\n3. list_tasks - List available tasks")
        print("   Usage: python model_flow.py list_tasks --config=<config_file> [--module=<module_name>]")
        
        print("\n4. run_task - Execute a single task")
        print("   Usage: python model_flow.py run_task --config=<config_file> --module=<module> --task=<task> [--parallel]")
        
        print("\n5. run_pipeline - Execute a pipeline")
        print("   Usage: python model_flow.py run_pipeline --config=<config_file> --module=<module> --pipeline=<pipeline>")
        
        print("\n6. show_task - Display detailed task information")
        print("   Usage: python model_flow.py show_task --config=<config_file> --module=<module> --task=<task>")
        
        print("\n7. run_gui - Launch the Textual-based GUI")
        print("   Usage: python model_flow.py run_gui [--config=<config_file>]")
        
        print("\n8. help - Show this help message")
        print("   Usage: python model_flow.py --help")
        
        print("\nFor detailed help on each command, use: python model_flow.py <command> --help")
        sys.exit(0)
    
    try:
        if args.command == 'init':
            init()
        elif args.command == 'build':
            build(Config(args.config))
        elif args.command == 'run_task':
            # Convert --set parameters to dict
            params = dict(args.set) if args.set else None
            run_task(
                args.config,
                args.module,
                args.task,
                args.parallel,
                args.output_dir,
                parameters=params  # Pass the --set parameters here
            )
        elif args.command == 'run_pipeline':
            run_pipeline(args.config, args.module, args.pipeline)
        elif args.command == 'list_tasks':
            list_tasks(args.config, args.module)
        elif args.command == 'show_task':  # New command
            show_task(args.config, args.module, args.task)
        elif args.command == 'run_gui':  # New run_gui command
            # Launch the Textual GUI
            app = ModelFlowApp()
            app.run()
        else:
            parser.print_help()
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Command failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()