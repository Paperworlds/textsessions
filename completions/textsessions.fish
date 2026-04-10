# Fish shell completions for textsessions
# Install: cp completions/textsessions.fish ~/.config/fish/completions/

set -l __ts_repos (textsessions sessions --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    repos = sorted(set(s.get('repo','') for s in data if s.get('repo')))
    print('\n'.join(repos))
except: pass
" 2>/dev/null)

# Top-level commands
complete -c textsessions -f -n "__fish_use_subcommand" -a "init"          -d "Initialize configuration"
complete -c textsessions -f -n "__fish_use_subcommand" -a "scan"           -d "Scan for sessions"
complete -c textsessions -f -n "__fish_use_subcommand" -a "scan-ghosts"    -d "Scan for ghost/orphan sessions"
complete -c textsessions -f -n "__fish_use_subcommand" -a "sessions"       -d "List sessions"
complete -c textsessions -f -n "__fish_use_subcommand" -a "reindex"        -d "Rebuild session indexes"
complete -c textsessions -f -n "__fish_use_subcommand" -a "index"          -d "Build and mutate session indexes"
complete -c textsessions -f -n "__fish_use_subcommand" -a "proxy"          -d "Show proxy stats"
complete -c textsessions -f -n "__fish_use_subcommand" -a "config"         -d "Show config"
complete -c textsessions -f -n "__fish_use_subcommand" -a "profile"        -d "Manage profiles"
complete -c textsessions -f -n "__fish_use_subcommand" -a "tree"           -d "Dump repos and sessions as YAML/JSON tree"

# reindex flags
complete -c textsessions -n "__fish_seen_subcommand_from reindex" -l repo -d "Limit to repo" -xa "(textsessions sessions --json 2>/dev/null | python3 -c \"import sys,json; [print(s.get('repo','')) for s in json.load(sys.stdin) if s.get('repo')]\" 2>/dev/null | sort -u)"

# index subcommands
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "auto-rename" -d "Rename hex-ID sessions using their slug"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "build"       -d "Rebuild YAML index"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "delete"      -d "Remove a session"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "priority"    -d "Set session priority"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "rename"      -d "Rename a session"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "tag"         -d "Add tags to a session"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "tags"        -d "List all tags"
complete -c textsessions -f -n "__fish_seen_subcommand_from index; and not __fish_seen_subcommand_from auto-rename build delete priority rename tag tags untag" -a "untag"       -d "Remove tags from a session"

# scan-ghosts flags
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l repo    -d "Limit to repo" -xa "data mono personal textlives textworld"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l archive -d "Tag as archived (reversible)"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l discard -d "Archive all orphans without prompt"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l keep    -d "Tag one session as keep" -r
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l keep-all -d "Tag all orphans in repo as keep"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l delete  -d "Hard delete (irreversible)"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l yes     -d "Skip confirmation"
complete -c textsessions -n "__fish_seen_subcommand_from scan-ghosts" -l json    -d "Machine-readable output"

# sessions flags
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l repo     -d "Filter by repo"  -xa "data mono personal textlives textworld"
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l tag      -d "Filter by tag"   -r
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l profile  -d "Filter by profile" -xa "default work personal"
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l priority -d "Sort by priority"
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l limit    -d "Max results" -r
complete -c textsessions -n "__fish_seen_subcommand_from sessions" -l resume   -d "Resume session by name" -xa "(textsessions sessions --names-only --limit 200 2>/dev/null)"

# tree flags
complete -c textsessions -n "__fish_seen_subcommand_from tree" -s o -l output          -d "Output file" -r
complete -c textsessions -n "__fish_seen_subcommand_from tree" -l repo                  -d "Filter to repo label" -r
complete -c textsessions -n "__fish_seen_subcommand_from tree" -l format                -d "Output format" -xa "yaml json"
complete -c textsessions -n "__fish_seen_subcommand_from tree" -l include-archived      -d "Include archived sessions"

# index auto-rename flags
complete -c textsessions -n "__fish_seen_subcommand_from index; and __fish_seen_subcommand_from auto-rename" -l dry-run -d "Preview without applying"
