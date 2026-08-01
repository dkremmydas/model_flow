# R tasks

R scripts (`.r`) use `#` as the annotation comment character:
`#@MODELFLOW_...`.

A `@MODELFLOW_config` annotation's value line must be a plain assignment,
optionally with a trailing comma:

```r
name = value,
```

## Example

```r
#@MODELFLOW_task name="1_create_baseline_data" module="v.main2020/d.baseline"

#@MODELFLOW_description_start
# Imports and prepares the baseline data.
#@MODELFLOW_description_end

#@MODELFLOW_config name="input_file" role="input_file" relative="0"
input_file = "d.fadn/output/data.csv"

#@MODELFLOW_config name="output_file" role="output_file" relative="0"
output_file = "v.main2020/d.baseline/baseline_data.csv"

#@MODELFLOW_config name="threshold" role="parameter" type="number"
threshold = 0.5
```

See [task-annotations.md](task-annotations.md) for the full annotation and
attribute reference.
