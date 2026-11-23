# Sourced by the deactivate alias in activate.csh. Do not run it directly.

if ($?_OLD_VIRTUAL_PATH) then
    setenv PATH "$_OLD_VIRTUAL_PATH:q"
    unset _OLD_VIRTUAL_PATH
endif
rehash

# an empty saved value tells us the variable was unset before activation
if ($?_OLD_VIRTUAL_TCL_LIBRARY) then
    if ("$_OLD_VIRTUAL_TCL_LIBRARY:q" == "") then
        unsetenv TCL_LIBRARY
    else
        setenv TCL_LIBRARY "$_OLD_VIRTUAL_TCL_LIBRARY:q"
    endif
    unset _OLD_VIRTUAL_TCL_LIBRARY
endif

if ($?_OLD_VIRTUAL_TK_LIBRARY) then
    if ("$_OLD_VIRTUAL_TK_LIBRARY:q" == "") then
        unsetenv TK_LIBRARY
    else
        setenv TK_LIBRARY "$_OLD_VIRTUAL_TK_LIBRARY:q"
    endif
    unset _OLD_VIRTUAL_TK_LIBRARY
endif

if ($?_OLD_PKG_CONFIG_PATH) then
    if ("$_OLD_PKG_CONFIG_PATH:q" == "") then
        unsetenv PKG_CONFIG_PATH
    else
        setenv PKG_CONFIG_PATH "$_OLD_PKG_CONFIG_PATH:q"
    endif
    unset _OLD_PKG_CONFIG_PATH
endif

if ($?_OLD_VIRTUAL_PYTHONHOME) then
    setenv PYTHONHOME "$_OLD_VIRTUAL_PYTHONHOME:q"
    unset _OLD_VIRTUAL_PYTHONHOME
endif

if ($?_OLD_VIRTUAL_PROMPT) then
    set prompt="$_OLD_VIRTUAL_PROMPT:q"
    unset _OLD_VIRTUAL_PROMPT
endif

unsetenv VIRTUAL_ENV
unsetenv VIRTUAL_ENV_PROMPT
unalias deactivate
unalias pydoc
unset deactivate_script
