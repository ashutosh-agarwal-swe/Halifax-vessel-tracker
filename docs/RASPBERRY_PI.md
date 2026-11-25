# Running the collector on a Raspberry Pi Zero 2 W

A collector has to run for weeks without sleeping. A Raspberry Pi is cheap,
silent and uses about as much power as a phone charger, so it is the best
machine for the job. The Pi Zero 2 W is small but more than strong enough:
the collector just holds one internet connection open and writes a few
megabytes a day.

Everything here works without ever plugging a screen or keyboard into
the Pi.

## What you need

- Raspberry Pi Zero 2 W
- A microSD card (8 GB or bigger)
- A good 5V power supply (2.5A, the official one or a quality phone charger — cheap ones cause crashes)
- WiFi the Pi can reach
- Your Windows computer, on the same network

---

## Step 1. Put Raspberry Pi OS on the SD card

1. On your Windows computer, install **Raspberry Pi Imager** from
   <https://www.raspberrypi.com/software/>.
2. Open it and make three choices:
   - **Device:** Raspberry Pi Zero 2 W
   - **Operating system:** Raspberry Pi OS Lite (64-bit) — "Lite" means no
     desktop, which is all a headless collector needs
   - **Storage:** your SD card
3. Click **Next**. When it asks "Would you like to apply OS customisation
   settings?", choose **Edit settings** and fill in:
   - **Hostname:** `aiscollector`
   - **Username and password:** pick a username you will remember, e.g. `ashutosh`
     (write it down — you need it for every ssh login)
   - **Wireless LAN:** your home WiFi name and password
   - **Wireless LAN country:** CA (or wherever you are — the wrong country
     can make WiFi not work at all)
   - **Services tab:** tick **Enable SSH** with password authentication
4. Write the card. Put it in the Pi and plug the Pi in.
5. Wait 2-3 minutes for the first boot (the green LED flickers while it works).

## Step 2. Connect to the Pi from Windows

Open PowerShell on your Windows computer:

```
ssh ashutosh@aiscollector.local
```

(use the username you picked). First time it asks about a "fingerprint" —
type `yes`. Then type the password you set. You are now typing commands
on the Pi.

If `aiscollector.local` is not found, look in your router's device list for
the Pi's IP address and use that instead: `ssh ashutosh@192.168.x.x`.

## Step 3. Install the project on the Pi

On the Pi, run these one at a time:

```
sudo apt update
sudo apt install -y git python3-websockets
git clone https://github.com/ashutosh-agarwal-swe/halifax-vessel-tracker.git
cd halifax-vessel-tracker
```

(If the repository is private, clone will ask for a login. Use your GitHub
username and a Personal Access Token from <https://github.com/settings/tokens>
as the password.)

Now give it the aisstream.io key. Make the file:

```
nano api_key.txt
```

Paste the key, then press **Ctrl+O**, **Enter**, **Ctrl+X** to save and quit.

Quick test — collect for 10 minutes:

```
python3 collect_ais.py --minutes 10
```

You should see `connected`, and after a minute or two the position count
should start climbing (Halifax is busy). Press Ctrl+C to stop early or let
it finish. If positions are being saved, everything works. If not, go to
the Problems section at the bottom before doing anything else.

## Step 4. Make it run forever, starting on every boot

This creates a systemd service: Linux will start the collector when the Pi
boots and restart it automatically if it ever crashes.

Create the service file:

```
sudo nano /etc/systemd/system/ais-collector.service
```

Paste this in (change `ashutosh` to your username in both places):

```
[Unit]
Description=AIS ship position collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ashutosh
WorkingDirectory=/home/ashutosh/halifax-vessel-tracker
ExecStart=/usr/bin/python3 collect_ais.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Save with **Ctrl+O**, **Enter**, **Ctrl+X**. Then:

```
sudo systemctl enable ais-collector
sudo systemctl start ais-collector
```

The collector is now running in the background and will survive reboots.
You can unplug the Pi, move it to a corner, plug it back in — a minute
after boot it will be collecting again.

## Step 5. Checking on it

Any time, ssh in and:

| What you want | Command |
|---|---|
| Is it running? | `sudo systemctl status ais-collector` |
| Live log of connect/disconnect events | `cat ~/halifax-vessel-tracker/data/raw/collector_log.csv` |
| How much data today | `ls -la ~/halifax-vessel-tracker/data/raw/` |
| Stop it | `sudo systemctl stop ais-collector` |
| Start it again | `sudo systemctl start ais-collector` |
| Turn off auto-start | `sudo systemctl disable ais-collector` |

Today's `positions_YYYY-MM-DD.csv` should be growing. A few disconnects a
day are normal — the script reconnects by itself.

## Step 6. Getting the data back to your computer for analysis

The analysis is easier to run on your Windows computer (it is faster and
already has the libraries). Every week or so, copy the data over. Run this
in PowerShell **on your Windows computer**:

```
scp -r ashutosh@aiscollector.local:~/halifax-vessel-tracker/data/raw "C:\Users\Ashut\Downloads\Fundy Vessel\data\raw"
```

(adjust the username and the project path if yours differ). Windows may
warn that files already exist from your test runs — overwriting is fine,
the Pi's copies are the complete ones.

Then run the pipeline as usual:

```
python run_pipeline.py
```

The collector on the Pi keeps running the whole time — copying files does
not interrupt it.

---

## Problems

| Problem | What to do |
|---|---|
| `ssh` can't find `aiscollector.local` | Wait another minute (first boot is slow), then check your router's device list for the Pi's IP and use that instead. If the Pi never appears, the WiFi name/password/country in the imager settings was probably wrong — re-flash the card |
| `ssh` asks for a password but rejects it | The username/password are the ones from the imager's OS customisation, not your GitHub or Windows login |
| `positions` files stay empty or missing | Check the internet: `ping -c 3 google.com`. If that works, look at `journalctl -u ais-collector -n 50` for errors |
| `ModuleNotFoundError: No module named 'websockets'` | Run `sudo apt install -y python3-websockets` again |
| Pi keeps crashing or corrupting the SD card | Almost always a weak power supply. Use a proper 5V 2.5A one |
| Want to unplug or move the Pi | ssh in and run `sudo shutdown now` first, wait 30 seconds, then unplug. Pulling the plug mid-write can corrupt the SD card |

## Notes

- The collector appends to the same files every day, so restarts never lose data.
- Times in the data files are UTC, same as before.
- If you ever update the project on GitHub, pull the changes on the Pi with
  `cd ~/halifax-vessel-tracker && git pull`, then `sudo systemctl restart ais-collector`.
