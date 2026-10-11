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

-- How a lower rate is made from the panel's own mode. Panels differ in what they take (wrong
-- colours, a shifted picture ...), so it's a choice: Settings -> Display writes its name to
-- ~/.config/gamingcrypt/panel-timing (read when gamescope starts).
--   front: more blank lines after the picture, before the sync pulse (the pixel clock stays)
--   back:  more blank lines after the sync pulse, before the picture
--   sync:  a longer sync pulse
--   line:  longer lines (more blank pixels after each one)
--   clock: a slower pixel clock, everything else as it is
local TIMINGS = { front = true, back = true, sync = true, line = true, clock = true }

local function chosen_timing()
    local ok, name = pcall(function()
        local folder = os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config")
        local file = io.open(folder .. "/gamingcrypt/panel-timing", "r")
        if not file then
            return nil
        end
        local text = file:read("*l")
        file:close()
        return text and text:match("^%s*(%a+)%s*$")
    end)
    if ok and name and TIMINGS[name] then
        return name
    end
    return "front"
end

local function lower_rate(base_mode, refresh, timing)
    local mode = base_mode
    if refresh >= mode.vrefresh then
        return mode -- the panel's own rate (or above it): as it is
    end
    if timing == "clock" then
        mode.clock = gamescope.modegen.calc_max_clock(mode, refresh)
    elseif timing == "line" then
        local width = math.floor((mode.clock * 1000) / (mode.vtotal * refresh) + 0.5)
        local more = width - mode.htotal
        mode.hsync_start = mode.hsync_start + more
        mode.hsync_end = mode.hsync_end + more
        mode.htotal = mode.htotal + more
    else
        local lines = math.floor((mode.clock * 1000) / (mode.htotal * refresh) + 0.5)
        local more = lines - mode.vtotal
        if timing == "back" then
            mode.vtotal = mode.vtotal + more
        elseif timing == "sync" then
            mode.vsync_end = mode.vsync_end + more
            mode.vtotal = mode.vtotal + more
        else
            gamescope.modegen.adjust_front_porch(mode, (mode.vsync_start - mode.vdisplay) + more)
        end
    end
    mode.vrefresh = gamescope.modegen.calc_vrefresh(mode)
    return mode
end

local timing = chosen_timing()

-- AYANEO 2021 / 2021 Pro: 800 x 1280 LCD, 60 Hz
gamescope.config.known_displays.gamingcrypt_ayaneo_2021_lcd = {
    pretty_name = "AYANEO 2021 LCD",
    dynamic_refresh_rates = rates(40, 60),
    dynamic_modegen = function(base_mode, refresh)
        debug("[gamingcrypt] "..refresh.." Hz for the AYANEO 2021 LCD ("..timing..")")
        return lower_rate(base_mode, refresh, timing)
    end,
    matches = function(display)
        if display.vendor == "UGD" and display.product == 0x1003 then
            debug("[gamingcrypt] matched the AYANEO 2021 LCD")
            return 4000
        end
        return -1
    end
}
