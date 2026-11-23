@setlocal DisableDelayedExpansion
@call :bindir
"%_PYDOC_BIN%python.exe" -m pydoc %*
@exit /b %ERRORLEVEL%
:bindir
@set "_PYDOC_BIN=%~dp0"
@exit /b
