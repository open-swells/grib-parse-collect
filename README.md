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
