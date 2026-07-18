import * as vscode from "vscode";
import { AnnotationSpec, buildRegExp, specForFileName } from "./annotationSpec";

const DESCRIPTIONS: Record<string, string> = {
  task: "Declares this file as a Model Flow task. Attributes: `name` (task name) and `module` (module name). A file with no `task` annotation is skipped by the parser.",
  config: "Declares one configuration parameter. The line immediately after this annotation must be the parameter's literal default-value assignment, in the exact syntax required for this file's language.",
  description_start: "Marks the start of the task's free-text description block (accumulated until `@MODELFLOW_description_end`).",
  description_end: "Marks the end of the task's free-text description block.",
};

export function createHoverProvider(spec: AnnotationSpec): vscode.HoverProvider {
  return {
    provideHover(document, position) {
      const fileSpec = specForFileName(spec, document.fileName);
      if (!fileSpec) {
        return undefined;
      }

      const line = document.lineAt(position.line).text.trim();
      const annotationRe = buildRegExp(fileSpec.annotationPattern, fileSpec.annotationPatternFlags);
      const match = annotationRe.exec(line);
      if (!match) {
        return undefined;
      }

      const key = (match[1] || "").trim();
      const description = DESCRIPTIONS[key];
      if (!description) {
        return undefined;
      }

      const markdown = new vscode.MarkdownString(`**@MODELFLOW_${key}**\n\n${description}`);
      return new vscode.Hover(markdown, document.lineAt(position.line).range);
    },
  };
}
