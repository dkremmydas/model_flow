# A simple R script for testing purposes

#@IFMCAP_task name="1_test_R" module="test"

#@IFMCAP_config name="external_parameter" type="number" role="config_var"
ext_par = 5

- @IFMCAP_config: A configuration variable (e.g. an input file, output file or another config variable). The next line will have the default value in the file
  - Explicit attributes:
    - name: the name of the variable
    - type: {number, string}
    - role: {input_file, output_file, config_var}
    - relative: {0,1} Relative to the DatabaseDirectory? 1=yes and 0=no; default is 1
  - Implicit attributes:
    - script_name: the name as defined in the script
    - script_value: the value that exist in the script



# Define a vector of numbers
numbers <- c(1, 2, 3, 4, 5)

# Perform basic operations
sum_numbers <- sum(numbers)  + ext_par    # Calculate the sum of the numbers
mean_numbers <- mean(numbers)    # Calculate the mean of the numbers

# Print the results
cat("Sum of numbers:", sum_numbers, "\n")
cat("Mean of numbers:", mean_numbers, "\n")

# Define a simple function
square_function <- function(x) {
  return(x^2)
}

# Apply the function to the numbers
squared_numbers <- square_function(numbers)

# Print the squared numbers
cat("Squared numbers:", squared_numbers, "\n")

# Plot the original numbers and their squares
plot(numbers, squared_numbers, type = "b", col = "blue",
     main = "Original Numbers and Their Squares",
     xlab = "Original Numbers", ylab = "Squared Numbers")

# Add a grid to the plot
grid()
