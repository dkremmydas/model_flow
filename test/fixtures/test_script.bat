@echo off
:: Simple Batch Script Without User Interaction

:: Set variables
set name=John Doe
set number=42

:: Display messages
echo Welcome to the simple batch script!
echo Name: %name%
echo Number: %number%

:: Perform a simple calculation (adding 10 to the number)
set /a new_number=%number%+10
echo The number %number% plus 10 is %new_number%.

:: Check if the number is greater than 50
if %new_number% GTR 50 (
    echo The result, %new_number%, is greater than 50.
) else (
    echo The result, %new_number%, is not greater than 50.
)

:: Write output to a file
echo Name: %name% > output.txt
echo Number: %number% >> output.txt
echo New Number: %new_number% >> output.txt

:: Notify the user
echo All done! Check the output.txt file for details.

:: Pause to keep the console open
pause
