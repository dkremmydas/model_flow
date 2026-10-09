"""Tests for parallel groups in pipelines ({"parallel": [step, ...], "max_workers"?}):
parsing/validation in Parser, and scheduling/failure handling in
ExecutionEngine.execute_pipeline. execute_task is faked throughout, same as
test_execution_engine.py's pipeline tests -- no real subprocesses."""

import json
import threading
import time
from pathlib import Path

import pytest

from classes import ExecutionEngine as execution_engine_module
from classes.Config import Config
from classes.ExecutionEngine import ExecutionEngine
from classes.Parser import Parser


# ---- Parser ----------------------------------------------------------------

def write(folder, filename, content):
    path = folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_task(folder, name, module="test_module"):
    content = (
        f'#@MODELFLOW_task name="{name}" module="{module}"\n'
        '#@MODELFLOW_config name="ext_par" type="number" role="parameter"\n'
        "ext_par = 5\n"
    )
    write(folder, "script_" + name + ".R", content=content)


def parse(tmp_path, pipelines, task_names=("1_task", "2_task", "3_task", "4_task"), lists=None):
    for name in task_names:
        write_task(tmp_path, name)
    write(tmp_path, "model_flow.pipelines.json",
          json.dumps({"module": "test_module", "pipelines": pipelines}))
    modules = Parser.parse_modules(str(tmp_path))
    return Parser.parse_pipelines(str(tmp_path), modules, lists)


def plain(task_name, overrides=None):
    return {"task": task_name, "overrides": overrides or {}, "loop": None}


def test_parse_pipelines_normalizes_parallel_group(tmp_path):
    pipelines = parse(tmp_path, [
        {"name": "run_all", "tasks": [
            "1_task",
            {"parallel": ["2_task", {"task": "3_task", "overrides": {"ext_par": "7"}}], "max_workers": 2},
            "4_task",
        ]},
    ])

    assert pipelines["test_module"][0]["tasks"] == [
        plain("1_task"),
        {"parallel": [plain("2_task"), plain("3_task", {"ext_par": "7"})], "max_workers": 2},
        plain("4_task"),
    ]


def test_parse_pipelines_parallel_group_max_workers_defaults_to_none(tmp_path):
    pipelines = parse(tmp_path, [{"name": "run_all", "tasks": [{"parallel": ["1_task", "2_task"]}]}])

    assert pipelines["test_module"][0]["tasks"] == [
        {"parallel": [plain("1_task"), plain("2_task")], "max_workers": None},
    ]


def test_parse_pipelines_accepts_looped_task_inside_parallel_group(tmp_path):
    lists = {"nuts2": {"name": "nuts2", "elements": ["AT11", "AT12"]}}
    pipelines = parse(tmp_path, [
        {"name": "run_all", "tasks": [
            {"parallel": ["1_task", {"task": "2_task", "loop": {"parameters": {"ext_par": "nuts2"}}}]},
        ]},
    ], lists=lists)

    group = pipelines["test_module"][0]["tasks"][0]
    assert group["parallel"][1]["loop"]["parameters"] == {"ext_par": "nuts2"}


@pytest.mark.parametrize("bad_step", [
    {"parallel": []},                                           # empty group
    {"parallel": "1_task"},                                     # not a list
    {"parallel": ["1_task", {"parallel": ["2_task"]}]},         # nested group
    {"parallel": ["1_task", "1_task"]},                         # same task twice
    {"parallel": ["1_task", "does_not_exist"]},                 # unknown task
    {"parallel": [{"task": "1_task", "overrides": {"nope": "1"}}]},  # unknown override
    {"parallel": ["1_task", "2_task"], "max_workers": 0},       # bad max_workers
    {"parallel": ["1_task", "2_task"], "max_workers": "2"},
    {"parallel": ["1_task", "2_task"], "max_workers": True},
])
def test_parse_pipelines_skips_pipeline_with_invalid_parallel_group(tmp_path, bad_step):
    pipelines = parse(tmp_path, [
        {"name": "bad", "tasks": ["1_task", bad_step]},
        {"name": "good", "tasks": ["1_task"]},
    ])

    assert [p["name"] for p in pipelines["test_module"]] == ["good"]


