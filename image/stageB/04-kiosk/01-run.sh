#!/bin/bash -e
# stageB/04-kiosk/01-run.sh
# Configure pi user autologin and X11 kiosk inside the chroot
on_chroot << EOF

# ---- Autologin: pi user on tty1 ---------------------------------------------
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I \$TERM
AUTOLOGIN

# ---- .bash_profile: start X on tty1 on login -------------------------------
grep -q "startx" /home/pi/.bash_profile 2>/dev/null || cat >> /home/pi/.bash_profile << 'BASHPROFILE'

# Beer Pro kiosk: auto-start X on tty1
if [[ -z "\$DISPLAY" ]] && [[ "\$(tty)" == "/dev/tty1" ]]; then
    startx -- -nocursor 2>/dev/null
fi
BASHPROFILE

chown pi:pi /home/pi/.bash_profile

# ---- .xinitrc: start openbox ------------------------------------------------
cat > /home/pi/.xinitrc << 'XINITRC'
#!/bin/sh
exec openbox-session
XINITRC
chown pi:pi /home/pi/.xinitrc

# ---- openbox per-user autostart: launch Beer Pro kiosk ---------------------
mkdir -p /home/pi/.config/openbox
cat > /home/pi/.config/openbox/autostart << 'AUTOSTART'
# Beer Pro kiosk
xset s off &
xset s noblank &
xset -dpms &
bash /home/pi/beerpro/scripts/kiosk.sh &
AUTOSTART
chown -R pi:pi /home/pi/.config

EOF
