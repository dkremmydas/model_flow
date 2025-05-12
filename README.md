# Model flow

## Introduction

 In modular design, a model is comprised of many small independent scripts that transform input data into ouput data. This enables a modular structure that isolates the logic of individual tasks and allows the modular structure of a model. On the other hand, this compartmentalization of the model into numerous small independent tasks, makes it difficult to keep the overarching logic of the model. For this, model flow provides the infrastructure to organize the different small tasks in a more explicit way.

## Terminology

A model is organized into *Modules*. Each *Module* is organized into *Tasks*. Here’s a glossary of key terms related with the tool.

1. Module: A collection of Tasks with an overarching logic. By convention, a module is contained inside a unique folder.

2. Task: A unit of work or operation to be performed. It corresponds to a single self-contained script. It follows the black-box pattern, where the script reads one or more input files and produces one or more output files. The user also control the behavior of the script with configuration parameters. A task belongs to a single module.

3. Pipeline: A structured series of tasks, where the output of one task is the input for the next. It is automated with no manual/human intervention. A Module can have one or more pipelines. Apipeline beolongs to one module.

4. Workflow: A structured series of modules, where the output of one module is the input of another. Workflows belong to the model as a whole. They are not contained in modules.

5. Task Dependency: A relationship where one task relies on the completion of another task before it can begin.

6. Job: A single execution of a task, pipeline or workflow, often managed by a scheduler or orchestrator.

7. Scheduler: A system that determines when and in what order tasks should be executed.

8. Execution Engine: A system that runs tasks and handles their inputs, outputs, and dependencies.

9. Annotations: In programming, annotations are additional information or metadata added to parts of code. They provide extra semantic meaning or instructions to tools, frameworks, or compilers without affecting the code's execution directly.

## How the tool works

The tool works by:

1. In each module (folder) a *module.flow.json* text file contains definitions of pipelines of the module. The contents are in json and contain the tasks. In case we need to run the task with a different value than that of the configuration variables o

2. In each self-contained script that corresponds to a task, inline annotations provide information on the task (e.g input and output files, configuration parameters, etc.)

3. For each module, the module.flow.json and the script annotations are parsed. The file *model_flow.db.json* is created that is a database of the tasks and the pipelines.

4. The *model_flow.py* script contains commands that allows to execute a tak or a pipeline.

5. A GUI allows to create/edit pipelines from tasks. It shows the available tasks per module. It allows to change the default script parameters.

## Command line

The main executable is the model_flow script. We call it like

<pre>
python model_flow [command] [parameters]*
</pre>

The commands are:

### init

Initializes a configuration file. It asks for the database and th code directory and saves the configuration file into the database directory. When using model_flow for the first time, use this command.


### build

Recursively scans the specified code directory to identify all model tasks and creates a centralized database file (`model_flow.db.json`) in the configured Database_directory.

- Required Parameters:

  - --config \<file>       Path to configuration JSON file. The config file must contain,

   ```json
   {
     "Code_directory": "path/to/model/code",
     "Database_directory": "path/to/model/database"
   }
   ```

### run_task

Run a task

- Required Parameters:
  - --config \<file>       Path to configuration JSON file
  - --module \<name>       Module containing the task (e.g., "v.main2020/d.policy")
  - --task \<name>         Name of task to execute (e.g., "1_create_policy_data")
- Optional parameters:
  - --output_dir \<directory>   The directory where any log output will be saved. Default is the temporary directory
- Parameter Overrides
  - --set \<var> \<value>   Override a single configuration value; Can be specified multiple times; Example: --set input_file "data/new_input.csv"
- Parallel Execution with Value Ranges:
  - --parallel            Enable parallel execution mode
  - --range \<var> \<start> \<end> \<step>    Execute with a numeric range of values; Example: --range threshold 0.1 1.0 0.2
  - --values \<var> \<val1> \<val2>...       Execute with specific values;  Example: --values method "A" "B" "C"

**Notes:**

1. When using --parallel with ranges/values:
   - The task will execute once for each combination of parameters
   - All executions run in parallel (up to system limits)
   - Output files should include parameter values to avoid conflicts

2. Parameter types are automatically detected:
   - Numbers (1, 3.14)
   - Booleans (true, false)
   - Strings (quoted if containing spaces)

### run_pipeline

Run a pipeline

- Required Parameters:
  - --config \<file>       Path to configuration JSON file
  - --module \<name>       Module containing the task (e.g., "v.main2020/d.policy")
  - --task \<name>         Task name to inspect

