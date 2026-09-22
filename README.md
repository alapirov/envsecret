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
| `e` | Edit. The same form, with the group and the name filled in. An empty value field keeps the stored secret |
| `d` | Delete, with a confirmation |
| `/` | Filter by group or name. `esc` clears it |
| `s` | Sort: group and name, then newest first, then oldest first |
| `t` | Colour scheme. The list previews live; enter keeps it, esc puts the old one back |
| `q` | Quit immediately |
| `esc` | Clears an active filter, otherwise asks before quitting |

In a card: `c` copies to the clipboard, `r` hides or shows the value, `e` opens
the edit form for that secret, `esc` goes back. Anything copied is wiped from the clipboard when you quit, so a secret
stops lingering there.

`envsecret --list` prints group, name and date without the TUI, for scripts,
in whichever order is saved.

## Columns

| Column | |
|---|---|
| group | Blank where it repeats the row above, which happens in name order |
| name | Clipped with `…` when the window is too narrow to hold it |
| added | The date the item was created, `DD.MM.YYYY`, in local time |
| value | Always masked here. Open the card to decrypt one |

`s` cycles the order: group and name, newest first, oldest first. The header
marks the column it is keyed to, `▴` ascending and `▾` descending, and the
cursor stays on the secret it was on. The order is saved alongside the theme,
and `--list` follows it.

Sorting runs off the raw keychain stamp rather than the shown date, so the
display format is free. Below 58 columns the date column gives way to the
names.

## Colour schemes

Press `t`. The list behind the panel is repainted in each scheme as you move
through the names, so you are picking from the real thing. Enter keeps the
highlighted one and writes it to `~/.config/envsecret/config`; esc puts back
the one you started with.

| | |
|---|---|
| `default` | Your terminal's own palette, no background painted |
| `norton` | Norton Commander, 1986: cyan on blue, black on cyan bars |
| `flipboard` | Solari split-flap board: matte black, white letters, amber cursor |
| `tokyo-night` | Indigo ground, blue title bar |
| `gruvbox` | Warm greys under a yellow title bar |
| `dracula` | Purple title bar, green values |
| `nord` | Cool greys, frost blue |
| `solarized-dark` | The classic teal-black ground |
| `phosphor` | Green CRT |
| `amber` | The amber tube on the other side of the office |

```sh
envsecret --themes          # list them, marking the saved one
envsecret --theme nord      # run in one without saving it
```

Each theme sets nine roles (body, dim, key, val, warn, head, foot, sel, zebra)
as xterm-256 colours. On a terminal with fewer, every colour is folded down to
the nearest one it does have, so the schemes still work over an 8-colour
`TERM`. Adding one is a ten-line entry in `THEMES`.

## How items are stored

Each secret is a generic password in the login keychain:

| Field | Value |
|---|---|
| Label | `envsecret [group] NAME` |
| Service (`-s`) | `NAME`, the variable name |
| Account (`-a`) | `$USER` |

The date in the `added` column is the keychain's own `cdat`, read from the same
`dump-keychain` pass as the labels. Writing over an item with `-U` bumps `mdat`
and leaves `cdat` alone, so editing a value keeps the date the secret was first
stored. Renaming one stores a new item, and its date starts from there.

**The keychain is the index.** Groups are parsed back out of the labels at call
time, so there is no separate list to keep in sync. Naming a group that does not
exist creates it; a group disappears when its last secret is deleted. In Keychain
Access, search `envsecret` to see them all together.

Names are normalised to `UPPER_SNAKE_CASE`, and a name already in use is refused
so you edit that item instead of shadowing it.

**Editing is a rewrite, because `security` has no attribute editor.** A new value
or a new group updates the item in place, since `-U` matches on account and
service and the group lives in the label. A new name is a different item, so it
is written under the new name first and the old one removed only once the new one
is stored: an interrupted rename leaves the secret intact under its old name. The
value is read back out of the keychain only when the value field is left empty,
which is the one case where changing a group has to decrypt anything.

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

**The tty's flow control is cleared while the TUI runs.** `curses.wrapper` puts
the terminal in cbreak, which leaves `IXON` set, so the line discipline eats `^s`
as XOFF and the form's save key never reaches `getch`. `run` clears `IXON` on the
way in and puts the saved attributes back on the way out.

**Attributes are passed to `addstr`, never left on the window with
`attron`.** A string holding any non-ASCII character goes out through curses'
wide-character path, which ignores the window's colour and falls back to the
background pair. This UI is full of `·`, so with a theme painting a background
every such line came out in the body colours: the title bar and the cursor row
lost their own. An attribute handed to `addstr` is applied to that write and
survives the wide path.

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
