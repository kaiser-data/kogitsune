# bash completion for kogitsune `kit`. Source it, or install via ./install.sh.
#   source /path/to/kogitsune/completions/kit.bash
# Uses the classic COMPREPLY idiom (no mapfile) so it works on bash 3.2+.
_kit() {
  local cur prev cmds kits
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  cmds="ls show save rm measure doctor help"

  if [[ ${COMP_CWORD} -eq 1 ]]; then
    kits="$(kit __kits 2>/dev/null)"
    # shellcheck disable=SC2207  # word-split is intended for completion words
    COMPREPLY=( $(compgen -W "${cmds} ${kits}" -- "${cur}") )
    return
  fi

  case "${prev}" in
    show|rm|measure)
      kits="$(kit __kits 2>/dev/null)"
      # shellcheck disable=SC2207
      COMPREPLY=( $(compgen -W "${kits}" -- "${cur}") )
      return
      ;;
  esac

  # after a kit name: offer launch flags
  # shellcheck disable=SC2207
  COMPREPLY=( $(compgen -W "--dry-run --strict --" -- "${cur}") )
}
complete -F _kit kit