def test_iter_pipeline_entries_flattens_groups_with_their_step_number():
    tasks = [
        "1_task",  # bare string from a stale pre-loop db file
        {"parallel": [plain("2_task"), plain("3_task")], "max_workers": None},
        plain("4_task"),
    ]

    flattened = [(entry["task"], group) for entry, group in Parser.iter_pipeline_entries(tasks)]

    assert flattened == [("1_task", None), ("2_task", 2), ("3_task", 2), ("4_task", None)]
    first_entry, _ = next(Parser.iter_pipeline_entries(tasks))
    assert first_entry == plain("1_task")


# ---- ExecutionEngine -------------------------------------------------------

def make_engine(tmp_path, **extra_config):
    (tmp_path / "model_flow.db.json").write_text("{}", encoding="utf-8")
    config_data = {
        "Code_directory": str(tmp_path),
        "Database_directory": str(tmp_path),
        "Temporary_directory": str(tmp_path),
        "Rscript_exe": "C:/R/Rscript.exe",
        "GAMS_exe": "C:/GAMS/gams.exe",
        **extra_config,
    }
    return ExecutionEngine(Config(json.dumps(config_data)))


@pytest.fixture
def engine(tmp_path):
    return make_engine(tmp_path)


def set_pipeline(engine, tasks, module="test_module", name="run_all"):
    engine.database.pipelines_data = {module: [{"name": name, "description": "", "tasks": tasks}]}


def group(*members, max_workers=None):
    return {"parallel": list(members), "max_workers": max_workers}


class FakeTasks:
    """Fake ExecutionEngine.execute_task that records start/end events and how
    many calls overlap. `returncodes` maps task name -> exit code (default 0);
    `before_return(task_name)` runs while the task is "running"."""

    def __init__(self, returncodes=None, before_return=None, duration=0.0):
        self.returncodes = returncodes or {}
        self.before_return = before_return
        self.duration = duration
        self.events = []
        self.calls = []
        self.running = 0
        self.peak = 0
        self.lock = threading.Lock()

    def __call__(self, engine_self, module, task_name, output_dir=None, overrides=None, **kwargs):
        with self.lock:
            self.calls.append((task_name, output_dir, overrides))
            self.events.append(("start", task_name))
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            if self.before_return:
                self.before_return(task_name)
            if self.duration:
                time.sleep(self.duration)
            return self.returncodes.get(task_name, 0)
        finally:
            with self.lock:
                self.running -= 1
                self.events.append(("end", task_name))


@pytest.fixture
def install(monkeypatch):
    def _install(fake):
        # A plain function (not the FakeTasks object itself), so it's bound as
        # a method and receives the engine as `self`.
        def execute_task(self, *args, **kwargs):
            return fake(self, *args, **kwargs)
        monkeypatch.setattr(ExecutionEngine, "execute_task", execute_task)
        return fake
    return _install


def test_parallel_group_members_actually_run_concurrently(engine, install):
    # Each member waits at a 3-party barrier: if they ran one at a time, the
    # first would wait alone until the timeout and raise BrokenBarrierError.
    barrier = threading.Barrier(3, timeout=5)
    fake = install(FakeTasks(before_return=lambda name: barrier.wait()))
    set_pipeline(engine, [group(plain("a"), plain("b"), plain("c"))])

    assert engine.execute_pipeline("test_module", "run_all") == 0
    assert sorted(c[0] for c in fake.calls) == ["a", "b", "c"]
    assert fake.peak == 3


def test_steps_around_a_parallel_group_still_run_in_order(engine, install):
    fake = install(FakeTasks(duration=0.02))
    set_pipeline(engine, [plain("first"), group(plain("a"), plain("b")), plain("last")])

    assert engine.execute_pipeline("test_module", "run_all") == 0

    position = {event: i for i, event in enumerate(fake.events)}
    # "first" finished before any group member started ...
    assert position[("end", "first")] < position[("start", "a")]
    assert position[("end", "first")] < position[("start", "b")]
    # ... and "last" started only after every group member finished.
    assert position[("end", "a")] < position[("start", "last")]
    assert position[("end", "b")] < position[("start", "last")]


