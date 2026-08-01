# Lists

A List is a named, ordered collection of values — e.g. the set of NUTS0
country codes or NUTS2 region codes used across a CAP model — kept in one
place so scripts/parameters can reference it by name instead of every task
repeating (and risking drifting copies of) the same values.

Outside of pipeline loops, Lists are a plain reference/lookup mechanism —
nothing else in `model_flow` reads them yet.

## Source lists

Unlike tasks and pipelines, lists aren't scanned via a script annotation —
there's no task/module involved. Instead, a `model_flow.lists.json` file can
be placed in **any** folder of `Code_directory` (not just the root, and not
one-per-module either — a folder either has one or it doesn't):

```json
{
  "lists": [
    {
      "name": "nuts0",
      "type": "string",
      "description": "EU27 member state codes (NUTS level 0).",
      "elements": ["AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "..."]
    }
  ]
}
```

- `name` — the list's identifier. Must be unique across the whole
  `Code_directory` tree — a duplicate found in another folder is dropped with
  a warning, first-seen wins.
- `type` — `string` or `number`; the type of every entry in `elements`.
- `elements` — the ordered list of values.
- `description` — optional free text.

## List discovery

`model_flow build` (`Parser.parse_lists`) walks every folder of
`Code_directory` looking for a `model_flow.lists.json`, collects every list it
declares, tags each one with the folder it was found in (relative to
`Code_directory`, forward slashes, `"."` for the root itself), and writes the
aggregated result to `model_flow.lists.json` in `Database_directory` —
mirroring how `model_flow.db.json`/`model_flow.pipelines.json` are themselves
build-generated, not hand-maintained in `Database_directory` directly. For
example, a list declared in
`Code_directory/v.main2020/d.policy/model_flow.lists.json` ends up in the
aggregated file as
`{"name": "nuts2", ..., "folder": "v.main2020/d.policy"}`.

## User-defined lists

`model_flow.lists_user.json`, in `Database_directory`, is where a user can
define their own lists directly, without touching the build-generated source
file. It's optional and only needs to exist once something has actually been
added to it. On a name collision between the two stores, the build-generated
(shared) list wins.

## Using lists in pipeline loops

Lists are consumed by a pipeline task's `loop` declaration (see
[pipelines.md](pipelines.md#looping-over-lists)), which runs that task once
per element (or combination of elements, across several Lists) instead of
just once. `ExecutionEngine` re-resolves a list's current elements at run
time — via its own `Lists` instance — rather than trusting whatever snapshot
the pipeline's own last `build` saw, so editing a list's elements takes effect
on the next run without needing to rebuild the pipeline.

## Scope and uniqueness rules

- List names have no module scoping — a `model_flow.lists.json` can sit in
  any folder, not just one per module.
- A list `name` must be unique across the *entire* `Code_directory` walk
  (not per-folder), since the merged result and `classes/Lists.py` both key
  purely by name.
