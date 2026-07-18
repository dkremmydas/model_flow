import * as fs from "fs";
import * as path from "path";

export interface FiletypeSpec {
  commentPrefix: string;
  annotationPattern: string;
  annotationPatternFlags: string;
  configValuePattern: string;
  configValuePatternFlags: string;
  configValueExample: string;
}

export interface AnnotationSpec {
  annotationKeys: string[];
  attributePattern: string;
  attributesByKey: Record<string, string[]>;
  filetypes: Record<string, FiletypeSpec>;
}

let cachedSpec: AnnotationSpec | undefined;

/**
 * Loads annotation-spec.json (copied alongside this extension by
 * scripts/copy-spec.js at build time -- see that script's comment). This is
 * the single source of truth shared with classes/Task.py; every regex/attribute
 * name used by this extension's diagnostics/snippets/hover comes from here so
 * it can never silently drift from the real Python parser.
 */
export function loadAnnotationSpec(extensionPath: string): AnnotationSpec {
  if (cachedSpec) {
    return cachedSpec;
  }
  const specPath = path.join(extensionPath, "annotation-spec.json");
  const raw = fs.readFileSync(specPath, "utf-8");
  cachedSpec = JSON.parse(raw) as AnnotationSpec;
  return cachedSpec;
}

/** Looks up the annotation-spec.json entry for a file's extension (e.g. ".r"), if any. */
export function specForFileName(spec: AnnotationSpec, fileName: string): FiletypeSpec | undefined {
  const ext = path.extname(fileName).toLowerCase();
  return spec.filetypes[ext];
}

export function buildRegExp(pattern: string, flags: string): RegExp {
  return new RegExp(pattern, flags);
}
