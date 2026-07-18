import { AnnotationSpec, specForFileName } from "./annotationSpec";

/**
 * Builds the value-line stub for a @MODELFLOW_config annotation, in the exact
 * syntax this filetype requires (see annotation-spec.json's configValueExample
 * for each). Tabstop $1 is reused for the config's "name" attribute AND the
 * script variable name, so editing one updates the other -- for .bat this also
 * structurally prevents the "guard variable doesn't match SET variable"
 * mistake, since both are the same tabstop.
 */
function configValueSnippetLine(ext: string): string {
  switch (ext) {
    case ".r":
      return '${1:param_name} = "${3:default_value}",';
    case ".rmd":
      return '${1:param_name}: "${3:default_value}"';
    case ".gms":
      return '$ SET ${1:param_name} "${3:default_value}"';
    case ".bat":
      return 'IF NOT DEFINED ${1:param_name} SET "${1:param_name}=${3:default_value}"';
    default:
      return "";
  }
}

export function taskAnnotationSnippet(spec: AnnotationSpec, fileName: string): string | undefined {
  const fileSpec = specForFileName(spec, fileName);
  if (!fileSpec) {
    return undefined;
  }
  return `${fileSpec.commentPrefix}@MODELFLOW_task name="\${1:task_name}" module="\${2:module_name}"\n`;
}

export function configAnnotationSnippet(spec: AnnotationSpec, fileName: string): string | undefined {
  const ext = fileName.slice(fileName.lastIndexOf(".")).toLowerCase();
  const fileSpec = specForFileName(spec, fileName);
  if (!fileSpec) {
    return undefined;
  }
  const valueLine = configValueSnippetLine(ext);
  return (
    `${fileSpec.commentPrefix}@MODELFLOW_config name="\${1:param_name}" role="parameter" type="\${2:string}"\n` +
    `${valueLine}\n`
  );
}

export function descriptionBlockSnippet(spec: AnnotationSpec, fileName: string): string | undefined {
  const fileSpec = specForFileName(spec, fileName);
  if (!fileSpec) {
    return undefined;
  }
  const c = fileSpec.commentPrefix;
  return `${c}@MODELFLOW_description_start\n${c} \${1:Description text.}\n${c}@MODELFLOW_description_end\n`;
}
