# A simple R script for testing purposes

# Define a vector of numbers
numbers <- c(1, 2, 3, 4, 5)

# Perform basic operations
sum_numbers <- sum(numbers)      # Calculate the sum of the numbers
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
