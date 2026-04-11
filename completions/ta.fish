#!/usr/bin/env fish
# ta — textaccounts wrapper for fish shell
# Provides the `ta` function and completions for textaccounts CLI

# Main ta function: wraps textaccounts and evals switch output
function ta --description "textaccounts shorthand"
    if test (count $argv) -ge 1; and test "$argv[1]" = "switch"
        eval (textaccounts switch $argv[2..-1])
    else
        textaccounts $argv
    end
end

# Load profile names from ~/.textaccounts/profiles.yaml for completions
function __ta_profiles
    if test -f ~/.textaccounts/profiles.yaml
        # Parse YAML to extract profile names (keys under "profiles:")
        # Simple grep-based extraction: look for "  <name>:" (indented 2 spaces)
        grep -E '^\s{2}[a-zA-Z0-9_-]+:' ~/.textaccounts/profiles.yaml | sed 's/^[[:space:]]*//; s/:.*$//' 2>/dev/null
    end
end

# Completions for ta/textaccounts main commands
complete -c ta -f -n "__fish_use_subcommand_from_list" -s h -l help -d "Show help"
complete -c ta -f -n "__fish_use_subcommand_from_list" -a "adopt" -d "Register existing dir as profile"
complete -c ta -f -n "__fish_use_subcommand_from_list" -a "create" -d "Snapshot current config dir"
complete -c ta -f -n "__fish_use_subcommand_from_list" -a "list" -d "Show all profiles"
complete -c ta -f -n "__fish_use_subcommand_from_list" -a "switch" -d "Switch to a profile"
complete -c ta -f -n "__fish_use_subcommand_from_list" -a "status" -d "Show active profile info"

# Completions for adopt command (needs name and path)
complete -c ta -n "__fish_seen_subcommand_from adopt" -f -a "(__ta_profiles)" -d "Profile name"

# Completions for create command (optional flags: --worker, --from)
complete -c ta -n "__fish_seen_subcommand_from create" -f
complete -c ta -n "__fish_seen_subcommand_from create" -l worker -d "Create worker profile (auth-only)"
complete -c ta -n "__fish_seen_subcommand_from create" -l from -d "Parent profile for worker copy"

# Completions for switch command (profile names)
complete -c ta -n "__fish_seen_subcommand_from switch" -f -a "(__ta_profiles)" -d "Profile name"

# textaccounts command (full name, for power users)
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -s h -l help -d "Show help"
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -a "adopt" -d "Register existing dir as profile"
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -a "create" -d "Snapshot current config dir"
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -a "list" -d "Show all profiles"
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -a "switch" -d "Switch to a profile"
complete -c textaccounts -f -n "__fish_use_subcommand_from_list" -a "status" -d "Show active profile info"

complete -c textaccounts -n "__fish_seen_subcommand_from adopt" -f -a "(__ta_profiles)" -d "Profile name"
complete -c textaccounts -n "__fish_seen_subcommand_from create" -f
complete -c textaccounts -n "__fish_seen_subcommand_from create" -l worker -d "Create worker profile (auth-only)"
complete -c textaccounts -n "__fish_seen_subcommand_from create" -l from -d "Parent profile for worker copy"
complete -c textaccounts -n "__fish_seen_subcommand_from switch" -f -a "(__ta_profiles)" -d "Profile name"
