# Domain navigation + git shortcuts (stowed to ~/.bash_aliases).
# Most distro .bashrc files already source ~/.bash_aliases; if yours doesn't,
# add:  [ -f ~/.bash_aliases ] && . ~/.bash_aliases

# Jump to each domain root. Rename to match your DOMAINS in setup.sh.
alias work='cd ~/work'
alias personal='cd ~/personal'

# Launch Claude Code from a domain root (inherits Layer 0 + that domain's Layer 1).
alias cwork='cd ~/work && claude'
alias cpersonal='cd ~/personal && claude'

# Everyday git.
alias gs='git status'
alias gd='git diff'
alias gl='git log --oneline -20'
