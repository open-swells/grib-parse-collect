## Systemd process to parse and store grib files

**Start Service**: `sudo systemctl start grib_parse.service`   
**View Logs**: `journalctl -u grib_parse.service `   
**stop service**: sudo systemctl stop grib_parse.service  
**status of service**: systemctl status grib_parse.service  
**Verify timer**:`systemctl list-timers`  
    
**Reload the system and enable the timer (this happens in setup_service.sh)**:  
```
sudo systemctl daemon-reload
sudo systemctl enable my_python_script.timer
sudo systemctl start my_python_script.timer
```

**necessary .env: **
```
SOURCE_PATH=...../grib-parse-collect/files
DEST_PATH=<server>/open-swells-app/static
PYTHON_SCRIPT=....../grib-parse-collect/gfs_to_contours.py
PYTHON_INTERPRETER=...../bin/python3
FILES_DIR=....../grib-parse-collect/files
LOG_DIR=...../grib-parse-collect/logs
SSH_KEY_PATH=/etc/ssh/ssh_host_ed25519_key
```

**Outputs per forecast hour**:
- `heatmap_XXX.png` — continuous-color height field in Web Mercator with
  transparent land; the app's primary swell layer. Corner coordinates are
  published as `heatmap_bounds` in `metadata.json`. Colors come from
  `HEATMAP_COLORS` in `gfs_to_contours.py`, matched by `SWELL_BANDS` in the
  web app's `pages/today.html` — change them together.
- `contours_XXX.geojson` (+`.gz`) — swell height polygons on fixed bands
  (`FIXED_LEVELS`); kept as the app's fallback layer when heatmaps are
  missing.
- `arrows_XXX.geojson` (+`.gz`) — coarse grid of swell direction points
  (properties `h`=height m, `p`=period s, `d`=direction from, deg true);
  also drives the app's hover readout.

See `../webgl-swell-rendering.md` for the possible next step (client-side
WebGL rendering with temporal interpolation).

`run.sh --verbose` draws a live progress bar in the terminal (the log is
unaffected); `--local` copies output to the sibling open-swells-app instead
of the server; `--limit <n>` processes only the first n forecast hours for
quick render checks (don't publish a limited run to the server).

**Optional tuning env vars**:
```
CONTOUR_STRIDE=2               # grid downsampling for contours
CONTOUR_SMOOTHING_SIGMA=1.0    # gaussian smoothing before contouring
CONTOUR_SIMPLIFY_TOLERANCE=    # shapely simplify tolerance (off by default)
ARROW_STRIDE=10                # arrow grid spacing (10 = one per 1.6 deg)
```
