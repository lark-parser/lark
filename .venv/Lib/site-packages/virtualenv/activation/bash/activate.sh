# This file must be used with "source bin/activate" *from bash*
# you cannot run it directly


if [ "${BASH_SOURCE-}" = "$0" ]; then
    echo "You must source this script: \$ source $0" >&2
    exit 33
fi

# A new shell can inherit the Windows PATH backup from batch activation.
if [ "$(command -v deactivate)" != deactivate ]; then
    unset _OLD_VIRTUAL_PATH
fi

deactivate () {
    unset -f pydoc >/dev/null 2>&1 || true

    # reset old environment variables
    if [ -n "${_OLD_VIRTUAL_PATH+x}" ] ; then
        PATH="$_OLD_VIRTUAL_PATH"
        export PATH
        unset _OLD_VIRTUAL_PATH
    fi
    if [ -n "${_OLD_VIRTUAL_PYTHONHOME+x}" ] ; then
        PYTHONHOME="$_OLD_VIRTUAL_PYTHONHOME"
        export PYTHONHOME
        unset _OLD_VIRTUAL_PYTHONHOME
    fi

    if [ -n "${_OLD_VIRTUAL_TCL_LIBRARY+x}" ]; then
        if [ -n "$_OLD_VIRTUAL_TCL_LIBRARY" ]; then
            TCL_LIBRARY="$_OLD_VIRTUAL_TCL_LIBRARY"
            export TCL_LIBRARY
        else
            unset TCL_LIBRARY
        fi
        unset _OLD_VIRTUAL_TCL_LIBRARY
    fi
    if [ -n "${_OLD_VIRTUAL_TK_LIBRARY+x}" ]; then
        if [ -n "$_OLD_VIRTUAL_TK_LIBRARY" ]; then
            TK_LIBRARY="$_OLD_VIRTUAL_TK_LIBRARY"
            export TK_LIBRARY
        else
            unset TK_LIBRARY
        fi
        unset _OLD_VIRTUAL_TK_LIBRARY
    fi
    if [ -n "${_OLD_PKG_CONFIG_PATH+x}" ]; then
        if [ -n "$_OLD_PKG_CONFIG_PATH" ]; then
            PKG_CONFIG_PATH="$_OLD_PKG_CONFIG_PATH"
            export PKG_CONFIG_PATH
        else
            unset PKG_CONFIG_PATH
        fi
        unset _OLD_PKG_CONFIG_PATH
    fi

    # The hash command must be called to get it to forget past
    # commands. Without forgetting past commands the $PATH changes
    # we made may not be respected
    hash -r 2>/dev/null || true

    if [ -n "${_OLD_VIRTUAL_PS1+x}" ] ; then
        if [ -n "$_OLD_VIRTUAL_PS1" ] ; then
            PS1="$_OLD_VIRTUAL_PS1"
        else
            unset PS1
        fi
        unset _OLD_VIRTUAL_PS1
    fi

    if [ -n "${_OLD_VIRTUAL_PSVAR+x}" ] ; then
        psvar[9]="$_OLD_VIRTUAL_PSVAR"
        unset _OLD_VIRTUAL_PSVAR
    fi

    unset VIRTUAL_ENV
    unset VIRTUAL_ENV_PROMPT
    if [ ! "${1-}" = "nondestructive" ] ; then
    # Self destruct!
        unset -f deactivate
    fi
}

# unset irrelevant variables
deactivate nondestructive

# Make sure to unalias pydoc if it's already there. This must run before the if block below is parsed: the shell
# expands aliases while parsing, so an alias would turn the pydoc function definition into a syntax error
alias pydoc 2>/dev/null >/dev/null && unalias pydoc || true

if [ ! -d __VIRTUAL_ENV__ ] &&
    { [ -z "${BASH_VERSION-}" ] || [ -z "${BASH_SOURCE-}" ]; }; then
    echo "Relocating this activation script requires sourcing it from bash." >&2
    false