def test_failing_member_lets_siblings_finish_then_stops_pipeline(engine, install):
    fake = install(FakeTasks(returncodes={"b": 3, "c": 5}, duration=0.02))
    set_pipeline(engine, [group(plain("a"), plain("b"), plain("c")), plain("after")])

    result = engine.execute_pipeline("test_module", "run_all")

    # First failure in *declared* order, regardless of which finished first.
    assert result == 3
    assert sorted(c[0] for c in fake.calls) == ["a", "b", "c"]  # all members ran
    assert "after" not in [c[0] for c in fake.calls]           # next step didn't


def test_group_max_workers_limits_concurrency(engine, install):
    fake = install(FakeTasks(duration=0.05))
    set_pipeline(engine, [group(plain("a"), plain("b"), plain("c"), plain("d"), max_workers=1)])

    assert engine.execute_pipeline("test_module", "run_all") == 0
    assert len(fake.calls) == 4
    assert fake.peak == 1


def test_config_max_workers_share_applies_to_group_without_its_own(tmp_path, install, monkeypatch):
    monkeypatch.setattr(execution_engine_module.os, "cpu_count", lambda: 4)
    engine = make_engine(tmp_path, Max_workers=0.5)  # half of 4 cores -> 2 workers
    # Two-party barrier: proves at least 2 run at once (else it times out).
    barrier = threading.Barrier(2, timeout=5)
    fake = install(FakeTasks(before_return=lambda name: barrier.wait(), duration=0.02))
    set_pipeline(engine, [group(plain("a"), plain("b"), plain("c"), plain("d"))])

    assert engine.execute_pipeline("test_module", "run_all") == 0
    assert fake.peak == 2


def test_group_member_overrides_and_extra_overrides_are_applied(engine, install):
    fake = install(FakeTasks())
    set_pipeline(engine, [group(plain("a", {"x": "1"}), plain("b"))])

    engine.execute_pipeline("test_module", "run_all", extra_overrides={"b": {"y": "2"}})

    overrides = {name: ov for name, _out, ov in fake.calls}
    assert overrides == {"a": {"x": "1"}, "b": {"y": "2"}}


def test_looped_task_inside_group_runs_every_iteration(engine, install):
    fake = install(FakeTasks())
    engine.lists.lists_data = {"nuts2": {"name": "nuts2", "elements": ["AT11", "AT12"]}}
    looped = {"task": "b", "overrides": {},
              "loop": {"parameters": {"nuts_code": "nuts2"}, "combine": None, "mode": "parallel", "max_workers": None}}
    set_pipeline(engine, [group(plain("a"), looped)])

    assert engine.execute_pipeline("test_module", "run_all") == 0

    b_calls = [c for c in fake.calls if c[0] == "b"]
    assert sorted(c[2]["nuts_code"] for c in b_calls) == ["AT11", "AT12"]
    # Each iteration still gets its own output folder.
    assert len({c[1] for c in b_calls}) == 2
    assert all(Path(c[1]).is_dir() for c in b_calls)


def test_group_members_report_the_groups_step_index(engine, install):
    install(FakeTasks())
    set_pipeline(engine, [plain("first"), group(plain("a"), plain("b"))])
    steps = []
    lock = threading.Lock()

    def on_step_start(step_index, total_steps, task_name, iteration_index, total_iterations, values):
        with lock:
            steps.append((step_index, total_steps, task_name))

    engine.execute_pipeline("test_module", "run_all", on_step_start=on_step_start)

    assert sorted(steps) == [(1, 2, "first"), (2, 2, "a"), (2, 2, "b")]


def test_stale_bare_string_steps_still_run_alongside_groups(engine, install):
    fake = install(FakeTasks())
    set_pipeline(engine, ["first", group(plain("a"))])

    assert engine.execute_pipeline("test_module", "run_all") == 0
    assert [c[0] for c in fake.calls] == ["first", "a"]
