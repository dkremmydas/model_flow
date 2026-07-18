import * as vscode from "vscode";
import { AnnotationSpec, buildRegExp, specForFileName } from "./annotationSpec";

/**
 * Re-implements the same walk classes/Task.py's _parse_file_R/_parse_file_GAMS/
 * _parse_file_BAT do -- annotation line, then (for "config") check the next
 * line against that filetype's required value-line form -- purely to surface
 * problems as editor diagnostics. This does NOT replace model_flow build's own
 * parsing; it's a best-effort live approximation using the same shared
 * annotation-spec.json patterns, so it can drift only if that spec itself
 * drifts from Task.py (guarded against by test_annotation_spec_matches_task_py.py).
 */
export function computeDiagnostics(document: vscode.TextDocument, spec: AnnotationSpec): vscode.Diagnostic[] {
  const fileSpec = specForFileName(spec, document.fileName);
  if (!fileSpec) {
    return [];
  }

  const annotationRe = buildRegExp(fileSpec.annotationPattern, fileSpec.annotationPatternFlags);
  const configValueRe = buildRegExp(fileSpec.configValuePattern, fileSpec.configValuePatternFlags);
  const isBat = document.fileName.toLowerCase().endsWith(".bat");

  const diagnostics: vscode.Diagnostic[] = [];
  let seenTask = false;

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex++) {
    const line = document.lineAt(lineIndex);
    const match = annotationRe.exec(line.text.trim());
    if (!match) {
      continue;
    }

    const key = (match[1] || "").trim();
    if (!spec.annotationKeys.includes(key)) {
      diagnostics.push(
        new vscode.Diagnostic(
          line.range,
          `Unrecognized Model Flow annotation '@MODELFLOW_${key}'.`,
          vscode.DiagnosticSeverity.Warning
        )
      );
      continue;
    }

    if (key === "task") {
      if (seenTask) {
        diagnostics.push(
          new vscode.Diagnostic(
            line.range,
            "Duplicate @MODELFLOW_task annotation -- only the first is used.",
            vscode.DiagnosticSeverity.Warning
          )
        );
      }
      seenTask = true;
    }

    if (key === "config") {
      const nextLineIndex = lineIndex + 1;
      if (nextLineIndex >= document.lineCount) {
        diagnostics.push(
          new vscode.Diagnostic(
            line.range,
            `@MODELFLOW_config must be followed by a value line, e.g. '${fileSpec.configValueExample}'.`,
            vscode.DiagnosticSeverity.Warning
          )
        );
        continue;
      }

      const nextLine = document.lineAt(nextLineIndex);
      const nextLineText = nextLine.text.trim();
      const valueMatch = configValueRe.exec(nextLineText);

      if (!valueMatch) {
        diagnostics.push(
          new vscode.Diagnostic(
            nextLine.range,
            `Invalid Model Flow config value line: expected the form '${fileSpec.configValueExample}', got '${nextLineText}'.`,
            vscode.DiagnosticSeverity.Warning
          )
        );
      } else if (isBat && valueMatch[1].toLowerCase() !== valueMatch[2].toLowerCase()) {
        // Mirrors Task.py's extra check beyond the regex itself: the guard
        // variable (IF NOT DEFINED <var>) and the SET variable must match.
        diagnostics.push(
          new vscode.Diagnostic(
            nextLine.range,
            `Guard variable '${valueMatch[1]}' does not match SET variable '${valueMatch[2]}'.`,
            vscode.DiagnosticSeverity.Warning
          )
        );
      }
    }
  }

  return diagnostics;
}
