// Copies the repo-root annotation-spec.json (the single source of truth shared
// with classes/Task.py, see test/test_annotation_spec_matches_task_py.py) into
// this extension's own folder so it ships inside the packaged .vsix and can be
// read at runtime without depending on the rest of the repo being checked out
// next to an installed extension.
const fs = require("fs");
const path = require("path");

const source = path.join(__dirname, "..", "..", "annotation-spec.json");
const destination = path.join(__dirname, "..", "annotation-spec.json");

fs.copyFileSync(source, destination);
console.log(`Copied ${source} -> ${destination}`);
