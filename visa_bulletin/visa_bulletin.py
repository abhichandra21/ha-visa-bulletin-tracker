import argparse
import json
import logging
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

HISTORY_DATA_FILE = "/config/visa_bulletin/history.json"


class VisaBulletinError(Exception):
    pass


class ParsingError(VisaBulletinError):
    pass


def get_latest_bulletin_url():
    main_url = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"
    try:
        response = requests.get(main_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise VisaBulletinError(f"Error fetching main bulletin page: {e}")

    soup = BeautifulSoup(response.content, "html.parser")
    link = soup.find("a", string=re.compile(r"Visa Bulletin For"))

    if not link or not link.get("href"):
        raise ParsingError("Could not find the latest visa bulletin link.")

    return urljoin(main_url, link["href"])


def parse_visa_bulletin(html_content):
    logger.debug(f"Content length: {len(html_content)} characters")

    try:
        soup = BeautifulSoup(html_content, "html.parser")

        marker_text = "FINAL ACTION DATES FOR EMPLOYMENT-BASED PREFERENCE CASES"
        normalized_html = " ".join(html_content.replace("&nbsp;", " ").split())
        if " ".join(marker_text.split()) not in normalized_html:
            raise ParsingError("Could not find employment-based final action dates marker")

        tables = soup.find_all("table")
        logger.debug(f"Found {len(tables)} tables in document")

        target_table = None
        for i, table in enumerate(tables, 1):
            if not table.find("tr"):
                continue
            header_text = table.find("tr").get_text(" ", strip=True)
            logger.debug(f"Table {i} header: {header_text[:100]}")
            if "Employment" in header_text and "INDIA" in header_text:
                logger.debug(f"Found target table at index {i}")
                target_table = table
                break

        if not target_table:
            raise ParsingError("Could not find employment-based table in the bulletin")

        results = {"eb1": None, "eb2": None, "eb3": None}
        rows = target_table.find_all("tr")

        header_cols = rows[0].find_all("td")
        india_col_index = None
        for i, col in enumerate(header_cols):
            if "INDIA" in col.get_text().upper():
                india_col_index = i
                logger.debug(f"India column at index {i}")
                break

        if india_col_index is None:
            raise ParsingError("Could not find India column in the table")

        for row in rows[1:]:
            cols = row.find_all("td")
            if not cols:
                continue

            category = cols[0].get_text(strip=True)
            if "1st" in category:
                key = "eb1"
            elif "2nd" in category:
                key = "eb2"
            elif "3rd" in category:
                key = "eb3"
            else:
                continue

            if len(cols) > india_col_index:
                raw = cols[india_col_index].get_text().strip().upper()
                if raw == "C":
                    results[key] = "current"
                elif raw == "U":
                    # U = Unauthorized: no visas being issued this month
                    results[key] = "unavailable"
                else:
                    try:
                        results[key] = datetime.strptime(raw, "%d%b%y").strftime("%Y-%m-%d")
                    except ValueError:
                        results[key] = None

        logger.debug(f"Parsed results: {results}")
        missing = [k for k, v in results.items() if not v]
        if missing:
            raise ParsingError(f"Could not find dates for: {', '.join(missing)}")

        return results

    except ParsingError:
        raise
    except Exception as e:
        raise ParsingError(f"Error parsing bulletin content: {e}")


def load_history(file_path):
    try:
        with open(file_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"months": []}


def save_history(file_path, current_data, bulletin_month):
    history = load_history(file_path)
    existing = next((m for m in history["months"] if m["month"] == bulletin_month), None)

    if existing:
        if any(existing.get(k) != current_data.get(k) for k in ("eb1", "eb2", "eb3")):
            existing.update({**{k: current_data[k] for k in ("eb1", "eb2", "eb3")},
                             "updated_at": datetime.now().isoformat()})
    else:
        history["months"].append({
            "month": bulletin_month,
            "eb1": current_data["eb1"],
            "eb2": current_data["eb2"],
            "eb3": current_data["eb3"],
            "captured_at": datetime.now().isoformat(),
        })

    history["months"] = sorted(history["months"], key=lambda x: x["month"])[-24:]

    try:
        with open(file_path, "w") as f:
            json.dump(history, f, indent=2)
    except IOError as e:
        logger.error(f"Error saving history: {e}")


def extract_bulletin_month(url):
    match = re.search(r"visa-bulletin-for-(\w+)-(\d{4})", url.lower())
    if match:
        month_name, year = match.groups()
        month_map = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
        }
        return f"{year}-{month_map.get(month_name, '01')}"
    return datetime.now().strftime("%Y-%m")


def to_comparable_date(date_str):
    if not date_str:
        return None
    if date_str.lower() == "current":
        return datetime(2100, 1, 1)
    if date_str.lower() == "unavailable":
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and parse the latest US Visa Bulletin for India EB categories."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        url = get_latest_bulletin_url()
        logger.info(f"Latest bulletin URL: {url}")

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        current_data = parse_visa_bulletin(response.text)
        bulletin_month = extract_bulletin_month(url)
        save_history(HISTORY_DATA_FILE, current_data, bulletin_month)

        history = load_history(HISTORY_DATA_FILE)
        history_months = history.get("months", [])

        prev_entry = next(
            (e for e in reversed(history_months) if e["month"] != bulletin_month),
            None,
        )

        movement = {}
        for cat in ("eb1", "eb2", "eb3"):
            cur = to_comparable_date(current_data.get(cat))
            prev = to_comparable_date(prev_entry.get(cat)) if prev_entry else None
            movement[f"{cat}_movement_days"] = (cur - prev).days if cur and prev else "N/A"

        output = {
            **current_data,
            **movement,
            "last_updated": datetime.now().isoformat(),
            "history": history_months,
            "bulletin_month": bulletin_month,
        }
        print(json.dumps(output, indent=2))

    except (VisaBulletinError, ParsingError) as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        logger.error(f"A network error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
