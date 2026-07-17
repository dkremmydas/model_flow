from classes.Task import Task


def write(tmp_path, filename, content):
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return path


def test_r_task_name_module_and_config(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_test_R" module="test_module"\n'
        "#@MODELFLOW_config name=\"ext_par\" type=\"number\" role=\"parameter\"\n"
        "ext_par = 5\n"
    )
    task = Task(str(write(tmp_path, "script.R", content)))

    assert task.name == "1_test_R"
    assert task.module == "test_module"
    assert task.config == [
        {
            "name": "ext_par",
            "type": "number",
            "role": "parameter",
            "script_name": "ext_par",
            "script_value": "5",
        }
    ]


def test_r_task_description_skips_non_alpha_lines(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_test_R" module="test_module"\n'
        "#@MODELFLOW_description_start\n"
        "Line one.\n"
        "\n"
        "***\n"
        "Line two.\n"
        "#@MODELFLOW_description_end\n"
    )
    task = Task(str(write(tmp_path, "script.R", content)))

    assert task.description.strip() == "Line one.\nLine two."


def test_file_without_task_annotation_has_no_name(tmp_path):
    content = "# just a regular comment\nx <- 1\n"
    task = Task(str(write(tmp_path, "script.R", content)))

    assert task.name is False
    assert task.module is False


def test_rmd_config_uses_colon_syntax(tmp_path):
    content = (
        '#@MODELFLOW_task name="1_create_baseline_data" module="v.main2020/d.baseline"\n'
        "#@MODELFLOW_config name=\"database_dir\" role=\"config_var\" type=\"string\"\n"
        'database_dir: "E:/IFM_CAP2/Database2020"\n'
    )
    task = Task(str(write(tmp_path, "script.rmd", content)))

    assert task.name == "1_create_baseline_data"
    assert task.module == "v.main2020/d.baseline"
    assert task.config == [
        {
            "name": "database_dir",
            "role": "config_var",
            "type": "string",
            "script_name": "database_dir",
            "script_value": "E:/IFM_CAP2/Database2020",
        }
    ]


def test_gams_task_name_module_and_config(tmp_path):
    content = (
        '* @MODELFLOW_task name="1_test_gams" module="test_module"\n'
        '* @MODELFLOW_config name="limit" role="parameter" type="number"\n'
        "$ SET limit 15\n"
    )
    task = Task(str(write(tmp_path, "script.gms", content)))

    assert task.name == "1_test_gams"
    assert task.module == "test_module"
    assert task.config == [
        {
            "name": "limit",
            "role": "parameter",
            "type": "number",
            "script_name": "limit",
            "script_value": "15",
        }
    ]


def test_bat_task_name_module_and_config(tmp_path):
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        '::@MODELFLOW_config name="target_dir" role="parameter" type="string"\n'
        'IF NOT DEFINED target_dir SET "target_dir=C:\\tools"\n'
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.name == "install_deps"
    assert task.module == "admin"
    assert task.config == [
        {
            "name": "target_dir",
            "role": "parameter",
            "type": "string",
            "script_name": "target_dir",
            "script_value": "C:\\tools",
        }
    ]


def test_bat_task_config_rejects_unquoted_set_with_warning(tmp_path, capsys):
    """Only the quoted SET "VAR=value" form is a valid parameter definition. An
    unquoted "set VAR=value" must be rejected (warned about, not parsed) rather
    than silently accepted."""
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        '::@MODELFLOW_config name="target_dir" role="parameter" type="string"\n'
        "set target_dir=C:\\tools\n"
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.config == []
    assert "invalid" in capsys.readouterr().out.lower()


def test_bat_task_config_accepts_if_not_defined_guard(tmp_path):
    """The guarded, quoted form IF NOT DEFINED VAR SET "VAR=value" is the only
    valid parameter definition -- the guard lets an externally-injected
    override survive the script running, unlike an unconditional SET."""
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        '::@MODELFLOW_config name="target_dir" role="parameter" type="string"\n'
        'IF NOT DEFINED target_dir SET "target_dir=C:\\tools"\n'
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.config == [
        {
            "name": "target_dir",
            "role": "parameter",
            "type": "string",
            "script_name": "target_dir",
            "script_value": "C:\\tools",
        }
    ]


def test_bat_task_config_rejects_unguarded_quoted_set_with_warning(tmp_path, capsys):
    """The old unguarded quoted form SET "VAR=value" is no longer valid -- it
    always clobbers an injected override, so only the guarded form is accepted."""
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        '::@MODELFLOW_config name="target_dir" role="parameter" type="string"\n'
        'SET "target_dir=C:\\tools"\n'
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.config == []
    assert "invalid" in capsys.readouterr().out.lower()


def test_bat_task_config_rejects_guard_variable_mismatch_with_warning(tmp_path, capsys):
    """The guard variable and the SET variable must be the same name."""
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        '::@MODELFLOW_config name="target_dir" role="parameter" type="string"\n'
        'IF NOT DEFINED other_var SET "target_dir=C:\\tools"\n'
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.config == []
    assert "invalid" in capsys.readouterr().out.lower()


def test_bat_task_description_block(tmp_path):
    content = (
        '::@MODELFLOW_task name="install_deps" module="admin"\n'
        "::@MODELFLOW_description_start\n"
        ":: Installs required tools.\n"
        "::@MODELFLOW_description_end\n"
    )
    task = Task(str(write(tmp_path, "script.bat", content)))

    assert task.description.strip() == ":: Installs required tools."
