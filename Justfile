default:
    @just --list

# Run tests
test:
    uv run pytest -x -q

# Install as editable uv tool (no venv required)
install:
    uv tool install -e . --force

# Build distribution
build:
    uv build

# Launch the TUI
run:
    uv run textsessions

# Scan for ghost/orphan sessions
scan-ghosts repo="":
    uv run textsessions scan-ghosts {{ if repo != "" { "--repo " + repo } else { "" } }}

# Show session list
sessions query="":
    uv run textsessions sessions {{ query }}

# Install shell completions (auto-detects fish/zsh/bash)
install-completions:
    #!/usr/bin/env sh
    shell=$(basename "$SHELL")
    case "$shell" in
        fish)
            dest="$HOME/.config/fish/completions/textsessions.fish"
            cp completions/textsessions.fish "$dest"
            echo "Installed fish completions → $dest"
            ;;
        zsh)
            dest="${ZDOTDIR:-$HOME}/.zsh/completions/_textsessions"
            mkdir -p "$(dirname "$dest")"
            _TEXTSESSIONS_COMPLETE=zsh_source textsessions > "$dest"
            echo "Installed zsh completions → $dest"
            echo "Make sure $(dirname $dest) is in your fpath."
            ;;
        bash)
            dest="$HOME/.bash_completion.d/textsessions"
            mkdir -p "$(dirname "$dest")"
            _TEXTSESSIONS_COMPLETE=bash_source textsessions > "$dest"
            echo "Installed bash completions → $dest"
            ;;
        *)
            echo "Unknown shell: $shell. Supported: fish, zsh, bash."
            exit 1
            ;;
    esac

# Show current version
version:
    @grep '^version' pyproject.toml | head -1
