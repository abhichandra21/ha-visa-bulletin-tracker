# Home Assistant Visa Bulletin Tracker

Tracks the monthly US Department of State [Visa Bulletin](https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html) priority dates for India employment-based (EB) categories directly inside Home Assistant.

Data is scraped from the official State Department website. No external services, APIs, or accounts required.

<img width="514" height="911" alt="image" src="https://github.com/user-attachments/assets/ddf63125-25ce-46ac-acea-413c0d5960ae" />

## What You Get

- Live EB1, EB2, EB3 priority dates for India (Final Action Dates table)
- Month-to-month movement in days (positive = forward, negative = retrogression)
- Up to 24 months of history stored locally in a JSON file
- A Lovelace dashboard with current dates, movement, history chart, and history table
- Push notification when a new bulletin is detected
- Individual HA entities for each EB category (for use in your own automations)

## Repository Layout

```
visa_bulletin/           ← copy this entire directory into your HA config
  visa_bulletin.py       ← scraper script
  dashboard.yaml         ← Lovelace dashboard
  package.yaml           ← all HA config: sensor, automations, input_text, templates
```

Everything lives in one directory. Installation is copying that folder and adding two lines to two existing files.

---

## Prerequisites

**Home Assistant:** 2023.x or later (tested through 2026.x)

**Python packages** — needs `requests` and `beautifulsoup4` in HA's Python environment. See [Installing Python Packages](#installing-python-packages) below.

