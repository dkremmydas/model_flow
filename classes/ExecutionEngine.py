import os
import re
import json
import copy
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Optional
from classes.Database import Database
from classes.Lists import Lists
from classes.Parser import Parser
from classes.Config import Config
from classes.Task import Task


@dataclass
class ExecutionResult:
    """Result of a task execution with captured output (capture_output=True)."""
    returncode: int
    stdout: Optional[str]
    stderr: Optional[str]


class ExecutionEngine:
    """
    Execution engine to run tasks based on their metadata from model_flow.db.json.
    Uses a configuration file to locate executables and set default parameters.
    """

    def __init__(self, config: Config):
        """
        Initialize the execution engine with the provided configuration.

        Parameters:
            config (dict): A dictionary containing configuration details such as paths to executables,
                   directories, and other necessary settings.

        Raises:
            ValueError: If the configuration is missing required fields or the database directory is invalid.
            Exception: If any other error occurs during initialization.
        """
        self.logger = logging.getLogger(__name__)
        
        try:
            # Use provided configuration
            self.config = config
            self.database = Database(config)
            self.lists = Lists(config)

            self.logger.info("Initialized ExecutionEngine with provided database instance.")

        except Exception as e:
            self.logger.error(f"Failed to initialize ExecutionEngine: {str(e)}")
            raise

    
    def execute_task(self, module: str, task_name: str, output_dir: Optional[str] = None,
                      overrides: Optional[Dict[str, str]] = None, capture_output: bool = False,
                      on_output: Optional[Callable[[str], None]] = None,
                      on_process_start: Optional[Callable[[subprocess.Popen], None]] = None):
        """
        Execute the given task based on its metadata.

        Parameters:
            module (str): The module name.
            task_name (str): The task name.
            output_dir (str, optional): Directory for output files. Defaults to config's Temporary_directory.
            overrides (dict, optional): Mapping of script_name -> value to override the task's
                default config values for this run only (does not mutate the underlying database).
            capture_output (bool): If True, capture stdout/stderr instead of inheriting the
                parent process's stdio and return an ExecutionResult. Needed by front ends
                (like the Textual GUI) whose own terminal rendering would otherwise be corrupted
                by an inherited child process stdio. Defaults to False (CLI behavior: live-streamed
                output to the console, returns an int return code) so existing CLI behavior is unchanged.
            on_output (callable, optional): Only used when capture_output=True. If given, output is
                streamed to it one line at a time as the process produces it (instead of only being
                available once the process exits) via subprocess.Popen. Runs on whatever thread calls
                execute_task -- callers updating a UI from it must marshal back to the UI thread
                themselves (e.g. Textual's App.call_from_thread).
            on_process_start (callable, optional): Only used together with on_output (the streaming
                path). Called once with the subprocess.Popen instance as soon as it's created, giving
                the caller a handle to (e.g.) terminate() the process from elsewhere -- terminating a
                Popen from a different thread than the one reading its output is safe.

        Returns:
            int: The return code of the executed process (capture_output=False).
            ExecutionResult: The captured result (capture_output=True).

        Raises:
            ValueError: If required task metadata is missing
            RuntimeError: If execution fails
        """
        try:
            task = self.database.get_task(module, task_name)

            self.logger.info(f"Executing task: {module}/{task_name}")

            if overrides:
                task = copy.deepcopy(task)
                for param in task.get("config", []):
                    if param.get("script_name") in overrides:
                        param["script_value"] = overrides[param["script_name"]]

            filetype = task['filetype'].lower()

            # Determine output directory (parameter > config > None)
            final_output_dir = output_dir or self.config.get("Temporary_directory")

            # Execute based on file type
            if filetype == ".r":
                return self._execute_r_task(task, capture_output=capture_output, on_output=on_output,
                                             on_process_start=on_process_start)
            elif filetype == ".rmd":
                return self._execute_rmd_task(task, final_output_dir, capture_output=capture_output,
                                               on_output=on_output, on_process_start=on_process_start)
            elif filetype == ".gms":
                return self._execute_gams_task(task, capture_output=capture_output, on_output=on_output,
                                                on_process_start=on_process_start)
            elif filetype == ".bat":
                return self._execute_bat_task(task, capture_output=capture_output, on_output=on_output,
                                               on_process_start=on_process_start)
            else:
                raise ValueError(f"Unsupported file type: {filetype}")

        except Exception as e:
            self.logger.error(f"Task execution failed: {str(e)}")
            raise RuntimeError(f"Failed to execute task {module}/{task_name}: {str(e)}") from e

    def execute_pipeline(self, module: str, pipeline_name: str, output_dir: Optional[str] = None,
                          capture_output: bool = False,
                          on_output: Optional[Callable[[str], None]] = None,
                          on_process_start: Optional[Callable[[subprocess.Popen], None]] = None,
                          on_step_start: Optional[Callable[[int, int, str, int, int, Dict[str, str]], None]] = None,
                          extra_overrides: Optional[Dict[str, Dict[str, str]]] = None) -> int:
        """
        Execute every task declared in a pipeline (Database.get_pipeline), in
        order, stopping at the first failure. Each pipeline task entry is
        normalized (by Parser.parse_pipelines) to {"task", "overrides", "loop"}:

        - No "loop": the task runs once, with "overrides" applied on top of its
          own config defaults (same override mechanism as execute_task).

        `extra_overrides` (optional {task_name: {script_name: value}}, matching
        the GUI's ShowTask.get_pipeline_overrides() shape) layers additional
        per-run overrides on top of each task's declared "overrides" -- used by
        the GUI to let a user tweak a pipeline task's parameters for one run
        without editing the JSON. For a looped task, these still lose to that
        iteration's own loop-driven value on a key collision (the loop is the
        whole point of that step); they're just an extra base layer, same
        precedence as the JSON-declared "overrides".
        - "loop": Parser.expand_loop resolves loop["parameters"] (a
          {script_name: list_name} mapping) against self.lists.get_elements into
          an ordered list of per-iteration override dicts, merged onto the
          task's own "overrides" (pre-validated to be disjoint keys). Each
          iteration runs against its own output subdirectory
          (output_dir/task_name/k=v__...) to avoid the .rmd output-filename
          collision that would occur if the same task ran repeatedly against one
          shared output_dir within the same clock minute.
            - mode "sequential" (default): iterations run in order, stopping the
              whole pipeline at the first non-zero return code (true
              stop-on-first-failure, matching a non-looped task's behavior).
            - mode "parallel": all iterations are submitted to a
              ThreadPoolExecutor (max_workers = loop["max_workers"] or
              min(iteration_count, os.cpu_count() or 4)) and all are allowed to
              finish before the step is judged -- a sibling iteration's failure
              does not cancel already-launched iterations. If any iteration
              failed, the step (and pipeline) is failed, returning the first
              such code in submission order for a deterministic result. This is
              a deliberate tradeoff (simpler than mid-flight cancellation), not
              an oversight.

        `on_step_start(step_index, total_steps, task_name, iteration_index,
        total_iterations, iteration_values)` is called once before each
        individual execution (once for a non-looped task, once per iteration for
        a looped one) so a caller (e.g. the GUI) can render live progress.
        `capture_output`/`on_output`/`on_process_start` are forwarded to every
        underlying execute_task call exactly as they are for a single task; note
        that a parallel loop step calls `on_output`/`on_process_start` from
        multiple worker threads concurrently -- the same thread-safety
        responsibility documented on execute_task applies per-call, just from
        more than one thread at a time now.

        Returns:
            int: 0 if every task/iteration succeeded, otherwise the first
            non-zero return code encountered (mirrors execute_task's plain-int
            contract regardless of capture_output, since a pipeline's output is
            already delivered live via on_output rather than as one aggregated
            result).

        Raises:
            ValueError: If the module/pipeline isn't found.
        """
        pipeline = self.database.get_pipeline(module, pipeline_name)
        if pipeline is None:
            raise ValueError(
                f"Pipeline '{pipeline_name}' not found in module '{module}'. "
                f"Run 'build' first if this pipeline was just added."
            )

        tasks = pipeline.get("tasks", [])
        final_output_dir = output_dir or self.config.get("Temporary_directory")
        total_steps = len(tasks)
        extra_overrides = extra_overrides or {}
        self.logger.info(f"Starting pipeline '{module}/{pipeline_name}' ({total_steps} steps)")

        for step_index, raw_entry in enumerate(tasks, start=1):
            # Defensive: a model_flow.pipelines.json built by a pre-loop-feature
            # version of model_flow still has plain task-name-string entries --
            # treat those the same as a normalized no-overrides/no-loop entry
            # instead of crashing, so a stale (not yet rebuilt) db file degrades
            # gracefully rather than with a confusing TypeError.
            entry = raw_entry if isinstance(raw_entry, dict) else {"task": raw_entry, "overrides": {}, "loop": None}
            task_name = entry["task"]
            base_overrides = {**(entry.get("overrides") or {}), **extra_overrides.get(task_name, {})}
            loop = entry.get("loop")

            if loop is None:
                if on_step_start:
                    on_step_start(step_index, total_steps, task_name, 1, 1, {})
                result = self.execute_task(
                    module, task_name, final_output_dir, overrides=base_overrides or None,
                    capture_output=capture_output, on_output=on_output, on_process_start=on_process_start,
                )
                returncode = result.returncode if isinstance(result, ExecutionResult) else result
                if returncode != 0:
                    self.logger.error(
                        f"Pipeline '{module}/{pipeline_name}' stopped: task '{task_name}' "
                        f"(step {step_index}/{total_steps}) exited {returncode}."
                    )
                    return returncode
                continue

            iterations = Parser.expand_loop(loop, self.lists.get_elements)
            total_iterations = len(iterations)

            if loop.get("mode") == "parallel":
                max_workers = loop.get("max_workers") or min(total_iterations, os.cpu_count() or 4)
                first_failure = None
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    for iter_index, iteration_values in enumerate(iterations, start=1):
                        if on_step_start:
                            on_step_start(step_index, total_steps, task_name, iter_index,
                                          total_iterations, iteration_values)
                        merged_overrides = {**base_overrides, **iteration_values}
                        iter_output_dir = self._pipeline_iteration_output_dir(
                            final_output_dir, task_name, iteration_values
                        )
                        futures.append(executor.submit(
                            self.execute_task, module, task_name, str(iter_output_dir),
                            overrides=merged_overrides, capture_output=capture_output,
                            on_output=on_output, on_process_start=on_process_start,
                        ))
                    for future in futures:
                        result = future.result()
                        returncode = result.returncode if isinstance(result, ExecutionResult) else result
                        if returncode != 0 and first_failure is None:
                            first_failure = returncode

                if first_failure is not None:
                    self.logger.error(
                        f"Pipeline '{module}/{pipeline_name}' stopped: task '{task_name}' "
                        f"(step {step_index}/{total_steps}, parallel loop) had a failing iteration "
                        f"(exit {first_failure})."
                    )
                    return first_failure
                continue

            # mode "sequential" (default)
            for iter_index, iteration_values in enumerate(iterations, start=1):
                if on_step_start:
                    on_step_start(step_index, total_steps, task_name, iter_index, total_iterations, iteration_values)
                merged_overrides = {**base_overrides, **iteration_values}
                iter_output_dir = self._pipeline_iteration_output_dir(final_output_dir, task_name, iteration_values)
                result = self.execute_task(
                    module, task_name, str(iter_output_dir), overrides=merged_overrides,
                    capture_output=capture_output, on_output=on_output, on_process_start=on_process_start,
                )
                returncode = result.returncode if isinstance(result, ExecutionResult) else result
                if returncode != 0:
                    self.logger.error(
                        f"Pipeline '{module}/{pipeline_name}' stopped: task '{task_name}' "
                        f"(step {step_index}/{total_steps}, iteration {iter_index}/{total_iterations}) "
                        f"exited {returncode}."
                    )
                    return returncode

        self.logger.info(f"Pipeline '{module}/{pipeline_name}' completed successfully ({total_steps} steps).")
        return 0

    @staticmethod
    def _sanitize_path_component(value) -> str:
        """Make a loop iteration value safe to use as a single filesystem path component."""
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', str(value)).strip()
        return sanitized or "_"

    def _pipeline_iteration_output_dir(self, base_output_dir, task_name: str,
                                        iteration_values: Dict[str, str]) -> Path:
        """
        Build (and create) a per-iteration output subdirectory so repeated runs of
        the same looped task don't collide on output filenames (notably .rmd's
        minute-granularity timestamp). Sorted so the folder name is stable
        regardless of dict ordering.
        """
        label = "__".join(
            f"{key}={self._sanitize_path_component(value)}" for key, value in sorted(iteration_values.items())
        )
        iter_dir = Path(base_output_dir) / task_name / label
        iter_dir.mkdir(parents=True, exist_ok=True)
        return iter_dir

    def _config_path(self, key: str) -> Path:
        """
        Fetch a config value expected to be a filesystem path, raising a clear,
        actionable error instead of a cryptic TypeError from Path(None) if the
        key is missing or empty (e.g. an optional key like Pandoc_dir that
        Config does not enforce as required).
        """
        value = self.config.get(key)
        if not value:
            raise ValueError(f"'{key}' is not set in the configuration file.")
        return Path(value)

    def _run(self, command, capture_output: bool, on_output: Optional[Callable[[str], None]] = None,
             on_process_start: Optional[Callable[[subprocess.Popen], None]] = None,
             env: Optional[Dict[str, str]] = None):
        """
        Run a command, either inheriting the parent process's stdio (CLI default,
        live-streamed output, returns an int) or capturing stdout/stderr (GUI use,
        returns an ExecutionResult) so a Textual TUI's own rendering isn't corrupted
        by an inherited child process stdio. When capturing with an `on_output`
        callback, output is streamed line-by-line as the process produces it,
        via `_run_streaming`, instead of only becoming available once it exits.

        `env`, if given, replaces the child process's environment entirely (not
        merged) -- callers that want to add to rather than replace the parent
        environment must pass a copy of os.environ with their own keys added.
        """
        if capture_output and on_output:
            return self._run_streaming(command, on_output, on_process_start, env)
        if capture_output:
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            return ExecutionResult(result.returncode, result.stdout, result.stderr)
        return subprocess.call(command, env=env)

    def _run_streaming(self, command, on_output: Callable[[str], None],
                        on_process_start: Optional[Callable[[subprocess.Popen], None]] = None,
                        env: Optional[Dict[str, str]] = None) -> ExecutionResult:
        """
        Run a command via Popen, calling `on_output(line)` for each line of output
        as it's produced (stdout and stderr merged, in the order they're written)
        rather than waiting for the process to exit. Note this is only as "live"
        as the child process's own output buffering allows -- e.g. R/Rscript
        block-buffers stdout when it isn't a terminal, so output from long
        stretches of a script with no explicit flush may still arrive in bursts.

        If `on_process_start` is given, it's called with the Popen instance right
        after creation, so a caller elsewhere (e.g. a "kill" keybinding) can hold
        onto it and call terminate() -- if the process is terminated mid-run, the
        stdout pipe closes, the read loop below ends, and this still returns a
        normal ExecutionResult (with whatever returncode the OS reports for a
        terminated process) rather than raising.
        """
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        if on_process_start:
            on_process_start(process)
        lines = []
        for line in process.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            on_output(line)
        process.wait()
        return ExecutionResult(process.returncode, "\n".join(lines), "")

    def _execute_r_task(self, task: Task, capture_output: bool = False,
                         on_output: Optional[Callable[[str], None]] = None,
                         on_process_start: Optional[Callable[[subprocess.Popen], None]] = None):
        """Execute an R script task."""

        try:
            rscript_path = self._config_path("Rscript_exe")
            task_file = Path(task["file_path"])

            # Convert Windows paths to R-friendly format
            def r_path(path):
                return str(path).replace('\\', '/')

            args_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    # Escape backslashes in parameter values too
                    value = str(param['script_value']).replace('\\', '/')
                    args_list.append(f"{param['script_name']}={value}")

            command = [str(rscript_path), r_path(task_file)] + args_list
            self.logger.info(f"Executing R script: {' '.join(command)}")

            return self._run(command, capture_output, on_output, on_process_start)

        except Exception as e:
            self.logger.error(f"R task execution failed: {str(e)}")
            raise

    def _execute_rmd_task(self, task: Task, output_dir=None, capture_output: bool = False,
                           on_output: Optional[Callable[[str], None]] = None,
                           on_process_start: Optional[Callable[[subprocess.Popen], None]] = None):
        """Execute an R Markdown task with output directory support and strict type handling."""
        try:
            # Get required paths from config
            rscript_path = self._config_path("Rscript_exe")
            pandoc_dir = self._config_path("Pandoc_dir")
            gams_dir = self._config_path("GAMS_exe").parent
            task_file = Path(task["file_path"])

            # Set output directory (default to config's Temporary_directory or current dir)
            output_dir = Path(output_dir or self.config.get("Temporary_directory", "."))
            if not output_dir.exists():
                raise FileNotFoundError(f"Output directory does not exist: {output_dir}")
            if not output_dir.is_dir():
                raise NotADirectoryError(f"Path is not a directory: {output_dir}")

            # Generate output filename
            task_name = task.get('name', 'output').replace(' ', '_')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            output_file = output_dir / f"{task_name}_{timestamp}.html"

            def r_path(path):
                """Convert Windows paths to R-friendly format"""
                return str(path).replace('\\', '/')
            
            def format_param_value(param):
                """Format parameter value according to its type"""
                value = param['script_value']
                
                # Handle numeric parameters
                if param.get('type') == 'number':
                    try:
                        if isinstance(value, (int, float)):
                            return str(value)
                        # Convert string to number if needed
                        return str(float(value) if '.' in str(value) else int(value))
                    except (ValueError, TypeError):
                        self.logger.warning(
                            f"Couldn't convert {param['script_name']} value '{value}' to number"
                        )
                
                # Default string handling
                return f"'{str(value).replace('\\', '/')}'"
            
            # Set environment variables
            env_script = (
                f"Sys.setenv(RSTUDIO_PANDOC='{r_path(pandoc_dir)}'); "
                f"Sys.setenv(PATH=paste('{r_path(gams_dir)}', Sys.getenv('PATH'), sep=';')); "
            )
            
            # Prepare parameters with type handling
            params_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    params_list.append(f"{param['script_name']}={format_param_value(param)}")

            # Build render command with output control
            render_script = (
                f"{env_script}"
                f"rmarkdown::render("
                f"input = '{r_path(task_file)}', "
                f"output_file = '{r_path(output_file)}', "
                f"params = list({', '.join(params_list)}), "
                f"intermediates_dir = '{r_path(output_dir)}', "
                f"knit_root_dir = '{r_path(output_dir)}'"
                f")"
            )

            command = [str(rscript_path), "-e", render_script]
            self.logger.info(f"Running {command}")
            self.logger.info(f"Rendering to {output_file}")

            result = self._run(command, capture_output, on_output, on_process_start)
            returncode = result.returncode if isinstance(result, ExecutionResult) else result
            if returncode == 0:
                self.logger.info(f"Successfully created: {output_file}")
            return result

        except Exception as e:
            self.logger.error(f"R Markdown execution failed: {str(e)}")
            raise

    def _execute_gams_task(self, task: Task, capture_output: bool = False,
                            on_output: Optional[Callable[[str], None]] = None,
                            on_process_start: Optional[Callable[[subprocess.Popen], None]] = None):
        """Execute a GAMS task."""
        try:
            gams_exe = self._config_path("GAMS_exe")
            task_file = Path(task["file_path"])

            args_list = []
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    args_list.append(f"{param['script_name']}={param['script_value']}")

            command = [str(gams_exe), str(task_file)] + args_list
            self.logger.info(f"Executing GAMS script: {' '.join(command)}")

            return self._run(command, capture_output, on_output, on_process_start)

        except Exception as e:
            self.logger.error(f"GAMS task execution failed: {str(e)}")
            raise

    def _execute_bat_task(self, task: Task, capture_output: bool = False,
                           on_output: Optional[Callable[[str], None]] = None,
                           on_process_start: Optional[Callable[[subprocess.Popen], None]] = None):
        """Execute a Windows batch (.bat) task."""
        try:
            task_file = Path(task["file_path"])

            # Config values are passed as environment variables (%NAME%), not
            # positional command-line arguments. cmd.exe's own argument tokenizer
            # splits on "=" (not just whitespace) when populating %1/%2/%*, so a
            # "NAME=value" token never survives intact as a single argument -- and
            # getting it through as one token via quoting runs straight into a
            # well-known "cmd /c" quoting trap (mismatched quote-stripping when the
            # command after /c contains multiple quoted segments). Environment
            # variables sidestep all of that and are the idiomatic way batch scripts
            # receive external parameters anyway.
            env = os.environ.copy()
            for param in task.get("config", []):
                if all(k in param for k in ['script_name', 'script_value']):
                    env[param['script_name']] = str(param['script_value'])

            # Invoke via "cmd /c" explicitly rather than passing the .bat path directly --
            # a .bat file isn't a PE executable, so relying on it "just working" without
            # shell=True is version/behavior-dependent. This is also cheaper than shell=True:
            # no shell-quoting/injection concern since the command list is built ourselves.
            command = ["cmd", "/c", str(task_file)]
            self.logger.info(f"Executing batch script: {' '.join(command)} "
                              f"(config passed via env: {[p.get('script_name') for p in task.get('config', [])]})")

            return self._run(command, capture_output, on_output, on_process_start, env)

        except Exception as e:
            self.logger.error(f"Batch task execution failed: {str(e)}")
            raise