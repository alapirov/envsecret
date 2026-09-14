# envsecret

A curses TUI for the secrets in the macOS login keychain, so credentials stay
out of `~/.zshrc` and out of every process's environment.

Python 3 standard library only. One file, nothing to install beyond it.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/alapirov/envsecret/main/envsecret \
  -o ~/.local/bin/envsecret && chmod +x ~/.local/bin/envsecret
```

macOS only: it talks to `/usr/bin/security`.

## Keys

| Key | Does |
|---|---|
| arrows or `j`/`k` | Move |
| `enter` | Open the card, decrypting that one value |
| `a` | Add. A form with a field each for group, name, and value. The value field is masked |
| `d` | Delete, with a confirmation |
| `/` | Filter by group or name. `esc` clears it |
| `q` | Quit immediately |
| `esc` | Clears an active filter, otherwise asks before quitting |

In a card: `c` copies to the clipboard, `r` hides or shows the value, `esc` goes
back. Anything copied is wiped from the clipboard when you quit, so a secret
stops lingering there.

`envsecret --list` prints group and name without the TUI, for scripts.

## How items are stored

Each secret is a generic password in the login keychain:

| Field | Value |
|---|---|
| Label | `envsecret [group] NAME` |
| Service (`-s`) | `NAME`, the variable name |
| Account (`-a`) | `$USER` |

**The keychain is the index.** Groups are parsed back out of the labels at call
time, so there is no separate list to keep in sync. Naming a group that does not
exist creates it; a group disappears when its last secret is deleted. In Keychain
Access, search `envsecret` to see them all together.

Names are normalised to `UPPER_SNAKE_CASE` on add, and an existing name is
refused so you open it instead.

## Design notes

**A value is decrypted only when you open its card.** Listing reads labels via
`security dump-keychain`, which returns metadata alone.

**Values go to `security` on stdin**, never as an argument, so they stay out of
`ps` output and out of `~/.zsh_history`.

**`security` is run detached from the terminal on purpose.** Its `-w` prompt goes
through `readpassphrase()`, which opens `/dev/tty` whenever a controlling
terminal exists and then ignores the pipe, printing `password data for new item:`
straight onto the curses screen and blocking on keystrokes. `start_new_session`
leaves the child with no controlling terminal, so it falls back to stdin. That
argument to `subprocess.run` in `write_value` is load-bearing.

**Bottom-row writes clip to `w - 1`.** curses returns `ERR` for any write that
reaches the terminal's last cell, which takes the whole TUI down. Any new
`addstr` on the last row needs the same clip.

## Shell side

Loading secrets into a shell is separate and lives in
[`alapirov/configs`](https://github.com/alapirov/configs) under `shell/`:
`lssecrets`, `loadgroup NAME`, `loadsecrets VAR...`, and `secret VAR` to print
one value to stdout without exporting it. `shell/restore-keychain.sh` there
repopulates a fresh machine in one pass. They read the same labels, so either
side can be used alone.

## Limitations

**GUI-launched apps see nothing.** Anything started from Spotlight or the Dock
inherits no shell environment.

**The login keychain never re-locks** under the default `no-timeout` setting, so
any process running as you can read any item with no prompt. This protects the
*files* and shrinks how many processes carry credentials in their environment; it
is not a defence against malware already running as your user. For a lock
timeout, move the items to their own keychain:

```sh
security create-keychain secrets.keychain
security set-keychain-settings -l -u -t 900 ~/Library/Keychains/secrets.keychain-db
security list-keychains -d user -s login.keychain-db secrets.keychain-db
```

Reads then prompt once per unlock window. Point `KEYCHAIN` at the top of the
script at that file too: `index()` dumps one named keychain, while reads and
writes go through the search list.

For per-read biometric authorisation and an audit trail, 1Password's `op` CLI is
the stronger option. `envchain` solves the same problem off the shelf, but its
last commit was 2024-04-23 and the PR migrating off Apple's deprecated
`SecKeychain` APIs has sat unmerged since April 2026.
