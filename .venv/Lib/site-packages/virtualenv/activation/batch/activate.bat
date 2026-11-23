@REM This file is UTF-8 encoded, so we need to update the current code page while executing it
@for /f "tokens=2 delims=:." %%a in ('"%SystemRoot%\System32\chcp.com"') do @set _OLD_CODEPAGE=%%a

@if defined _OLD_CODEPAGE (
    "%SystemRoot%\System32\chcp.com" 65001 > nul
)

@REM Undo an activation that is still in effect, otherwise its values get saved as the ones to restore
@if defined _OLD_VIRTUAL_PATH @call "__VIRTUAL_ENV_CALL__\__BIN_NAME__\deactivate.bat"
@if defined _OLD_VIRTUAL_PATH_UNSET @call "__VIRTUAL_ENV_CALL__\__BIN_NAME__\deactivate.bat"

@set "VIRTUAL_ENV=__VIRTUAL_ENV__"

@set "VIRTUAL_ENV_PROMPT=__VIRTUAL_PROMPT__"
@if NOT DEFINED VIRTUAL_ENV_PROMPT (
    @for %%d in ("%VIRTUAL_ENV%") do @set "VIRTUAL_ENV_PROMPT=%%~nxd"
)

@if not defined PROMPT @set "PROMPT=$P$G"
@if defined _OLD_VIRTUAL_PROMPT @call :assign PROMPT _OLD_VIRTUAL_PROMPT
@if not defined VIRTUAL_ENV_DISABLE_PROMPT (
    @call :assign _OLD_VIRTUAL_PROMPT PROMPT
    @set "PROMPT=(%VIRTUAL_ENV_PROMPT:$=$$%) "
    @call :assign PROMPT PROMPT _OLD_VIRTUAL_PROMPT
)

@if not defined _OLD_VIRTUAL_PYTHONHOME @call :assign _OLD_VIRTUAL_PYTHONHOME PYTHONHOME
@set PYTHONHOME=

@if defined TCL_LIBRARY @call :assign _OLD_VIRTUAL_TCL_LIBRARY TCL_LIBRARY
@if NOT "__TCL_LIBRARY__"=="" @set "TCL_LIBRARY=__TCL_LIBRARY__"

@if defined TK_LIBRARY @call :assign _OLD_VIRTUAL_TK_LIBRARY TK_LIBRARY
@if NOT "__TK_LIBRARY__"=="" @set "TK_LIBRARY=__TK_LIBRARY__"

@if defined PKG_CONFIG_PATH (
    @call :assign _OLD_PKG_CONFIG_PATH PKG_CONFIG_PATH
    @set "PKG_CONFIG_PATH=%VIRTUAL_ENV%\lib\pkgconfig;"
    @call :assign PKG_CONFIG_PATH PKG_CONFIG_PATH _OLD_PKG_CONFIG_PATH
) else (
    @set "PKG_CONFIG_PATH=%VIRTUAL_ENV%\lib\pkgconfig"
)

@if not defined _OLD_VIRTUAL_PATH (
    @call :assign _OLD_VIRTUAL_PATH PATH
    @if not defined PATH @set _OLD_VIRTUAL_PATH_UNSET=1
)
@set "PATH=%VIRTUAL_ENV%\__BIN_NAME__;"
@call :assign PATH PATH _OLD_VIRTUAL_PATH

@if defined _OLD_CODEPAGE (
    "%SystemRoot%\System32\chcp.com" %_OLD_CODEPAGE% > nul
    @set _OLD_CODEPAGE=
)
@exit /b

__BATCH_ASSIGN__
