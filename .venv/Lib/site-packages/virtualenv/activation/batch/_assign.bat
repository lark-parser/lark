:assign
@REM Delayed expansion reads inherited values after cmd parses operators and quotes.
@if "!!"=="" goto assign_delayed
@setlocal EnableDelayedExpansion
@for /f "delims=" %%v in ("%1=!%2!!%3!") do @endlocal & @set "%%v" & @exit /b
:assign_delayed
@set "%1=!%2!!%3!"
@exit /b