- list_tasks: list the available tasks
- Required parameters:
  - --dir="{model root directory}"
- Optional parameters:
  - --module="{the module that contains the task}"

### show_task

Display detailed information about a specific task.

- Required parameters:
  - --dir="{model datababase directory}"
  - --module="{the module that contains the task}"
  - --pipeline="{the pipeline name}"

### list_tasks

List all available tasks with filtering options.

- Required parameters:
  - --config \<file>       Path to configuration JSON file
- Optional parameters:
  - --module="{the module that contains the task}"

### Examples

1. Basic execution:
   - model_flow build --config "E:/IFM_CAP2/Code/conf/model_flow.config.json"
   - model_flow list_tasks --module="d.estat" --config="E:/IFM_CAP2/Code/conf/model_flow.config.json"
   - model_flow run_task --task="00_initialization" --module="d.fadn" --config="E:/IFM_CAP2/Database2020/model_flow.config.json"
   - model_flow run_task --task="1_download_and_prepare" --module="d.estat" --output_dir="E:/IFM_CAP2/Database2020/d.estat" --config="E:/IFM_CAP2/Database2020/model_flow.config.json"
   - model_flow run_task --task="1_import_agri_csv" --module="d.fadn" --output_dir="E:/IFM_CAP2/Database2020/d.fadn" --config="E:/IFM_CAP2/Code/conf/model_flow.config.json" --set root_csv "E:/IFM_CAP2/original_csv" --set raw_str_map "E:/IFM_CAP2/Model External Data/raw_str_map.2014_and_after.json"

2. With parameter override:
   model_flow run_task --config=config.json  --module=v.main2020/d.policy  --task=1_create_policy_data  --set year 2023  --set input_file "data/new_data.csv"

3. Parallel execution with value range:
   model_flow run_task --config=config.json  --module=model/training  --task=train_model  --parallel  --range learning_rate 0.001 0.01 0.002

4. Parallel execution with specific values:
   model_flow run_task --config=config.json  --module=model/training  --task=train_model  --parallel  --values optimizer "adam" "sgd"  --values batch_size 32 64 128

## Annotations

