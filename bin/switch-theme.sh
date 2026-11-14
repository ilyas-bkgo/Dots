#!/usr/bin/env bash
set -euo pipefail

config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
theme_root="$config_home/hypr/themes"
waybar_dir="$config_home/waybar"
wofi_dir="$config_home/wofi"
kitty_dir="$config_home/kitty"
gtk3_dir="$config_home/gtk-3.0"
gtk4_dir="$config_home/gtk-4.0"

atomic_link() {
    local target=$1 link=$2 tmp="${2}.new.$$"
    ln -sfn -- "$target" "$tmp"
    mv -Tf -- "$tmp" "$link"
}

apply_wallpaper() {
    "$HOME/.local/bin/everforest-wallpaper" --apply "$1"
}

startup=false
if [[ "${1:-}" == "--startup" ]]; then
    startup=true
    theme=$(cat "$config_home/hypr/theme-current" 2>/dev/null || true)
    [[ -n "$theme" ]] || theme=everforest
else
    [[ $# -eq 1 ]] || { printf 'Usage: %s <theme-name>\n' "$0" >&2; exit 2; }
    theme=$1
fi

case "$theme" in
    everforest|lawson-night|black-arch|cyberpunk|jojo|jjk|gruvbox) ;;
    *) printf 'Unknown theme: %s (available: everforest, lawson-night, black-arch, cyberpunk, jojo, jjk, gruvbox)\n' "$theme" >&2; exit 2 ;;
esac

dir="$theme_root/$theme"
for file in hyprland.lua hyprlock.conf waybar.css kitty.conf gtk.css gtk4.css; do
    [[ -r "$dir/$file" ]] || { printf 'Missing theme file: %s\n' "$dir/$file" >&2; exit 1; }
done
if [[ -r "$dir/wallpaper.png" ]]; then
    wallpaper="$dir/wallpaper.png"
elif [[ -r "$dir/wallpaper.jpg" ]]; then
    wallpaper="$dir/wallpaper.jpg"
else
    # A deleted main image must not prevent using the remaining collection.
    wallpaper=""
    for candidate in "$HOME/.local/share/wallpapers/$theme/"*.{png,jpg,jpeg,webp,avif}; do
        if [[ -r "$candidate" ]]; then wallpaper=$candidate; break; fi
    done
    if [[ -z "$wallpaper" ]]; then
        printf 'No readable wallpaper for %s\n' "$theme" >&2
        exit 1
    fi
fi

# Keep the selected wallpaper when restoring the same theme after login.
if [[ "$startup" == true && -r "$config_home/hypr/current-wallpaper" ]]; then
    IFS= read -r saved_wallpaper < "$config_home/hypr/current-wallpaper"
    [[ -r "$saved_wallpaper" ]] && wallpaper=$saved_wallpaper
fi

mkdir -p "$waybar_dir" "$wofi_dir" "$kitty_dir" "$gtk3_dir" "$gtk4_dir"
atomic_link "$dir/hyprland.lua" "$config_home/hypr/theme-active.lua"
atomic_link "$dir/hyprlock.conf" "$config_home/hypr/hyprlock.conf"
atomic_link "$dir/waybar.css" "$waybar_dir/theme-colors.css"
atomic_link "$dir/wofi.css" "$wofi_dir/style.css"
atomic_link "$dir/wofi-wallpaper.css" "$wofi_dir/wallpaper.css"
atomic_link "$dir/wofi.css" "$wofi_dir/theme-colors.css"
atomic_link "$dir/kitty.conf" "$kitty_dir/theme.conf"
atomic_link "$dir/gtk.css" "$gtk3_dir/gtk.css"
atomic_link "$dir/gtk4.css" "$gtk4_dir/gtk.css"
if command -v python3 >/dev/null 2>&1; then
    "$HOME/.local/bin/apply-theme-apps.py" "$theme"
fi

# Wallpaper support is optional; a missing compositor helper must not leave only
# part of the app theme applied.
if apply_wallpaper "$wallpaper"; then
    printf '%s\n' "$theme" > "$config_home/hypr/theme-current"
    printf '%s\n' "$wallpaper" > "$config_home/hypr/current-wallpaper"
    atomic_link "$wallpaper" "$config_home/hypr/wallpaper-active"
else
    printf 'Theme files were switched, but the wallpaper was not applied.\n' >&2
    exit 1
fi

if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' || true
    # Use the neutral GTK base theme; the active theme's gtk.css supplies colors.
    gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita' || true
fi
# GTK 4 apps such as Files read this per-user setting directly. Keep both
# GTK generations on Adwaita so the active theme's gtk.css provides the colors.
for settings in "$gtk3_dir/settings.ini" "$gtk4_dir/settings.ini"; do
    if [[ -f "$settings" ]] && grep -q '^gtk-theme-name=' "$settings"; then
        sed -i 's/^gtk-theme-name=.*/gtk-theme-name=Adwaita/' "$settings"
    fi
done

if [[ "$startup" == false ]]; then
    if command -v hyprctl >/dev/null 2>&1 && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
        hyprctl reload
    fi
    if command -v waybar >/dev/null 2>&1; then
        if pgrep -x waybar >/dev/null 2>&1; then
            pkill -USR2 -x waybar 2>/dev/null || true
            # Some Waybar builds crash while rebuilding Hyprland IPC modules.
            # Recover the bar if that reload took its process down.
            sleep 0.5
        fi
        if ! pgrep -x waybar >/dev/null 2>&1; then
            log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/theme-switcher"
            mkdir -p "$log_dir"
            setsid waybar >>"$log_dir/waybar.log" 2>&1 </dev/null &
        fi
    fi
    if pgrep -x kitty >/dev/null 2>&1; then
        pkill -USR1 -x kitty 2>/dev/null || true
    fi
    printf 'Switched to %s.\n' "$theme"
fi
