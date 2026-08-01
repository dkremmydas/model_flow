# R Markdown tasks

R Markdown files (`.rmd`) use `#` as the annotation comment character, same as
plain R. `@MODELFLOW_task`/`@MODELFLOW_description_*` can go anywhere in the
document (commonly right after the YAML front matter's opening `---`).
`@MODELFLOW_config` annotations go inside the YAML front matter's `params:`
block, and their value line uses YAML syntax rather than R assignment syntax:

```yaml
name: value
```

Rendering an `.rmd` task requires `Pandoc_dir` to be set in the config (it's
optional at the `Config` level, since not every model has `.rmd` tasks, but
effectively required once one exists).

## Example

```rmd
---
#@MODELFLOW_task name="1_create_baseline_data" module="v.main2020/d.baseline"
title: "Create baseline data"
author: "Lola Rey"
output:
  html_document:
    toc: true
    toc_depth: 5
params:
  #@MODELFLOW_config name="database_dir" role="parameter" type="string"
  database_dir: "E:/IFM_CAP2/Database2020"

  #@MODELFLOW_config name="d_fadn_data_file" role="input_file" relative="0"
  d_fadn_data_file: "d.fadn/ifm_cap_out/d_fadn_ifm_cap_data_2020.gdx"

  #@MODELFLOW_config name="calib_output" role="input_file" relative="0"
  calib_output: "v.main2020/d.calibration/output_PMP.gdx"

  #@MODELFLOW_config name="output_dir" role="parameter" type="string"
  output_dir: "v.main2020/d.baseline/"
---
```

See [task-annotations.md](task-annotations.md) for the full annotation and
attribute reference.
