-- cyberpunk theme visual settings. Loaded by ~/.config/hypr/hyprland.lua.
hl.config({
    general = {
        gaps_in = 5,
        gaps_out = 6,
        border_size = 2,
        col = {
            active_border = { colors = { "rgba(ff3b81ee)", "rgba(00e5ffee)" }, angle = 45 },
            inactive_border = "rgba(414958ee)",
        },
    },
    decoration = {
        rounding = 10,
        rounding_power = 2,
        active_opacity = 1.0,
        inactive_opacity = 1.0,
        shadow = { enabled = true, range = 4, render_power = 3, color = 0xee1a1a1a },
        blur = { enabled = true, size = 5, passes = 2, new_optimizations = true },
    },
})