**Custom Lovelace cards** — the dashboard uses two cards installable via [HACS](https://hacs.xyz):

| Card | Purpose |
|------|---------|
| [custom:template-entity-row](https://github.com/thomasloven/lovelace-template-entity-row) | Per-row Jinja templates in entity cards |
| [custom:apexcharts-card](https://github.com/RomRider/apexcharts-card) | Historical progression chart |

---

## Installation

### Step 1 — Copy the directory

Copy the entire `visa_bulletin/` directory into your HA configuration directory (the same folder as `configuration.yaml`):

```
<config>/
  configuration.yaml
  visa_bulletin/          ← paste here
    visa_bulletin.py
    dashboard.yaml
    package.yaml
```

### Step 2 — Install Python packages

The script requires `requests` and `beautifulsoup4`. Install them in HA's Python environment:

**Home Assistant OS / Supervised:**
```bash
docker exec -it homeassistant pip install requests beautifulsoup4
```

**Home Assistant Container (manual Docker):**
```bash
docker exec -it <your-container-name> pip install requests beautifulsoup4
```

**Home Assistant Core (venv):**
```bash
source /srv/homeassistant/bin/activate
pip install requests beautifulsoup4
```

> These packages don't survive a full HA container rebuild. If the sensor goes unavailable after a major HA upgrade, re-run the install command.

**Verify before continuing:**
```bash
# HA OS / Supervised:
docker exec -it homeassistant python3 /config/visa_bulletin/visa_bulletin.py

# HA Core / Container:
python3 /path/to/config/visa_bulletin/visa_bulletin.py
```

You should see JSON output with `eb1`, `eb2`, `eb3` fields. If not, see [Troubleshooting](#troubleshooting).

### Step 3 — Load the package

Add these two lines to your `customize.yaml` (the file included under `homeassistant:` in configuration.yaml):

```yaml
packages:
  visa_bulletin: !include visa_bulletin/package.yaml
```

This is an [HA Packages](https://www.home-assistant.io/docs/configuration/packages/) declaration. It merges the sensor, automations, input_text helpers, and template sensors from `package.yaml` into your configuration without touching any of your existing files.

> If you don't use `customize.yaml` and your `configuration.yaml` has a bare `homeassistant:` block, add the `packages:` key directly there instead.

### Step 4 — Register the dashboard

Add this block to your `ui-lovelace.yaml` under the `dashboards:` key:

```yaml
lovelace-visa:
  mode: yaml
  title: "Visa Bulletin"
  icon: mdi:passport
  show_in_sidebar: true
  filename: visa_bulletin/dashboard.yaml
```

### Step 5 — Set your notification service

Open `visa_bulletin/package.yaml` and find the notification automation near the bottom. Replace `notify.YOUR_NOTIFY_SERVICE` with your actual service:

```yaml
- action: notify.YOUR_NOTIFY_SERVICE   # ← change this
```

Common values:

| Setup | Service name |
|-------|-------------|
| HA Companion app | `notify.mobile_app_<your_phone_name>` |
| Default | `notify.notify` |

To find yours: **Developer Tools → Actions → search "notify"**.

### Step 6 — Restart Home Assistant

After restart, the startup automation fires immediately. Wait ~30 seconds, then open the Visa Bulletin dashboard — you should see current data.

---

## How It Works

```
HA triggers script (on startup + every 12 hours)
  └─▶ Fetch travel.state.gov bulletin index
        └─▶ Find URL of latest bulletin
              └─▶ Fetch and parse "Final Action Dates" table
                    └─▶ Extract EB1/EB2/EB3 → India column
                          └─▶ Append/update visa_bulletin/history.json
                                └─▶ Compute movement vs. previous month
                                      └─▶ Print JSON → sensor.visa_bulletin
```

History is stored in `visa_bulletin/history.json`. It's created automatically on first run and keeps the last 24 months. If deleted, it rebuilds from the next run onward.

---

## Understanding the Values

| Value | Meaning |
|-------|---------|
| `Jan 01, 2020` | Priority date cutoff — applicants with earlier dates may proceed |
| `Current` | No backlog; all priority dates in this category are current |
| `Retrogressed (U)` | Unauthorized — USCIS is not accepting new cases this month |
| `N/A` (movement) | Movement can't be calculated (e.g. prior month had no comparable date) |

The State Department uses single-letter codes in the bulletin table:
- `C` → Current
- `U` → Unauthorized (retrogressed)

---

## Entities Created

After installation, these entities are available in HA:

| Entity | Description |
|--------|-------------|
| `sensor.visa_bulletin` | Main sensor — state is last fetch time, attributes carry all data |
| `sensor.eb1_current_month` | EB1 India priority date |
| `sensor.eb2_current_month` | EB2 India priority date |
| `sensor.eb3_current_month` | EB3 India priority date |
| `sensor.eb1_monthly_movement` | EB1 movement in days vs. prior month |
| `sensor.eb2_monthly_movement` | EB2 movement in days vs. prior month |
| `sensor.eb3_monthly_movement` | EB3 movement in days vs. prior month |
| `binary_sensor.eb1_recently_updated` | `on` if data updated in the last 7 days |
| `binary_sensor.eb2_recently_updated` | `on` if data updated in the last 7 days |
| `binary_sensor.eb3_recently_updated` | `on` if data updated in the last 7 days |

---

## Configuration Options

### Scan interval

The sensor polls every 12 hours (`scan_interval: 43200` in `package.yaml`). The bulletin is released once a month, so this is well within reason. Lower to `3600` (1 hour) for faster detection of new releases — be respectful of State Department servers.

### Recorder history retention

HA's default recorder keeps only 10 days of sensor history. To retain `sensor.visa_bulletin` longer, add to your `recorder.yaml`:

```yaml
include:
  entities:
    - sensor.visa_bulletin
```

Note: this is separate from the `history.json` file, which stores up to 24 months regardless.

---

## Troubleshooting

**Sensor shows `unavailable` or `unknown`**

Run the script directly to see the error:
```bash
docker exec -it homeassistant python3 /config/visa_bulletin/visa_bulletin.py
# Add --debug for verbose HTML parsing output
docker exec -it homeassistant python3 /config/visa_bulletin/visa_bulletin.py --debug
```

**`ModuleNotFoundError: No module named 'requests'`**

Python packages aren't installed in HA's environment. Re-run Step 2.

**`Could not find employment-based table in the bulletin`**

The State Department changed their page layout. Open an issue with the `--debug` output — the fix is typically a one-line change to the table-detection logic.

**`Could not find dates for categories: eb2`** (or eb1/eb3)

That category is likely `U` (Unauthorized/retrogressed) in the current bulletin. Make sure you have the latest `visa_bulletin.py` — this is handled automatically.

**History file error when testing outside HA**

When you run the script directly on the host (not inside the container), `/config` doesn't exist so the history file can't be saved. The JSON output to stdout is still correct — the error only affects the persistence step, which works fine when HA runs the script inside its container.

---

## License

MIT
