# Prints one JSON object describing an .rds file's top-level object: its
# full R class chain, plus structural detail for data.frame/data.table (and,
# layered on that, sf) objects, matrix/array objects, and plain lists. Any
# other class still reports its class chain, just with no further detail --
# see classes/RdsInspector.py, which invokes this via Rscript and consumes
# its stdout.
#
# class() is used rather than a reimplemented RDS parser specifically because
# it's authoritative for any object R itself can deserialize -- no per-class
# special-casing needed to get a correct class name.

if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("The 'jsonlite' R package is required for RDS inspection (install.packages('jsonlite')).")
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
    stop("Usage: Rscript inspect_rds.R <path-to-rds-file>")
}

obj <- readRDS(args[[1]])
classes <- class(obj)

result <- list(
    classes = as.list(classes),
    primary_class = classes[[1]],
    detail = NULL
)

if (inherits(obj, "data.frame")) {
    column_classes <- vapply(obj, function(col) class(col)[[1]], character(1))
    detail <- list(
        kind = "data_frame",
        rows = nrow(obj),
        columns = ncol(obj),
        column_names = as.list(names(obj)),
        column_classes = as.list(unname(column_classes))
    )

    if (inherits(obj, "sf")) {
        detail$sf <- tryCatch(
            {
                geometry_column <- attr(obj, "sf_column")
                crs <- sf::st_crs(obj)$input
                geometry_types <- as.character(unique(sf::st_geometry_type(obj)))
                list(
                    geometry_column = if (is.null(geometry_column)) NA else geometry_column,
                    crs = if (is.null(crs)) NA else crs,
                    geometry_types = as.list(geometry_types)
                )
            },
            error = function(e) NULL
        )
    }

    result$detail <- detail
} else if (inherits(obj, "matrix") || inherits(obj, "array")) {
    result$detail <- list(
        kind = "matrix",
        dim = as.list(dim(obj)),
        type = typeof(obj)
    )
} else if (is.list(obj)) {
    element_classes <- vapply(obj, function(el) class(el)[[1]], character(1))
    obj_names <- names(obj)
    result$detail <- list(
        kind = "list",
        length = length(obj),
        names = if (is.null(obj_names)) NULL else as.list(obj_names),
        element_classes = as.list(unname(element_classes))
    )
}

cat(jsonlite::toJSON(result, auto_unbox = TRUE, null = "null"))
