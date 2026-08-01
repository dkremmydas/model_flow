# GAMS tasks

GAMS files (`.gms`) use `*` as the annotation comment character:
`*@MODELFLOW_...`.

A `@MODELFLOW_config` annotation's value line must be:

```gams
$ SET NAME "value"
```

## Controlled block

A GAMS task should wrap its configuration in a `$IFTHENI.controlled` block so
the same file behaves correctly both when opened in the GAMS IDE (where the
hard-coded values below apply) and when launched externally by Model Flow
(where `--CONTROLLED=1` is passed and the block is skipped in favor of
injected values):

```gams
$IFTHENI.controlled NOT %CONTROLLED% == "1"

$  SET CONFIG_VAR_1 "CONFIG_VALUE_1"

$  SET CONFIG_VAR_2 "CONFIG_VALUE_2"

$  SET CONFIG_VAR_N "CONFIG_VALUE_N"

$ENDIF.controlled
```

Whenever the script is called from an external source (e.g. `cmd`, or Model
Flow itself), the `CONTROLLED` global should be set to `1`:
`gams script.gms --CONTROLLED=1`.

## Worked example

```gams
$IFTHENI.controlled NOT %CONTROLLED% == "1"

*@MODELFLOW_config name="baseline_data" role="input_file" relative="0"
$  SET BASELINE_DATA "v.main2020/d.baseline/baseline_data.addAct_capriTr_pol2023_infl.bef_ECO.gdx"

* The spatial resolution that the file is solved for.
*  NUTS2,NUTS3,BATCH
*@MODELFLOW_config name="run_resolution" role="parameter" type="string"
$  SET RUN_RESOLUTION "NUTS3"

*  Defining which NUTS2 region(s) to run
*@MODELFLOW_config name="run_nuts" role="parameter" type="string"
$  SET RUN_NUTS "BE211"

*  Save debug information?
*@MODELFLOW_config name="debug" role="parameter" type="string"
$  SET DEBUG "YES"

*@MODELFLOW_config name="output_file" role="output_file" relative="0"
$  SET OUTPUT_FILE "v.main2020/d.baseline/ecoscheme_calibration/calibration_test_BE211.gdx"

$ENDIF.controlled
```

See [task-annotations.md](task-annotations.md) for the full annotation and
attribute reference.
