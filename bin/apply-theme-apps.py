#!/usr/bin/env python3
"""Apply a theme palette to installed desktop applications without replacing app layouts."""
import configparser
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
THEME_ROOT = CONFIG / "hypr" / "themes"

if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--intellij-only"):
    raise SystemExit("Usage: apply-theme-apps.py <theme-name> [--intellij-only]")
name = sys.argv[1]
intellij_only = len(sys.argv) == 3
if name not in {"everforest", "lawson-night", "black-arch", "cyberpunk", "jojo", "jjk", "gruvbox"}:
    raise SystemExit(f"Unknown theme: {name}")
theme = THEME_ROOT / name
palette = json.loads((theme / "app-palette.json").read_text())


def update_helium() -> None:
    """Generate a Chromium theme for Helium from the active desktop palette."""
    profile = CONFIG / "net.imput.helium/Default"
    preferences_path = profile / "Preferences"
    if not profile.is_dir() or not preferences_path.is_file():
        return
    extension_dir = CONFIG / "net.imput.helium/theme-switcher"
    extension_dir.mkdir(parents=True, exist_ok=True)

    def rgb(color: str) -> list[int]:
        value = color.lstrip("#")
        return [int(value[index:index + 2], 16) for index in (0, 2, 4)]

    manifest = {
        "manifest_version": 2,
        "name": "Desktop Theme Follower",
        "version": "1.0.0",
        "theme": {
            "colors": {
                "frame": rgb(palette["bg"]),
                "frame_inactive": rgb(palette["bg"]),
                "background_tab": rgb(palette["surface"]),
                "background_tab_inactive": rgb(palette["bg"]),
                "toolbar": rgb(palette["surface"]),
                "toolbar_text": rgb(palette["fg"]),
                "toolbar_button_icon": rgb(palette["accent2"]),
                "tab_text": rgb(palette["fg"]),
                "tab_background_text": rgb(palette["muted"]),
                "tab_background_text_inactive": rgb(palette["muted"]),
                "bookmark_text": rgb(palette["fg"]),
                "ntp_background": rgb(palette["bg"]),
                "ntp_header": rgb(palette["accent"]),
                "ntp_link": rgb(palette["accent2"]),
                "ntp_text": rgb(palette["fg"]),
                "omnibox_background": rgb(palette["surface2"]),
                "omnibox_text": rgb(palette["fg"]),
                "button_background": rgb(palette["accent"]),
            }
        },
    }
    write_json(extension_dir / "manifest.json", manifest)

    # Route desktop launches through a small wrapper so the theme extension is
    # loaded even when Helium is opened outside the theme switcher.
    launcher = HOME / ".local/bin/helium-themed"
    launcher.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "helium_bin=\"$(command -v helium || true)\"\n"
        "if [[ -z \"$helium_bin\" && -x /opt/helium/helium ]]; then helium_bin=/opt/helium/helium; fi\n"
        "if [[ -z \"$helium_bin\" ]]; then echo \"Helium executable not found\" >&2; exit 127; fi\n"
        "exec \"$helium_bin\" --load-extension=\"$HOME/.config/net.imput.helium/theme-switcher\" \"$@\"\n"
    )
    launcher.chmod(0o755)
    desktop_source = Path("/usr/share/applications/helium.desktop")
    desktop_override = DATA_HOME / "applications/helium.desktop"
    if desktop_source.is_file():
        source = desktop_source.read_text()
        source = source.replace("Exec=helium %U", f"Exec={launcher} %U")
        source = source.replace("Exec=helium --new-window", f"Exec={launcher} --new-window")
        source = source.replace("Exec=helium --incognito", f"Exec={launcher} --incognito")
        source = source.replace("Exec=helium\n", f"Exec={launcher}\n")
        desktop_override.parent.mkdir(parents=True, exist_ok=True)
        temporary_desktop = desktop_override.with_name(desktop_override.name + f".tmp.{os.getpid()}")
        temporary_desktop.write_text(source)
        os.replace(temporary_desktop, desktop_override)

    # Preferences are owned by Chromium while it is running, so restart it
    # cleanly after writing the extension and restore its previous tabs.
    helium_pids = []
    proc_root = Path("/proc")
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            executable = os.readlink(proc / "exe")
            command_line = (proc / "cmdline").read_bytes().decode(errors="replace")
        except (OSError, PermissionError):
            continue
        if Path(executable).name == "helium" and "--type=" not in command_line:
            helium_pids.append(int(proc.name))

    if helium_pids:
        for pid in helium_pids:
            try:
                os.kill(pid, 15)  # SIGTERM lets Chromium save its session cleanly.
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            alive = []
            for pid in helium_pids:
                try:
                    os.kill(pid, 0)
                    alive.append(pid)
                except ProcessLookupError:
                    pass
            if not alive:
                break
            time.sleep(0.25)
        else:
            print("Helium did not close cleanly; its theme was left unchanged.", file=sys.stderr)
            return

    if helium_pids:
        helium_binary = shutil.which("helium") or "/opt/helium/helium"
        try:
            subprocess.Popen(
                [helium_binary, "--load-extension=" + str(extension_dir), "--restore-last-session"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=os.environ.copy(),
            )
        except OSError as error:
            print(f"Helium's color was updated, but it could not be reopened: {error}", file=sys.stderr)
        else:
            print("Helium restarted with the new theme colors and restored tabs.")


def make_intellij_scheme(theme_name: str) -> str:
    """Build a native IntelliJ editor color scheme from one desktop palette."""
    scheme_palette = json.loads((THEME_ROOT / theme_name / "app-palette.json").read_text())
    # Parent the generated scheme on the user's current Islands Dark scheme so
    # language-specific colors and all IDE-supported attributes remain intact.
    colors = {
        "BACKGROUND": scheme_palette["bg"],
        "CARET_COLOR": scheme_palette["accent"],
        "CARET_ROW_COLOR": scheme_palette["surface"],
        "SELECTION_BACKGROUND": scheme_palette["surface2"],
        "SELECTION_FOREGROUND": scheme_palette["fg"],
        "LINE_NUMBERS_COLOR": scheme_palette["muted"],
        "GUTTER_BACKGROUND": scheme_palette["bg"],
        "WHITESPACES": scheme_palette["surface2"],
        "INDENT_GUIDE": scheme_palette["surface2"],
        "RIGHT_MARGIN_COLOR": scheme_palette["surface2"],
        "CONSOLE_BACKGROUND_KEY": scheme_palette["bg"],
        "TEARLINE_COLOR": scheme_palette["surface2"],
    }
    attributes = {
        # IntelliJ's common syntax keys are DEFAULT_* and TEXT. The earlier
        # generic KEYWORD/STRING names were ignored, leaving base colors such
        # as black in otherwise dark schemes.
        "TEXT": (scheme_palette["fg"], scheme_palette["bg"]),
        "DEFAULT_ATTRIBUTE": (scheme_palette["fg"], None),
        "DEFAULT_KEYWORD": (scheme_palette["purple"], None),
        "DEFAULT_STRING": (scheme_palette["green"], None),
        "DEFAULT_NUMBER": (scheme_palette["yellow"], None),
        "DEFAULT_CONSTANT": (scheme_palette["yellow"], None),
        "DEFAULT_LINE_COMMENT": (scheme_palette["muted"], None),
        "DEFAULT_BLOCK_COMMENT": (scheme_palette["muted"], None),
        "DEFAULT_DOC_COMMENT": (scheme_palette["muted"], None),
        "DEFAULT_DOC_COMMENT_TAG_VALUE": (scheme_palette["accent2"], None),
        "DEFAULT_ENTITY": (scheme_palette["accent2"], None),
        "DEFAULT_METADATA": (scheme_palette["purple"], None),
        "DEFAULT_FUNCTION_DECLARATION": (scheme_palette["accent"], None),
        "DEFAULT_FUNCTION_CALL": (scheme_palette["accent"], None),
        "DEFAULT_INSTANCE_FIELD": (scheme_palette["fg"], None),
        "DEFAULT_STATIC_FIELD": (scheme_palette["accent2"], None),
        "DEFAULT_STATIC_METHOD": (scheme_palette["accent"], None),
        "DEFAULT_TAG": (scheme_palette["accent2"], None),
        "DEFAULT_VALID_STRING_ESCAPE": (scheme_palette["accent2"], None),
        "DEFAULT_INVALID_STRING_ESCAPE": (scheme_palette["fg"], scheme_palette["red"]),
        "CUSTOM_KEYWORD1_ATTRIBUTES": (scheme_palette["purple"], None),
        "CUSTOM_NUMBER_ATTRIBUTES": (scheme_palette["yellow"], None),
        "CUSTOM_STRING_ATTRIBUTES": (scheme_palette["green"], None),
        "INSTANCE_FIELD_ATTRIBUTES": (scheme_palette["fg"], None),
        "STATIC_FIELD_ATTRIBUTES": (scheme_palette["accent2"], None),
        "STATIC_METHOD_ATTRIBUTES": (scheme_palette["accent"], None),
        "BAD_CHARACTER": (scheme_palette["fg"], scheme_palette["red"]),
        "ERRORS_ATTRIBUTES": (scheme_palette["red"], None),
        "WARNING_ATTRIBUTES": (scheme_palette["yellow"], None),
        "SEARCH_RESULT": (scheme_palette["fg"], scheme_palette["surface2"]),
        "MATCHED_BRACE": (scheme_palette["accent"], scheme_palette["surface2"]),
        "TODO_DEFAULT": (scheme_palette["yellow"], scheme_palette["surface"]),
    }
    scheme_names = {
        "gruvbox": "Gruvbox Desktop",
        "everforest": "Everforest Desktop",
        "lawson-night": "Lawson Night Desktop",
        "black-arch": "Black Arch Desktop",
        "cyberpunk": "Cyberpunk Desktop",
        "jojo": "JoJo Part 7 Desktop",
        "jjk": "Jujutsu Kaisen Desktop",
    }
    scheme = ET.Element("scheme", {
        "name": scheme_names[name], "version": "142", "parent_scheme": "Islands Dark"
    })
    ET.SubElement(scheme, "metaInfo")
    color_node = ET.SubElement(scheme, "colors")
    for key, value in colors.items():
        ET.SubElement(color_node, "option", {"name": key, "value": value.lstrip("#")})
    attribute_node = ET.SubElement(scheme, "attributes")
    for key, (foreground, background) in attributes.items():
        option = ET.SubElement(attribute_node, "option", {"name": key})
        value = ET.SubElement(option, "value")
        if foreground:
            ET.SubElement(value, "option", {"name": "FOREGROUND", "value": foreground.lstrip("#")})
        if background:
            ET.SubElement(value, "option", {"name": "BACKGROUND", "value": background.lstrip("#")})
    ET.indent(scheme, space="  ")
    return ET.tostring(scheme, encoding="unicode", xml_declaration=True) + "\n"


def update_intellij() -> None:
    """Install and select native UI and editor themes for IntelliJ IDEA."""
    config_root = CONFIG / "JetBrains"
    if not config_root.is_dir():
        return
    theme_specs = {
        "gruvbox": ("Gruvbox Desktop", "dev.hxh.deskthemepalettes.gruvbox"),
        "everforest": ("Everforest Desktop", "dev.hxh.deskthemepalettes.everforest"),
        "lawson-night": ("Lawson Night Desktop", "dev.hxh.deskthemepalettes.lawsonnight"),
        "black-arch": ("Black Arch Desktop", "dev.hxh.deskthemepalettes.blackarch"),
        "cyberpunk": ("Cyberpunk Desktop", "dev.hxh.deskthemepalettes.cyberpunk"),
        "jojo": ("JoJo Part 7 Desktop", "dev.hxh.deskthemepalettes.jojo"),
        "jjk": ("Jujutsu Kaisen Desktop", "dev.hxh.deskthemepalettes.jjk"),
    }
    plugin_xml = ET.Element("idea-plugin")
    ET.SubElement(plugin_xml, "id").text = "dev.hxh.deskthemepalettes"
    ET.SubElement(plugin_xml, "name").text = "Desktop Theme Palettes"
    ET.SubElement(plugin_xml, "version").text = "1.0.0"
    ET.SubElement(plugin_xml, "vendor").text = "hxh"
    ET.SubElement(plugin_xml, "description").text = "Local UI themes synchronized with the desktop theme switcher."
    ET.SubElement(plugin_xml, "depends").text = "com.intellij.modules.platform"
    extensions = ET.SubElement(plugin_xml, "extensions", {"defaultExtensionNs": "com.intellij"})
    resources: dict[str, bytes] = {}
    for theme_name, (display_name, theme_id) in theme_specs.items():
        theme_palette = json.loads((THEME_ROOT / theme_name / "app-palette.json").read_text())
        color_names = {
            "background": theme_palette["bg"],
            "surface": theme_palette["surface"],
            "foreground": theme_palette["fg"],
            "muted": theme_palette["muted"],
            "border": theme_palette["surface2"],
            "accent": theme_palette["accent"],
        }
        theme_json = {
            "name": display_name,
            "author": "hxh",
            "dark": True,
            "editorScheme": f"/{theme_name}.icls",
            "colors": color_names,
            "ui": {
                "*": {
                    "background": "background",
                    "foreground": "foreground",
                    "separatorColor": "border",
                    "borderColor": "border",
                },
                "Panel.background": "background",
                "ToolWindow.background": "background",
                "MainToolbar.background": "background",
                "EditorTabs": {
                    "selectedBackground": "background",
                    "selectedForeground": "foreground",
                    "inactiveBackground": "surface",
                    "inactiveForeground": "muted",
                    "underlineColor": "accent",
                },
                "DefaultTabs": {
                    "selectedBackground": "background",
                    "selectedForeground": "foreground",
                    "inactiveBackground": "surface",
                    "inactiveForeground": "muted",
                    "underlineColor": "accent",
                },
                "PopupMenu.background": "surface",
                "Menu.background": "surface",
                "TextField.background": "surface",
                "Button.background": "surface",
            },
        }
        json_name = f"{theme_name}.theme.json"
        resources[json_name] = (json.dumps(theme_json, indent=2) + "\n").encode()
        resources[f"{theme_name}.icls"] = make_intellij_scheme(theme_name).encode()
        ET.SubElement(extensions, "themeProvider", {"id": theme_id, "path": f"/{json_name}"})
    ET.indent(plugin_xml, space="  ")
    resources["META-INF/plugin.xml"] = ET.tostring(plugin_xml, encoding="utf-8", xml_declaration=True)

    for ide_config in config_root.glob("IntelliJIdea*"):
        if not ide_config.is_dir():
            continue
        # JetBrains separates config files under ~/.config from installed
        # plugins under ~/.local/share on Linux.
        plugin_dir = DATA_HOME / "JetBrains" / ide_config.name / "desktop-theme-palettes/lib"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        plugin_path = plugin_dir / "desktop-theme-palettes.jar"
        temporary_plugin = plugin_path.with_name(plugin_path.name + f".tmp.{os.getpid()}")
        with zipfile.ZipFile(temporary_plugin, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for resource_path, data in resources.items():
                archive.writestr(resource_path, data)
        os.replace(temporary_plugin, plugin_path)

        display_name, theme_id = theme_specs[name]
        scheme_dir = ide_config / "colors"
        scheme_dir.mkdir(parents=True, exist_ok=True)
        scheme_path = scheme_dir / f"{display_name}.icls"
        temporary_scheme = scheme_path.with_name(scheme_path.name + f".tmp.{os.getpid()}")
        temporary_scheme.write_text(resources[f"{name}.icls"].decode())
        os.replace(temporary_scheme, scheme_path)

        options = ide_config / "options/colors.scheme.xml"
        options.parent.mkdir(parents=True, exist_ok=True)
        try:
            root = ET.parse(options).getroot() if options.exists() else ET.Element("application")
        except ET.ParseError:
            # If the settings file is malformed, leave it untouched rather than
            # replacing the user's unrelated IDE options.
            print(f"IntelliJ color scheme installed, but could not parse {options}", file=sys.stderr)
            continue
        component = root.find("component[@name='EditorColorsManagerImpl']")
        if component is None:
            component = ET.SubElement(root, "component", {"name": "EditorColorsManagerImpl"})
        selected = component.find("global_color_scheme")
        if selected is None:
            selected = ET.SubElement(component, "global_color_scheme")
        selected.set("name", display_name)
        ET.indent(root, space="  ")
        temporary_options = options.with_name(options.name + f".tmp.{os.getpid()}")
        ET.ElementTree(root).write(temporary_options, encoding="unicode", xml_declaration=True)
        temporary_options.write_text(temporary_options.read_text() + "\n")
        os.replace(temporary_options, options)

        # Select the matching plugin theme for the complete IDE UI on next
        # launch. JetBrains persists this separately from editor color schemes.
        laf_options = ide_config / "options/laf.xml"
        laf_options.parent.mkdir(parents=True, exist_ok=True)
        try:
            laf_root = ET.parse(laf_options).getroot() if laf_options.exists() else ET.Element("application")
        except ET.ParseError:
            print(f"IntelliJ palette installed, but could not parse {laf_options}", file=sys.stderr)
            continue
        laf_component = laf_root.find("component[@name='LafManager']")
        if laf_component is None:
            laf_component = ET.SubElement(laf_root, "component", {"name": "LafManager"})
        laf_component.set("autodetect", "false")
        laf = laf_component.find("laf")
        if laf is None:
            laf = ET.SubElement(laf_component, "laf")
        laf.set("class-name", "com.intellij.ide.ui.laf.darcula.DarculaLaf")
        laf.set("themeId", theme_id)
        ET.indent(laf_root, space="  ")
        temporary_laf = laf_options.with_name(laf_options.name + f".tmp.{os.getpid()}")
        ET.ElementTree(laf_root).write(temporary_laf, encoding="unicode", xml_declaration=True)
        temporary_laf.write_text(temporary_laf.read_text() + "\n")
        os.replace(temporary_laf, laf_options)

        # Keep the saved tool-window arrangement aligned across IntelliJ
        # projects. Project files remain untouched; the layout is IDE-wide.
        layouts_path = ide_config / "options/window.layouts.xml"
        if layouts_path.exists():
            try:
                layouts_root = ET.parse(layouts_path).getroot()
                layouts_component = layouts_root.find("component[@name='ToolWindowLayout']")
                if layouts_component is not None and layouts_component.text:
                    layout_data = json.loads(layouts_component.text)
                    for layout in layout_data.get("layouts", {}).values():
                        for window in layout.get("v2", []):
                            if window.get("id") == "Project":
                                window["anchor"] = "RIGHT"
                    layouts_component.text = "\n" + json.dumps(layout_data, indent=2) + "\n"
                    ET.indent(layouts_root, space="  ")
                    temporary_layouts = layouts_path.with_name(layouts_path.name + f".tmp.{os.getpid()}")
                    ET.ElementTree(layouts_root).write(temporary_layouts, encoding="unicode", xml_declaration=True)
                    temporary_layouts.write_text(temporary_layouts.read_text() + "\n")
                    os.replace(temporary_layouts, layouts_path)
            except (ET.ParseError, json.JSONDecodeError):
                print(f"Could not update IntelliJ's global Project tool-window layout in {layouts_path}", file=sys.stderr)


update_intellij()
if intellij_only:
    raise SystemExit(0)


def atomic_link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    temp = link.with_name(link.name + f".new.{os.getpid()}")
    try:
        temp.unlink(missing_ok=True)
        temp.symlink_to(target)
        os.replace(temp, link)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    source = path.read_text()
    # App settings commonly use JSONC. Strip comments and trailing commas while
    # respecting quoted strings, then parse as JSON.
    output = []
    i = 0
    quoted = False
    escaped = False
    while i < len(source):
        ch = source[i]
        if quoted:
            output.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            i += 1
            continue
        if ch == '"':
            quoted = True
            output.append(ch)
            i += 1
        elif source.startswith("//", i):
            end = source.find("\n", i)
            i = len(source) if end == -1 else end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = len(source) if end == -1 else end + 2
        elif ch == ",":
            next_nonspace = i + 1
            while next_nonspace < len(source) and source[next_nonspace].isspace():
                next_nonspace += 1
            if next_nonspace >= len(source) or source[next_nonspace] not in "]}":
                output.append(ch)
            i += 1
        else:
            output.append(ch)
            i += 1
    return json.loads("".join(output))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


update_helium()


def update_spotify() -> None:
    """Keep the existing Spicetify layout and switch only its color palette."""
    spicetify_dir = CONFIG / "spicetify"
    config_path = spicetify_dir / "config-xpui.ini"
    colors_path = spicetify_dir / "Themes/Everforestify/color.ini"
    executable = HOME / ".spicetify/spicetify"
    if not (config_path.is_file() and colors_path.is_file() and executable.is_file()):
        return

    scheme_names = {
        "gruvbox": "Gruvbox",
        "everforest": "Everforest",
        "lawson-night": "LawsonNight",
        "black-arch": "BlackArch",
        "cyberpunk": "Cyberpunk",
        "jojo": "JoJoPart7",
        "jjk": "JujutsuKaisen",
    }
    scheme = scheme_names[name]
    color = lambda key: palette[key].lstrip("#")
    values = {
        "text": color("fg"), "subtext": color("muted"),
        "button-text": color("bg"), "subbutton-text": color("fg"),
        "main": color("bg"), "sidebar": color("bg"), "player": color("surface"),
        "card": color("surface"), "shadow": color("bg"),
        "selected-row": color("surface2"), "sub-button": color("surface"),
        "button": color("accent"), "button-active": color("accent2"),
        "button-disabled": color("muted"), "sidebar-button": color("accent"),
        "play-button": color("accent"), "tab-active": color("surface2"),
        "notification": color("surface"), "notification-error": color("red"),
        "playback-bar": color("accent"), "misc": color("muted"),
    }
    colors = configparser.ConfigParser(interpolation=None)
    colors.optionxform = str
    colors.read(colors_path)
    if not colors.has_section(scheme):
        colors.add_section(scheme)
    for key, value in values.items():
        colors.set(scheme, key, value)
    with colors_path.open("w") as stream:
        colors.write(stream, space_around_delimiters=False)

    settings = configparser.ConfigParser(interpolation=None)
    settings.read(config_path)
    if not settings.has_section("Setting"):
        settings.add_section("Setting")
    settings.set("Setting", "current_theme", "Everforestify")
    settings.set("Setting", "color_scheme", scheme)
    with config_path.open("w") as stream:
        settings.write(stream, space_around_delimiters=False)

    result = subprocess.run([str(executable), "apply"], text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        print(f"Spotify palette saved as {scheme}, but Spicetify apply failed: {detail}", file=sys.stderr)

# VS Code: merge palette customizations while keeping its extensions and preferences.
code_settings = CONFIG / "Code/User/settings.json"
if code_settings.exists():
    settings = read_json(code_settings)
    # Remove the transparent workbench colors Vibrancy Continued left behind.
    # Transparency now comes from Hyprland's native window opacity/blur rule.
    vibrancy_colors = {
        "editorPane.background", "editorGroupHeader.noTabsBackground", "breadcrumb.background",
        "editorGutter.background", "tab.unfocusedActiveBackground", "sideBarTitle.background",
        "tab.unfocusedInactiveBackground", "editorStickyScroll.background",
        "editorStickyScrollGutter.background", "sideBarStickyScroll.background",
        "panelStickyScroll.background", "terminalStickyScroll.background", "minimap.background",
        "inlineChat.background", "editorHoverWidget.background", "editorSuggestWidget.background",
        "notifications.background", "notificationCenterHeader.background", "menu.background",
        "quickInput.background", "editor.lineHighlightBorder",
    }
    customizations = settings.get("workbench.colorCustomizations", {})
    for key in vibrancy_colors:
        customizations.pop(key, None)
    # These guide colors are owned by the desktop theme palette. Remove old
    # levels first so switching palettes cannot leave colors from a prior theme.
    for family in ("editorIndentGuide", "editorBracketPairGuide"):
        for depth in range(1, 5):
            customizations.pop(f"{family}.background{depth}", None)
            customizations.pop(f"{family}.activeBackground{depth}", None)
    overrides = json.loads((theme / "vscode.json").read_text())
    customizations.update(overrides["workbench.colorCustomizations"])
    settings["workbench.colorCustomizations"] = customizations
    current_tokens = settings.setdefault("editor.tokenColorCustomizations", {})
    for key, value in overrides["editor.tokenColorCustomizations"].items():
        current_tokens[key] = value
    write_json(code_settings, settings)

# Zed: use its native theme_overrides, retaining the selected theme and all other settings.
zed_settings_path = CONFIG / "zed/settings.json"
if zed_settings_path.exists():
    zed_settings = read_json(zed_settings_path)
    selected = zed_settings.get("theme", {}).get("dark") if isinstance(zed_settings.get("theme"), dict) else None
    if selected:
        zed_settings.setdefault("theme_overrides", {})[selected] = json.loads((theme / "zed.json").read_text())
        write_json(zed_settings_path, zed_settings)

# Firefox: apply browser-chrome CSS to the selected profile; web pages are untouched.
firefox_root = CONFIG / "mozilla/firefox"
profiles_ini = firefox_root / "profiles.ini"
if profiles_ini.exists():
    parser = configparser.ConfigParser()
    parser.read(profiles_ini)
    selected_profile = None
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            selected_profile = parser.get(section, "Default")
            break
    if not selected_profile:
        for section in parser.sections():
            if section.startswith("Profile") and parser.get(section, "Default", fallback="0") == "1":
                selected_profile = parser.get(section, "Path", fallback=None)
                break
    if selected_profile:
        profile = Path(selected_profile)
        if not profile.is_absolute():
            profile = firefox_root / profile
        chrome = profile / "chrome"
        atomic_link(theme / "firefox.css", chrome / "userChrome.css")
        user_js = profile / "user.js"
        contents = user_js.read_text() if user_js.exists() else ""
        pref = 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
        if "toolkit.legacyUserProfileCustomizations.stylesheets" not in contents:
            with user_js.open("a") as stream:
                if contents and not contents.endswith("\n"):
                    stream.write("\n")
                stream.write(pref + "\n")
        # Firefox reads userChrome.css when the profile starts. Updating the
        # symlink cannot restyle an already-running browser, so report the
        # restart requirement instead of silently implying it was live-applied.
        if shutil.which("pgrep") and subprocess.run(
            ["pgrep", "-x", "firefox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0:
            print("Firefox browser colors are staged; restart Firefox to load the new userChrome.css.", file=sys.stderr)

# Obsidian: add/enable one CSS snippet in each registered local vault.
obsidian_config = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
flatpak_registry = HOME / ".var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json"
registries = [flatpak_registry, CONFIG / "obsidian/obsidian.json"]
vaults = set()
for registry in registries:
    if registry.exists():
        try:
            data = read_json(registry)
            vaults.update(Path(item["path"]) for item in data.get("vaults", {}).values() if item.get("path"))
        except (OSError, ValueError, KeyError):
            pass
# Keep currently opened vault discoverable even if Obsidian has not written its registry yet.
if (HOME / "Desktop/obs/.obsidian").is_dir():
    vaults.add(HOME / "Desktop/obs")
for vault in vaults:
    obsidian_dir = vault / ".obsidian"
    if not obsidian_dir.is_dir():
        continue
    snippet_dir = obsidian_dir / "snippets"
    snippet_dir.mkdir(parents=True, exist_ok=True)
    # Copy atomically so Obsidian's snippet watcher sees a content update.
    target = snippet_dir / "theme-switcher.css"
    tmp = target.with_name(target.name + f".tmp.{os.getpid()}")
    shutil.copyfile(theme / "obsidian.css", tmp)
    os.replace(tmp, target)
    appearance_path = obsidian_dir / "appearance.json"
    appearance = read_json(appearance_path)
    enabled = appearance.setdefault("enabledCssSnippets", [])
    if "theme-switcher" not in enabled:
        enabled.append("theme-switcher")
    write_json(appearance_path, appearance)

# Neovim reads the active palette on its next start; its config preserves all plugin choices.
atomic_link(theme / "nvim.lua", CONFIG / "hypr/theme-active-nvim.lua")

# Spotify keeps its existing Spicetify theme and layout; only the selected colors change.
update_spotify()
