import * as vscode from "vscode";
import { loadAnnotationSpec } from "./annotationSpec";
import { computeDiagnostics } from "./diagnostics";
import { createHoverProvider } from "./hoverProvider";
import { configAnnotationSnippet, descriptionBlockSnippet, taskAnnotationSnippet } from "./snippets";

const SUPPORTED_EXTENSIONS = [".r", ".rmd", ".gms", ".bat"];

function isSupported(document: vscode.TextDocument): boolean {
  const fileName = document.fileName.toLowerCase();
  return SUPPORTED_EXTENSIONS.some((ext) => fileName.endsWith(ext));
}

export function activate(context: vscode.ExtensionContext): void {
  const spec = loadAnnotationSpec(context.extensionPath);

  const diagnosticCollection = vscode.languages.createDiagnosticCollection("modelFlow");
  context.subscriptions.push(diagnosticCollection);

  const refresh = (document: vscode.TextDocument) => {
    if (!isSupported(document)) {
      return;
    }
    diagnosticCollection.set(document.uri, computeDiagnostics(document, spec));
  };

  vscode.workspace.textDocuments.forEach(refresh);

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument(refresh),
    vscode.workspace.onDidChangeTextDocument((event) => refresh(event.document)),
    vscode.workspace.onDidCloseTextDocument((document) => diagnosticCollection.delete(document.uri))
  );

  context.subscriptions.push(
    vscode.languages.registerHoverProvider(
      [{ pattern: "**/*.r" }, { pattern: "**/*.rmd" }, { pattern: "**/*.gms" }, { pattern: "**/*.bat" }],
      createHoverProvider(spec)
    )
  );

  const registerInsertCommand = (
    command: string,
    build: (spec: import("./annotationSpec").AnnotationSpec, fileName: string) => string | undefined
  ) => {
    context.subscriptions.push(
      vscode.commands.registerCommand(command, async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
          return;
        }
        const snippetText = build(spec, editor.document.fileName);
        if (!snippetText) {
          vscode.window.showWarningMessage(
            "Model Flow: this file's extension isn't one of .r/.rmd/.gms/.bat."
          );
          return;
        }
        await editor.insertSnippet(new vscode.SnippetString(snippetText));
      })
    );
  };

  registerInsertCommand("modelFlow.insertTaskAnnotation", taskAnnotationSnippet);
  registerInsertCommand("modelFlow.insertConfigAnnotation", configAnnotationSnippet);
  registerInsertCommand("modelFlow.insertDescriptionBlock", descriptionBlockSnippet);
}

export function deactivate(): void {}
