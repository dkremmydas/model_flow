# IFMCAP flow

## Introduction

 IFMCAP is comprised of many small independent scripts that transform input data into ouput data. This enables a modular structure that isolates the logic of individual tasks and allows the modular structure of IFMCAP. On the other hand, this compartmentalization of IFMCAPinto numerous small independent tasks, makes it difficult to keep the overarching logic of IFMCAP. For this, IFMCAP flow provides the infrastructure to organize the different small tasks in a more explicit way.

## Terminology

IFMCAP is organized into *Modules*. Each *Module* is organized into *Tasks*. Here’s a glossary of key terms related with the tool.

1. Module: A collection of Tasks with an overarching logic. By convention, a module is contained inside a unique folder.

2. Task: A unit of work or operation to be performed. It corresponds to a single self-contained script. It follows the black-box pattern, where the script reads one or more input files and produces one or more output files. The user also control the behavior of the script with configuration parameters. A task belongs to a single module.

3. Pipeline: A structured series of tasks, where the output of one task is the input for the next. It is automated with no manual/human intervention. A Module can have one or more pipelines. Apipeline beolongs to one module.

4. Workflow: A structured series of modules, where the output of one module is the input of another. Workflows belong to IFMCAP model. They are not contained in modules.

5. Task Dependency: A relationship where one task relies on the completion of another task before it can begin.

6. Job: A single execution of a task, pipeline or workflow, often managed by a scheduler or orchestrator.

7. Scheduler: A system that determines when and in what order tasks should be executed.

8. Execution Engine: A system that runs tasks and handles their inputs, outputs, and dependencies.

9. Annotations: In programming, annotations are additional information or metadata added to parts of code. They provide extra semantic meaning or instructions to tools, frameworks, or compilers without affecting the code's execution directly.

## How the tool works

### Overview

The tool works by:

1. In each module (folder) a *pipelines.flow* text file contains definitions of pipelines of the module. The contents are in json and contain the tasks. In case we need to run the task with a different value than that of the configuration variables o

2. In each self-contained script that corresponds to a task, inline annotations provide information on the task (e.g input and output files, configuration parameters, etc.)

3. For each module in IFMCAP, the module.flow and the script annotations are parsed. The file workflows.flow is created.

4. A script allows one to browse the modules tasks and pipelines. It also allows to execute a tak or a pipeline.

### Command line

The main executable is the ifmcap_flow script. We call it like

<pre>
python ifmcap_flow [command] [parameters]*
</pre>

The commands are:

- build: parse recursively the directories and create the *ifmcap_flow.json.db*
  - Required parameters:
    - --dir="{ifmcap root directory}"

- run_task: run a task
  - Required parameters:
    - --dir="{ifmcap root directory}"
    - --module="{the module of ifmcap that contains the task}"
    - --task="{the task name}"

- run_pipeline: run a pipeline
  - Required parameters:
    - --dir="{ifmcap root directory}"
    - --module="{the module of ifmcap that contains the task}"
    - --pipeline="{the pipeline name}"

## Annotations

An annotation variable has the following form, {C}@IFMCAP_{annotation} [{attribute name}="{attribute value}]*

The {C} is the programming language specific comment character. For example in R, {C}=#, in GAMS, {C}=*. 

Examples of valid annotations are below:

- #@IFMCAP_task name="Compile external data" module="d.econ_social_ind"
- #@IFMCAP_description_start
- #@IFMCAP_config name="external_data" type="config_var" relative="0"

Attributes are of two types:

- Explicit attributes: they are defined explicitly in the line of the annotation by the author of the script
- Implicit attributes: they are automatically parsed from the source code 

A list of accepted annotation their semantics and their attributes are below:

- @IFMCAP_task: The script corresponds to a Task
  - Explicit attributes:
    - name: the name of the task
    - module: the module it belongs to. It should have a folder like structure. For example "v.main2020/p.scenar2020" or "d.fadn".
    - previous: the task that precedes it
  - Implicit attributes

- @IFMCAP_description_start ... @IFMCAP_description_end
  - Implicit attributes
    - description: Any lines between the start and the end of the annotation will be saved in the description attribute of the task

- @IFMCAP_config: A configuration variable (e.g. an input file, output file or another config variable). The next line will have the default value in the file
  - Explicit attributes:
    - name: the name of the variable
    - type: {number, string}
    - role: {input_file, output_file, config_var}
    - relative: {0,1} Relative to the DatabaseDirectory? 1=yes and 0=no; default is 1
  - Implicit attributes:
    - script_name: the name as defined in the script
    - script_value: the value that exist in the script
