# This file must be used with "source bin/activate.csh" *from csh*.
# You cannot run it directly.
# Created by Davide Di Blasi <davidedb@gmail.com>.

set newline='\
'

# History substitution precedes quote parsing, and the generated literals escape only its default character.
unset _virtualenv_histchars
if ($?histchars) then
    set _virtualenv_histchars="$histchars:q"
    unset histchars
endif

# Undo an activation that is still in effect, otherwise its values get saved as the ones to restore
if ($?_OLD_VIRTUAL_PATH) source __VIRTUAL_ENV__"/"__BIN_NAME__"/deactivate.csh"

set _virtualenv_dir=__VIRTUAL_ENV__
setenv VIRTUAL_ENV "$_virtualenv_dir:q"

set _OLD_VIRTUAL_PATH="$PATH:q"
if ("$PATH:q" == "") then
    setenv PATH "$_virtualenv_dir:q/"__BIN_NAME__
else
    setenv PATH "$_virtualenv_dir:q/"__BIN_NAME__":$PATH:q"
endif

# PYTHONHOME can redirect the standard library lookup away from this environment.
if ($?PYTHONHOME) then
    set _OLD_VIRTUAL_PYTHONHOME="$PYTHONHOME:q"
    unsetenv PYTHONHOME
endif

if ($?PKG_CONFIG_PATH) then
    set _OLD_PKG_CONFIG_PATH="$PKG_CONFIG_PATH"
    setenv PKG_CONFIG_PATH "$_virtualenv_dir:q/lib/pkgconfig:${PKG_CONFIG_PATH}"
else
    set _OLD_PKG_CONFIG_PATH=""
    setenv PKG_CONFIG_PATH "$_virtualenv_dir:q/lib/pkgconfig"
endif

if (__TCL_LIBRARY__ != "") then
    if ($?TCL_LIBRARY) then
        set _OLD_VIRTUAL_TCL_LIBRARY="$TCL_LIBRARY"
    else
        set _OLD_VIRTUAL_TCL_LIBRARY=""
    endif
    setenv TCL_LIBRARY __TCL_LIBRARY__
endif

if (__TK_LIBRARY__ != "") then
    if ($?TK_LIBRARY) then
        set _OLD_VIRTUAL_TK_LIBRARY="$TK_LIBRARY"
    else
        set _OLD_VIRTUAL_TK_LIBRARY=""
    endif
    setenv TK_LIBRARY __TK_LIBRARY__
endif

if (__VIRTUAL_PROMPT__ != "") then
    setenv VIRTUAL_ENV_PROMPT __VIRTUAL_PROMPT__
else
    setenv VIRTUAL_ENV_PROMPT "$_virtualenv_dir:t:q"
endif

if ( $?VIRTUAL_ENV_DISABLE_PROMPT ) then
    if ( $VIRTUAL_ENV_DISABLE_PROMPT == "" ) then
        set do_prompt = "1"
    else
        set do_prompt = "0"
    endif
else
    set do_prompt = "1"
endif

# Skipped branches use a different quote scanner, so assign prompt literals before entering them.
# PATH now starts with the environment's bin directory, so use a system printf for prompt bytes.
set _virtualenv_printf=/usr/bin/printf
if (! -x "$_virtualenv_printf") set _virtualenv_printf=/bin/printf
if (! -x "$_virtualenv_printf") set _virtualenv_printf=/run/current-system/sw/bin/printf
set _virtualenv_prompt_tcsh = __VIRTUAL_PROMPT_DISPLAY_TCSH__
set _virtualenv_prompt_plain = __VIRTUAL_PROMPT_DISPLAY_PLAIN__

if ( $do_prompt == "1" ) then
    # Could be in a non-interactive environment,
    # in which case, $prompt is undefined and we wouldn't
    # care about the prompt anyway.
    if ( $?prompt ) then
        set _OLD_VIRTUAL_PROMPT="$prompt:q"
        if ( "$prompt:q" =~ *"$newline:q"* ) then
            :
        else if ( $?tcsh ) then
            set prompt = __VIRTUAL_PROMPT_PREFIX_TCSH__"$prompt:q"
        else
            set prompt = __VIRTUAL_PROMPT_PREFIX_PLAIN__"$prompt:q"
        endif
    endif
endif

unset env_name
unset do_prompt
unset _virtualenv_dir
unset _virtualenv_prompt_tcsh
unset _virtualenv_prompt_plain
unset _virtualenv_printf

alias pydoc python -m pydoc

# stashed in a variable, not embedded directly in the alias body, because the alias's own single
# quotes cannot nest around a path that itself needed single-quoting
set deactivate_script = __VIRTUAL_ENV__"/"__BIN_NAME__"/deactivate.csh"
alias deactivate 'source "$deactivate_script:q"'

if ($?_virtualenv_histchars) then
    set histchars="$_virtualenv_histchars:q"
    unset _virtualenv_histchars
endif

rehash
