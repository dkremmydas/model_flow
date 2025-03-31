#!/usr/bin/env python3
"""
IFMCAP Flow - Main command-line interface for managing IFMCAP workflows
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from task import Task
from execution_engine import ExecutionEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def parse_modules(directory: str) -> Dict:
    """
    Recursively parse modules and tasks from the given directory.
    
    Args:
        directory: The root directory to parse
        
    Returns:
        Dictionary containing parsed modules and tasks
        
    Raises:
        FileNotFoundError: If directory doesn't exist
    """
    allowed_extensions = {".r", ".rmd", ".gms"}
    ignore_dirs = {".git", ".vscode", ".svn", "__pycache__", "venv"}
    modules = {}
    total_tasks = 0  # Counter for total tasks found

    try:
        root_path = Path(directory).resolve()
        if not root_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        logger.info(f"Starting module parsing in: {root_path}")
        
        for root, dirs, files in os.walk(root_path):
            # Filter ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in allowed_extensions:
                    file_path = Path(root) / file
                    
                    try:
                        task = Task(str(file_path))
                        if not task.name:
                            continue
                            
                        module_name = task.module or 'Uncategorized'
                        module_data = {
                            "file": file,
                            "file_path": str(file_path),
                            "filetype": file_ext,
                            "name": task.name,
                            "previous": task.previous,
                            "description": task.description.strip(),
                            "config": task.config,
                        }
                        
                        if module_name not in modules:
                            modules[module_name] = []
                        modules[module_name].append(module_data)
                        total_tasks += 1  # Increment task counter
                        
                    except Exception as e:
                        logger.warning(f"Error parsing {file_path}: {str(e)}")
                        continue

        # Enhanced logging with both module and task counts
        logger.info(f"Found {len(modules)} modules containing {total_tasks} total tasks")
        return modules

    except Exception as e:
        logger.error(f"Error during module parsing: {str(e)}")
        raise

def build(config_path: str) -> None:
    """
    Build the ifmcap_flow.json.db file by scanning Code_directory 
    and saving to Database_directory from config
    
    Args:
        config_path: Path to the configuration JSON file
        
    Raises:
        FileNotFoundError: If directories don't exist
        PermissionError: If write access is denied
    """
    try:
        # Load configuration
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
        
        code_dir = Path(config["Code_directory"])
        db_dir = Path(config["Database_directory"])
        
        if not code_dir.exists():
            raise FileNotFoundError(f"Code directory not found: {code_dir}")
        if not db_dir.exists():
            logger.info(f"Creating database directory: {db_dir}")
            db_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Scanning code directory: {code_dir}")
        modules = parse_modules(str(code_dir))
        
        output_file = db_dir / "ifmcap_flow.db.json"
        
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
    List all available tasks from the database
    
    Args:
        config_path: Path to the configuration file
        module_filter: Optional module name to filter tasks
        
    Raises:
        FileNotFoundError: If config or database file doesn't exist
        json.JSONDecodeError: If config or database file is malformed
        KeyError: If required config keys are missing
    """
    try:
        # Load configuration
        try:
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {config_path}")
            raise
        
        # Validate config structure
        try:
            db_dir = Path(config["Database_directory"])
            db_path = db_dir / "ifmcap_flow.db.json"
        except KeyError:
            logger.error("Missing 'Database_directory' in config file")
            raise
        
        # Check database existence
        if not db_path.exists():
            logger.error(f"Database file not found at {db_path}. Run 'build' command first.")
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        # Load database
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                modules = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in database file: {db_path}")
            raise
        
        # Apply module filter if specified
        if module_filter:
            modules = {k: v for k, v in modules.items() if k == module_filter}
            if not modules:
                logger.warning(f"No tasks found in module: {module_filter}")
                return
        
        # Display task listing
        logger.info("Available tasks:")
        for module_name, tasks in modules.items():
            logger.info(f"\nModule: {module_name}")
            for task in tasks:
                task_name = task.get('name', 'Unnamed Task')
                task_desc = task.get('description', 'No description available')
                logger.info(f"  • {task_name}")
                logger.info(f"    Description: {task_desc[:80]}{'...' if len(task_desc) > 80 else ''}")
                logger.info(f"    File: {task.get('file_path', 'Unknown')}")
        
        # Summary count
        total_modules = len(modules)
        total_tasks = sum(len(tasks) for tasks in modules.values())
        logger.info(f"\nFound {total_tasks} tasks across {total_modules} modules")
        
    except Exception as e:
        logger.error(f"Failed to list tasks: {str(e)}")
        raise

def run_task(config_path: str, module: str, task_name: str, parallel: bool = False) -> int:
    """
    Execute a specific task by finding it in the database and running it
    
    Args:
        config_path: Path to configuration file
        module: Module name containing the task
        task_name: Name of task to execute
        parallel: Whether to run in parallel mode
        
    Returns:
        Exit code from task execution
        
    Raises:
        FileNotFoundError: If config or database file doesn't exist
        ValueError: If module/task not found
        RuntimeError: If execution fails
    """
    try:
        # Load configuration
        try:
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {config_path}")
            raise

        # Get database path from config
        try:
            db_dir = Path(config["Database_directory"])
            db_path = db_dir / "ifmcap_flow.db.json"
        except KeyError:
            logger.error("Missing 'Database_directory' in config file")
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
        
        logger.info(f"Found task: {module}/{task_name}")
        logger.debug(f"Task details: {json.dumps(task_found, indent=2)}")
        
        # Create execution engine with full config
        engine = ExecutionEngine(config_path)
        
        # Execute based on parallel flag
        if parallel:
            with ThreadPoolExecutor() as executor:
                future = executor.submit(engine.execute_task, module, task_name)
                result = future.result()
        else:
            result = engine.execute_task(module, task_name)
        
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


def main():
    """Main entry point for the IFMCAP Flow CLI"""
    parser = argparse.ArgumentParser(
        description="IFMCAP Flow - Modular workflow management system",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
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
        '--parallel',
        action='store_true',
        help='Run task in parallel mode'
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
    
    args = parser.parse_args()
    
    try:
        if args.command == 'build':
            build(args.config)  # Changed from args.dir to args.config
        elif args.command == 'run_task':
            run_task(args.config, args.module, args.task, args.parallel)
        elif args.command == 'run_pipeline':
            run_pipeline(args.config, args.module, args.pipeline)
        elif args.command == 'list_tasks':
            list_tasks(args.config, args.module)  # Changed from args.dir to args.config
            
    except Exception as e:
        logger.error(f"Command failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()