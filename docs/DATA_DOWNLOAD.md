# Getting the data, step by step

## Read this first

There is no file to download for Halifax.

- **MarineCadastre.gov** (the big free AIS archive) only includes ships inside the United States Exclusive Economic Zone. Halifax is Canadian waters and is not in it.
- Canada does not publish a free archive of raw AIS positions.

So the data for this project is **collected live**, using a free service called aisstream.io. You start a script, leave it running for a few weeks, and it saves every ship it hears in the study area.

Two things follow from that:

1. **You cannot get last month's data.** Collection starts the day you start the script.
2. **It only works if aisstream.io has a receiver near Halifax.** Step 4 below is a 30 minute test that tells you. Do that test before anything else. (When this project was aimed at Saint John, this test is exactly what saved it: zero messages over four days of trying. The first Halifax test picked up 34 ships in five minutes.) If it fails for you, go to [Plan B](#plan-b-use-us-waters-instead).

---

## Step 1. Install Python and the libraries

1. Install Python 3.10 or newer from <https://www.python.org/downloads/>. On Windows, tick **"Add Python to PATH"** in the installer.
2. Open a terminal (Command Prompt or PowerShell on Windows, Terminal on Mac).
3. Go to the project folder:

   ```
   cd path/to/halifax-vessel-tracker
   ```

4. Install the libraries:

   ```
   pip install -r requirements.txt
   ```

## Step 2. Check that everything works, using fake data

```
python run_pipeline.py --sample
```

This makes fake ships, runs the whole analysis on them, and writes results to `outputs_sample/`. You should see a summary ending with 1 flagged gap, 2 loitering runs and 1 rendezvous. Open `outputs_sample/map.html` in a browser to see the map.

If this step fails, fix it before going on. Nothing later will work either.

## Step 3. Get a free aisstream.io API key

1. Go to <https://aisstream.io/authenticate> and sign in with your GitHub account.
2. Open the **API Keys** page and click **Create New API Key**.
3. Copy the key. It is a long string of letters and numbers.
4. In the project folder, make a new text file called exactly `api_key.txt` and paste the key into it. Nothing else goes in the file.

`api_key.txt` is listed in `.gitignore`, so git will not upload it. **Never paste the key into the code or commit it.** If you do by accident, delete the key on the aisstream website and make a new one.

## Step 4. Run the 30 minute coverage test

```
python collect_ais.py --minutes 30
```

You should see `connected`, then a status line every 5 minutes, then a final line like:

```
Saved 412 positions from 17 ships.
```

While it runs, open a live ship map such as <https://www.marinetraffic.com> or <https://www.vesselfinder.com> and look at Halifax. There are almost always ships in the harbour, at the anchorages or moving in the approaches.

| What you see | What it means | What to do |
|---|---|---|
| Ships on the live map **and** positions saved | It works | Go to step 5 |
| Ships on the live map but **0 positions saved** after 30 minutes | aisstream.io has no receiver that can hear this area | Try once more at a different time of day. If still 0, go to Plan B |
| An error mentioning the API key | The key is wrong | Check `api_key.txt` has only the key, with no spaces or quotes |
| `disconnected` again and again | Network problem, or a firewall blocking websockets | Try a different network (school wifi often blocks this) |

Then run the pipeline on your 30 minutes of data to make sure the files are readable:

```
python run_pipeline.py
```

It will find little or nothing, because 30 minutes is far too short. You are only checking that it runs without an error.

## Step 5. Collect for three to four weeks

```
python collect_ais.py
```

Leave it running. Stop it with **Ctrl+C**. You can stop and restart as often as you like, because it adds to the existing files.

**The computer has to stay on and awake the whole time.** Every hour it is off is an hour of missing data. The pipeline detects these outages and ignores them, but a dataset that is half outages is not worth much.

Ways to keep it running:

- **Your own computer:** turn off sleep in the power settings and keep it plugged in.
  - Windows: Settings > System > Power > "When plugged in, put my device to sleep after" > **Never**. Leave the terminal window open.
  - Mac: run `caffeinate -i python collect_ais.py` instead of the normal command.
  - Linux: run `nohup python collect_ais.py &` so it keeps going after you close the terminal.
- **A Raspberry Pi or old laptop** left on in a corner. This is the most reliable cheap option — full setup guide for a Pi in **[docs/RASPBERRY_PI.md](RASPBERRY_PI.md)**.
- **A small cloud server**, if you already know how to use one.

### Checking on it

Once a day, look in `data/raw/`:

- There should be a new `positions_YYYY-MM-DD.csv` for each day, and today's file should be getting bigger.
- `collector_log.csv` lists every time the script connected, disconnected or was stopped. A few disconnects a day are normal. The script reconnects by itself.

Dates and times in the files are in **UTC**, which is 4 hours ahead of Halifax in winter and 3 hours ahead in summer. A new file starts at 8 pm or 9 pm local time, not at midnight.

### How much data to expect

This depends on how many ships are around and how good reception is, so treat it as a rough guide: a few megabytes a day, and well under a gigabyte for a month.

## Step 6. Run the analysis

```
python run_pipeline.py
```

Results go to `outputs/`:

| File | What it is |
|---|---|
| `summary.txt` | The headline numbers for the README |
| `map.html` | Interactive map. Open it in a browser |
| `map.png`, `coverage_map.png` | Pictures for the README |
| `gaps_flagged.csv` | Gaps that passed every check |
| `gaps_all_candidates.csv` | Every gap, with the result of each check |
| `loitering.csv`, `rendezvous.csv` | The other two detectors |

You can run this at any time while the collector is still going, to watch the results build up.

## Step 7. Tune the port circles

After the first real run, open `outputs/map.html` and look at the loitering squares. If a lot of them are bunched together just outside a port circle, that is an anchorage, not suspicious behaviour. Make the circle bigger or add a new one in `config.py`, and run the pipeline again.

Pilot boats meet every large ship on its way into Halifax, near the pilot boarding area off Chebucto Head. If the rendezvous triangles bunch up in one spot outside the port circles, that is a boarding or waiting area. Add a circle for it.

## Step 8. Review the flags by hand

```
python review.py
```

Open `outputs/review_sheet.csv` in Excel or Google Sheets. For each row, find the event on the map, look the ship up by name or MMSI number, and type `genuine`, `false_positive` or `unsure` in the `label` column. Save it as CSV, then:

```
python review.py --score
```

While you are looking each ship up, check that none of them is a navy or coast guard ship that slipped past the military filter (the filter only catches ships that report AIS type 35). If one did, do not publish that row. Add its type to `EXCLUDED_TYPES` in `config.py` if it reports one, or leave it out of the results by hand and say so in the README.

Put the numbers in the Results section of the README.

---

## Plan B: use US waters instead

Use this only if step 4 shows that aisstream.io cannot hear ships in your study area. (This project already used a simpler version of Plan B once: it started in the Bay of Fundy, where aisstream.io hears nothing, and moved to Halifax. If even Halifax fails for you, US waters are the last resort, because they are the only ones with a free historical archive.)

MarineCadastre.gov has years of historical AIS data, free, but only for US waters. You move the study area across the border and download a month of history instead of collecting it.

1. **Pick a US area.** Two options:
   - Closest to home: the Maine coast from Eastport to Machias (latitude 44.3 to 45.0, longitude -67.6 to -66.9). Traffic is light, so there may not be much to find.
   - Busier: Portland, Maine and Casco Bay (latitude 43.4 to 43.9, longitude -70.4 to -69.8).
2. **Change `config.py`:** set `AREA_NAME`, `LAT_MIN`, `LAT_MAX`, `LON_MIN`, `LON_MAX` to the new area, and replace the `PORTS` list with the ports in that area.
3. **Download the data:**
   1. Go to <https://marinecadastre.gov/ais> and click **Launch AccessAIS**.
   2. Draw a box on the map matching the one in `config.py`.
   3. Pick a date range of about one month.
   4. Choose the point (broadcast) data, submit the order and enter your email address.
   5. A download link arrives by email. The file is a zipped CSV. Orders are limited to around 2 GB, so if yours is refused, pick a shorter date range.
4. **Put the downloaded file** in a new folder called `data/marinecadastre/`.
5. **Convert it:**

   ```
   python import_marinecadastre.py
   ```

6. **Run the analysis:**

   ```
   python run_pipeline.py
   ```

Remember to update the README, since the project would no longer be about Halifax.

---

## Problems

| Problem | Likely cause |
|---|---|
| `No API key found` | `api_key.txt` is missing, misnamed (check it is not `api_key.txt.txt`) or in the wrong folder |
| `ModuleNotFoundError: No module named 'websockets'` | Run `pip install -r requirements.txt` again |
| `No positions_*.csv files found in data/raw` | The collector has not saved anything yet |
| `No rows left after cleaning` | The data is outside the box in `config.py` |
| Pipeline says 0 well covered cells | Not enough data yet. A cell needs 20 ship visits before it is trusted |
| Every gap has `feed_was_working = False` | The collector was off a lot. Check `collector_log.csv` |