else
    if [ ! -d __VIRTUAL_ENV__ ]; then
        echo "Virtual environment directory" __VIRTUAL_ENV__ "does not exist!" >&2
        CURRENT_PATH=$(realpath "${BASH_SOURCE[0]}") || return 1
        CURRENT_DIR=$(dirname "${CURRENT_PATH}") || return 1
        CURRENT_ENV="$(realpath "${CURRENT_DIR}/../")" || return 1
        if [ ! "$CURRENT_PATH" -ef "$CURRENT_ENV/"__BIN_NAME__"/activate" ] || [ ! -f "$CURRENT_ENV/pyvenv.cfg" ]; then
            echo "Cannot identify relocated environment: $CURRENT_ENV" >&2
            unset CURRENT_ENV
            return 1
        fi
        case "${CURRENT_ENV#*%}" in
            func*|builtin*)
                echo "Virtual environment directory $CURRENT_ENV contains a shell PATH option." >&2
                unset CURRENT_ENV
                return 1
                ;;
        esac
        VIRTUAL_ENV="$CURRENT_ENV"
        unset CURRENT_ENV
    else
        VIRTUAL_ENV=__VIRTUAL_ENV__
    fi

    case "$(uname)" in
        CYGWIN*|MSYS*|MINGW*)
            VIRTUAL_ENV=$(cygpath "$VIRTUAL_ENV")
            ;;
    esac
    # Git Bash realpath can return a Windows drive letter until cygpath converts it.
    case "$VIRTUAL_ENV" in
        *:*)
            echo "Virtual environment directory $VIRTUAL_ENV contains the PATH separator." >&2
            unset VIRTUAL_ENV
            return 1
            ;;
    esac
    export VIRTUAL_ENV

    _OLD_VIRTUAL_PATH="$PATH"
    PATH="$VIRTUAL_ENV/"__BIN_NAME__"${PATH:+:$PATH}"
    export PATH

    _OLD_PKG_CONFIG_PATH="${PKG_CONFIG_PATH:-}"
    PKG_CONFIG_PATH="${VIRTUAL_ENV}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
    export PKG_CONFIG_PATH

    if [ "x"__VIRTUAL_PROMPT__ != x ] ; then
        VIRTUAL_ENV_PROMPT=__VIRTUAL_PROMPT__
    else
        VIRTUAL_ENV_PROMPT=$(basename "$VIRTUAL_ENV")
    fi
    export VIRTUAL_ENV_PROMPT

    # unset PYTHONHOME if set
    if [ -n "${PYTHONHOME+x}" ] ; then
        _OLD_VIRTUAL_PYTHONHOME="$PYTHONHOME"
        unset PYTHONHOME
    fi

    # an empty saved value tells deactivate to unset the variable
    if [ __TCL_LIBRARY__ != "" ]; then
        _OLD_VIRTUAL_TCL_LIBRARY="${TCL_LIBRARY:-}"
        TCL_LIBRARY=__TCL_LIBRARY__
        export TCL_LIBRARY
    fi

    if [ __TK_LIBRARY__ != "" ]; then
        _OLD_VIRTUAL_TK_LIBRARY="${TK_LIBRARY:-}"
        TK_LIBRARY=__TK_LIBRARY__
        export TK_LIBRARY
    fi

    if [ -z "${VIRTUAL_ENV_DISABLE_PROMPT-}" ] &&
        { [ -n "${BASH_VERSION-}" ] || [ -n "${ZSH_VERSION-}" ]; }; then
        _OLD_VIRTUAL_PS1="${PS1-}"
        if [ -n "${BASH_VERSION-}" ]; then
            # Escape both prompt passes even if promptvars changes after activation.
            # A nonprinting marker separates a high byte from the next escape under legacy multibyte locales.
            _virtualenv_escape_prompt () {
                # A read-only LC_ALL pins the shell to its current locale.
                local LC_ALL=C || :
                local _VIRTUAL_INDEX=0 _VIRTUAL_MARK= _VIRTUAL_CHARACTER
                while [ "$_VIRTUAL_INDEX" -lt "${#1}" ]; do
                    _VIRTUAL_CHARACTER=${1:_VIRTUAL_INDEX:1}
                    _VIRTUAL_INDEX=$((_VIRTUAL_INDEX + 1))
                    case $_VIRTUAL_CHARACTER in
                        \\) _VIRTUAL_PROMPT+="$_VIRTUAL_MARK\\\\\\\\" ;;
                        \$ | \`) _VIRTUAL_PROMPT+="$_VIRTUAL_MARK\\$_VIRTUAL_CHARACTER" ;;
                        *) _VIRTUAL_PROMPT+=$_VIRTUAL_CHARACTER ;;
                    esac
                    # $'...' inside a double-quoted ${...} stays literal in posix mode and without extquote
                    case $_VIRTUAL_CHARACTER in
                        [\ -~]) _VIRTUAL_MARK= ;;
                        *) _VIRTUAL_MARK=$'\001\002' ;;
                    esac
                done
            }
            _VIRTUAL_PROMPT=
            # Bash can warn when restoring an unavailable locale on return.
            _virtualenv_escape_prompt "$VIRTUAL_ENV_PROMPT" 2>/dev/null
            unset -f _virtualenv_escape_prompt
        else
            # zsh inserts a psvar entry into the prompt as data under every prompt option, so the value needs no
            # escaping, and the %9v reference holds nothing for another shell to expand when PS1 is exported. The guard
            # above keeps POSIX shells such as dash away from the array assignment
            _OLD_VIRTUAL_PSVAR="${psvar[9]-}"
            psvar[9]="$VIRTUAL_ENV_PROMPT"
            # %Nv counts psvar entries from 1 under every option, but KSH_ARRAYS makes the subscript above count from 0
            if [[ -o ksharrays ]]; then
                _VIRTUAL_PROMPT='%10v'
            else
                _VIRTUAL_PROMPT='%9v'
            fi
        fi
        PS1="${_VIRTUAL_PROMPT:+(${_VIRTUAL_PROMPT}) }${PS1-}"
        unset _VIRTUAL_PROMPT
    fi

    pydoc () {
        python -m pydoc "$@"
    }

    # The hash command must be called to get it to forget past
    # commands. Without forgetting past commands the $PATH changes
    # we made may not be respected
    hash -r 2>/dev/null || true
fi
