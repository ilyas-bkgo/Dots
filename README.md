# Dots

My Hyprland desktop: a thin Waybar, animated wallpaper transitions, transparent coverflow pickers, and a themed lockscreen.

Seven themes: Everforest, Lawson Night, Black Arch, Cyberpunk, JoJo, Yuta, and Gruvbox. Yuta keeps the internal name `jjk`. Bleach is not included.

## Included

- Hyprland Lua configuration, window animations, keybindings, and theme palettes.
- Original 26px Waybar layout and its network, audio, Bluetooth, display, and power panels.
- Wallpaper and theme pickers rendered over the desktop using GTK 4 layer shell. Arrow keys/A/D or the mouse wheel browse; Enter applies; Escape closes. No footer hints.
- `swww` wallpaper transitions with a `swaybg` fallback, plus persistent wallpaper selection.
- Hyprlock with themed wallpaper, large clock, live seconds, and animated password feedback.
- Kitty, GTK 3/4, Wofi, and application palette templates.
- Current wallpaper collections and per-theme defaults. Lawson Night uses the blue cloud scene; Gruvbox uses `gruvbox1.png`.

## Requirements

This configuration uses **Hyprland's Lua API**, not the older `.conf` format. It was exported from Fedora 44. It assumes an `eDP-1` monitor, US/French AZERTY layouts, systemd user services, and Fedora portal paths; review `config/hypr/hyprland.lua` on another machine.

Install these dependencies through your distribution or their upstream projects:

- Hyprland with Lua configuration support, Hyprlock (tested with 0.9.7), Waybar, Kitty, Wofi.
- Python 3.10+, PyGObject, Pycairo, Pillow; GTK 3/4; `gtk-layer-shell` and **`gtk4-layer-shell`**, including their GObject introspection typelibs.
- [`swww` and `swww-daemon`](https://github.com/LGFae/swww) for animation. `swaybg` is supported as a fallback without transition effects.
- NetworkManager (`nmcli`), BlueZ (`bluetoothctl`), PipeWire/WirePlumber (`wpctl`), `brightnessctl`, `playerctl`, `pactl` (audio panels), `notify-send`.
- `grim`, `slurp`, and `wl-clipboard` for screenshots.
- `xdg-desktop-portal`, the Hyprland portal, GTK portal, and `busctl`.
- Noto Sans, JetBrainsMono Nerd Font, Font Awesome 6 Free/Brands.
- Nautilus, GNOME Calendar, and GNOME Control Center are used by the desktop menu; substitute your preferred applications if needed.

No compiled binaries or user-local shared libraries are committed. Install `gtk4-layer-shell` system-wide on a fresh machine. The picker also supports an existing library and typelibs under `~/.local/lib/desktop-layer-shell`.

## Install

```sh
git clone git@github.com:ilyas-bkgo/Dots.git
cd Dots
python3 install.py --dry-run
python3 install.py --theme lawson-night
```

The installer copies files, creates theme links, and renders `@HOME@` placeholders for the destination account. It saves overwritten files under `~/.local/state/dots-backups/<timestamp>-<pid>/`. It does not install packages, start applications, change the current session, or run the application theme updater. On a disposable destination you can test with `python3 install.py --home /tmp/dots-preview`.

Review monitor, keyboard, portal, and app choices before your next Hyprland login. The default configuration starts Waybar and restores the selected theme at login. Keep only one Waybar startup entry.

The application theme updater writes palettes to supported installed apps (including browser/editor integrations) and may restart Helium to reload its theme. Read `bin/apply-theme-apps.py` before enabling this on a different machine.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Super+W | Wallpaper picker |
| Super+Ctrl+T | Theme picker |
| Super+L | Lock screen |
| Super+Return | Kitty |
| Super+Space | Application launcher |
| Super+K | Keybinding reference |
| Print / Shift+Print | Full-screen / area screenshot |

Theme changes apply to Hyprland, Waybar, lockscreen, Kitty, GTK, Wofi, and supported application palettes. The personal Content Studio recording shortcut was omitted because its external project is not bundled.

## Repository layout

`config/` contains configuration templates; `bin/` contains executable helpers; `wallpapers/` contains image collections; `theme-wallpapers.json` selects the main image for each theme. Runtime files, backups, caches, browser profiles, and credentials are excluded.

Wallpaper credits and links are kept alongside collections where available. Artwork belongs to its respective creators; source metadata is incomplete for manually downloaded images. No blanket license is granted for third-party artwork.

## Prepare a later update

These files are copies: edits in `~/.config` do not automatically change the repository. Copy intended changes back, replace account-specific paths with `@HOME@`, and check the diff before committing.
