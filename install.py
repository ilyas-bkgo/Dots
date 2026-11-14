#!/usr/bin/env python3
"""Install copied dotfiles, render home paths, and back up overwritten files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home(), help='destination home (use a temporary directory to test)')
    parser.add_argument('--theme', default='lawson-night', help='initial theme; jjk is displayed as Yuta')
    parser.add_argument('--dry-run', action='store_true', help='show installation paths without writing files')
    args = parser.parse_args()
    defaults = json.loads((ROOT / 'theme-wallpapers.json').read_text())
    if args.theme not in defaults:
        parser.error('Unknown theme: ' + args.theme)
    home = args.home.expanduser().resolve()
    if str(home) == '/':
        parser.error('--home must be a home directory')
    if home == ROOT or ROOT.is_relative_to(home / '.config'):
        parser.error('destination must not contain the repository under .config')
    backup = home / '.local/state/dots-backups' / f'{time.strftime("%Y%m%d-%H%M%S")}-{os.getpid()}'
    operations = []
    for source_root, dest_root, render in [(ROOT/'config', home/'.config', True), (ROOT/'bin', home/'.local/bin', True), (ROOT/'wallpapers', home/'.local/share/wallpapers', False)]:
        for source in sorted(source_root.rglob('*')):
            if source.is_file():
                operations.append((source, dest_root/source.relative_to(source_root), render))
    # Validate default wallpaper paths before making any changes.
    for relative in defaults.values():
        source = ROOT/'wallpapers'/relative
        if not source.is_file() or not source.resolve().is_relative_to(ROOT/'wallpapers'):
            parser.error('Missing or invalid wallpaper: ' + relative)
    if args.dry_run:
        print(f'Would install {len(operations)} files into {home}')
        print(f'Initial theme: {args.theme}; backups: {backup}')
        return

    def preserve(path):
        # Avoid traversing an existing destination directory symlink.
        for parent in reversed(path.parents):
            if parent == home or not parent.is_relative_to(home):
                continue
            if parent.is_symlink():
                saved = backup/parent.relative_to(home)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(parent), str(saved))
                parent.mkdir()
        if path.is_symlink() or path.exists():
            saved = backup/path.relative_to(home)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(saved))
        path.parent.mkdir(parents=True, exist_ok=True)

    for source, dest, render in operations:
        preserve(dest)
        if render:
            dest.write_text(source.read_text().replace('@HOME@', str(home)))
            shutil.copymode(source, dest)
        else:
            shutil.copy2(source, dest)

    def link(target, dest):
        preserve(dest)
        dest.symlink_to(target)

    for theme, relative in defaults.items():
        # Decoder detects the format; keep the default filename consistent.
        link(home/'.local/share/wallpapers'/relative, home/'.config/hypr/themes'/theme/'wallpaper.png')
    theme_dir = home/'.config/hypr/themes'/args.theme
    links = {
        'hypr/theme-active.lua': 'hyprland.lua',
        'hypr/theme-active-nvim.lua': 'nvim.lua',
        'hypr/hyprlock.conf': 'hyprlock.conf',
        'hypr/wallpaper-active': 'wallpaper.png',
        'waybar/theme-colors.css': 'waybar.css',
        'wofi/style.css': 'wofi.css',
        'wofi/theme-colors.css': 'wofi.css',
        'wofi/wallpaper.css': 'wofi-wallpaper.css',
        'kitty/theme.conf': 'kitty.conf',
        'gtk-3.0/gtk.css': 'gtk.css',
        'gtk-4.0/gtk.css': 'gtk4.css',
    }
    for dest, source in links.items():
        link(theme_dir/source, home/'.config'/dest)
    for dest, value in [('theme-current', args.theme), ('current-wallpaper', str(home/'.local/share/wallpapers'/defaults[args.theme]))]:
        path=home/'.config/hypr'/dest
        preserve(path)
        path.write_text(value+'\n')
    print(f'Installed {len(operations)} files. Initial theme: {args.theme}.')
    print(f'Previous files saved in {backup}')
    print('No applications were restarted. Review monitor/input settings before logging into Hyprland.')


if __name__ == '__main__':
    main()