An annotation variable has the following form, {C}@MODELFLOW_{annotation} [{attribute name}="{attribute value}]*

The {C} is the programming language specific comment character. For example in R, {C}=#, in GAMS, {C}=*. 

Examples of valid annotations are below:

- #@MODELFLOW_task name="Compile external data" module="d.econ_social_ind"
- #@MODELFLOW_description_start
- #@MODELFLOW_config name="external_data" type="parameter" relative="0"

Attributes are of two types:

- Explicit attributes: they are defined explicitly in the line of the annotation by the author of the script
- Implicit attributes: they are automatically parsed from the source code 

A list of accepted annotation their semantics and their attributes are below

### @MODELFLOW_task

Defines that the source file corresponds to a Task

- Explicit attributes:
  - name: the name of the task
  - module: the module it belongs to. It should have a folder like structure. For example "v.main2020/p.scenar2020" or "d.fadn".
- Implicit attributes

### @MODELFLOW_description_start ... @MODELFLOW_description_end

Defines lines that provide a description of the source file 

- Implicit attributes
  - description: Any lines between the start and the end of the annotation will be saved in the description attribute of the task

### @MODELFLOW_config

A configuration variable (e.g. an input file, output file or another config variable). The next line will have the default value in the file

- Explicit attributes:
  - name: the name of the variable
  - role: {input_file, output_file, parameter}
  - type: {number, string}; only for role=="parameter
  - relative: {0,1} Relative to the DatabaseDirectory? 1=yes and 0=no; default is 1; only for role=={"input_file","output_file}
- Implicit attributes:
  - script_name: the name as defined in the script
  - script_value: the value that exist in the script

## How to prepare files for model_flow

For controlling the source files through the model_flow tool, they need to contains special chunks of code.

The code ensures that the configuration of the script can be exposed to the flow tool.

### GAMS files

The gams file taks should contain the following code:

```gams
$IFTHENI.controlled NOT %CONTROLLED% == "1"

$  SET CONFIG_VAR_1 "CONFIG_VALUE_1"

$  SET CONFIG_VAR_2 "CONFIG_VALUE_2"

$  SET CONFIG_VAR_N "CONFIG_VALUE_N"

$ENDIF.controlled
```

An example of a gams file controlled with the flow tool is below.

Anytime the script is called from an external srouce (e.g. cmd), the CONTROLLED global variable should be set to 1, e.g. gams script.gms --CONTROLLED=1.

The code below allow, when running the gams file through the GAMS IDE, to consider the code configuration values, while to disregard them when the script is run outseide of the IDE.

```gams
$IFTHENI.controlled NOT %CONTROLLED% == "1"

*$  SET BASELINE_DATA "v.main2020/p.2024_06_scenar2040/input/baseline_data.gdx"
$  SET BASELINE_DATA "v.main2020/d.baseline/baseline_data.addAct_capriTr_pol2023_infl.bef_ECO.gdx"

* The spatial resolution that the file is solved for.
*  NUTS2,NUTS3,BATCH
$  SET RUN_RESOLUTION "NUTS3"

*  Defining which NUTS2 region(s) to run
$  SET RUN_NUTS "BE211"

*  The number of jobs the NUTS level will be splitted
$  SET BATCH_JOB_NUMBER 1000

*  The current job number
$  SET BATCH_JOB_CUR 1

*  Save debug information?
$  SET DEBUG "YES"

$  SET OUTPUT_FILE "v.main2020/d.baseline/ecoscheme_calibration/calibration_test_BE211.gdx"

*  The ID of the farm(s) to run. If active, the model will run only for the selected farm(s). In case of
*     more than one farm add farm codes using comma: 74000000020130,74000000020387,...,etc.
$ SET RUNF_ID 615005400773



* The voluntary eco-scheme to run. If active it will run only this eco-scheme.
*  It still enforces the madnatory GAECs
*$ SET RUN_ECO_VOL  "BE_FL-1.1 BE_FL-1.1"


$ENDIF.controlled
```

### Rmd Files

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
  #@MODELFLOW_config name="database_dir" role="config_var" type="string" 
  database_dir: "E:/IFM_CAP2/Database2020"
  
  #@MODELFLOW_config name="d_fadn_data_file" role="input_file" relative="0"
  d_fadn_data_file: "d.fadn/ifm_cap_out/d_fadn_ifm_cap_data_2020.gdx"
  
  #@MODELFLOW_config name="calib_output" role="input_file" relative="0"
  calib_output: "v.main2020/d.calibration/output_PMP.gdx"
  
  #@MODELFLOW_config name="feed_data" role="input_file" relative="0"
  feed_data: "v.main2020/d.feed/output/estimations/d_feed_data_out_ALL.gdx"
  
  #@MODELFLOW_config name="add_acts_data" role="input_file" relative="0"
  add_acts_data: "v.main2020/d.add_acts/default/output_add_acts.gdx"
  
  #@MODELFLOW_config name="capri_trend_file2020" role="input_file" relative="0"
  capri_trend_file2020: "U:/SCIENTIFIC/FARM @ U/30-Projects/01-IFM-CAP/04-Model External Data/capri_data/d.baseline/res_2_1720scenar2040_refdefaulta.gdx" 
  #capri_trend_file2040: "U:/SCIENTIFIC/FARM @ U/30-Projects/01-IFM-CAP/04-Model External Data/capri_data/d.baseline/res_2_1740scenar2040_refdefaulta.gdx"
  
  #@MODELFLOW_config name="capri_trend_file2040" role="input_file" relative="0"
  capri_trend_file2040: "U:/SCIENTIFIC/FARM @ U/30-Projects/01-IFM-CAP/04-Model External Data/capri_data/p.2024_06_scenar2040/yield_20241013_from_scenar2030/res_2_1740scenar2040_refpol_exotechCSP_all_scenar2040defaulta.gdx"
  
  #@MODELFLOW_config name="CAP_payments" role="input_file" relative="0"
  CAP_payments: "v.main2020/d.policy/02.payments_without_ecoschemes.gdx"
  
  #@MODELFLOW_config name="ECO_specs"  role="input_file" relative="0"
  ECO_specs: "v.main2020/d.policy/02.ecoscheme_specification_conversion.gdx"
  
  #@MODELFLOW_config name="ECO_specs_farm_level"  role="input_file" relative="0"
  ECO_specs_farm_level: "v.main2020/d.policy/02.ecoscheme_specification_farm_level.gdx"
  
  #@MODELFLOW_config name="external_data" type="parameter" type="string"
  external_data: "U:/SCIENTIFIC/FARM @ U/30-Projects/01-IFM-CAP/04-Model External Data"
  
  #@MODELFLOW_config name="output_dir" type="parameter" type="string"
  output_dir: "v.main2020/d.baseline/"
  ```