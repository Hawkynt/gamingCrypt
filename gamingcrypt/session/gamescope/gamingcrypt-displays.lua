-- GamingCrypt: refresh rates for handheld panels gamescope has no profile for, so the
-- screen can follow a game's frame rate (a 50 Hz PAL game on a 60 Hz screen stutters:
-- every fifth frame is shown twice). Copied to ~/.config/gamescope/scripts by install.sh.

local function rates(low, high)
    local list = {}
    for hz = low, high do
        table.insert(list, hz)
    end
    return list
end

-- The panel's own mode with a longer pause between two pictures (more lines after the last
-- visible one), so fewer pictures fit in a second. The pixel clock stays as it is: with a slower
-- clock (the other way to a lower rate) this panel showed wrong, shifting colours.
local function longer_blank(base_mode, refresh)
    local mode = base_mode
    local lines = math.floor((mode.clock * 1000) / (mode.htotal * refresh) + 0.5)
    if lines <= mode.vtotal then
        return mode -- the panel's own rate (or above it): as it is
    end
    local front_porch = mode.vsync_start - mode.vdisplay
    gamescope.modegen.adjust_front_porch(mode, front_porch + (lines - mode.vtotal))
    mode.vrefresh = gamescope.modegen.calc_vrefresh(mode)
    return mode
end

-- AYANEO 2021 / 2021 Pro: 800 x 1280 LCD, 60 Hz
gamescope.config.known_displays.gamingcrypt_ayaneo_2021_lcd = {
    pretty_name = "AYANEO 2021 LCD",
    dynamic_refresh_rates = rates(40, 60),
    dynamic_modegen = function(base_mode, refresh)
        debug("[gamingcrypt] "..refresh.." Hz for the AYANEO 2021 LCD")
        return longer_blank(base_mode, refresh)
    end,
    matches = function(display)
        if display.vendor == "UGD" and display.product == 0x1003 then
            debug("[gamingcrypt] matched the AYANEO 2021 LCD")
            return 4000
        end
        return -1
    end
}
