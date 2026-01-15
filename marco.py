import csv
import time
import requests
from urllib.parse import quote


INPUT_CSV = "location-terms.csv"
OUTPUT_CSV = "location-import-wikimedia.csv"


HEADERS = [
    "Title",
    "Thumbnail",
    "maps location name",
    "General overview",
    "Population and lifestyle",
    "Airport name",
    "Airport distance km",
    "Airport drive time min",
    "Beach name",
    "Beach distance km",
    "Beach drive time min",
    "Golf course name",
    "Golf distance km",
    "Golf drive time min",
    "History and character",
    "Property styles",
    "Property prices",
    "Things to do",
    "Education",
    "Points of interest",
    "Nearby restaurants"
]


UA = {
    "User-Agent": "WPAllImport-LocationBuilder/1.0 (contact: you@example.com)"
}


FALLBACK_FILE = "Andalusia_montage.jpg"
FALLBACK_THUMB = (
    f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(FALLBACK_FILE)}"
)


WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/{}"



def wikidata_search_entity(place_name: str):
    """
    Search Wikidata for a place name.
    Tries to prefer Spanish municipalities/cities.
    Returns QID (e.g. 'Q12345') or None.
    """
    params = {
        "action": "wbsearchentities",
        "search": place_name,
        "language": "en",
        "format": "json",
        "limit": 8,
    }

    r = requests.get(WIKIDATA_SEARCH, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    results = r.json().get("search", [])

    if not results:
        return None

    def score(item):
        desc = (item.get("description") or "").lower()
        s = 0

        if "spain" in desc or "spanish" in desc:
            s += 5
        if any(k in desc for k in ["municipality", "town", "village", "city"]):
            s += 3
        if any(k in desc for k in ["málaga", "malaga", "granada", "andalusia", "andalucía"]):
            s += 2
        if any(k in desc for k in ["born", "actor", "album", "film"]):
            s -= 5

        return s

    best = sorted(results, key=score, reverse=True)[0]
    return best.get("id")


def wikidata_get_p18_filename(qid: str):
    """
    Fetch Wikidata P18 (image) filename.
    Returns filename string or None.
    """
    r = requests.get(WIKIDATA_ENTITY.format(qid), headers=UA, timeout=30)
    r.raise_for_status()

    js = r.json()
    ent = js.get("entities", {}).get(qid, {})
    claims = ent.get("claims", {})
    p18 = claims.get("P18")

    if not p18:
        return None

    try:
        return p18[0]["mainsnak"]["datavalue"]["value"]
    except Exception:
        return None


def commons_direct_url_from_filename(filename: str):
    """
    Converts a Commons filename into a direct, import-friendly URL.
    """
    return COMMONS_FILEPATH.format(quote(filename))


def wikimedia_thumbnail_for_place(title: str):
    """
    Resolve a Wikimedia thumbnail for a place.
    Falls back to a default image if nothing is found.
    """
  
    qid = wikidata_search_entity(title)
    if qid:
        fn = wikidata_get_p18_filename(qid)
        if fn:
            return commons_direct_url_from_filename(fn)

    
    qid = wikidata_search_entity(f"{title} Spain")
    if qid:
        fn = wikidata_get_p18_filename(qid)
        if fn:
            return commons_direct_url_from_filename(fn)

    return FALLBACK_THUMB

def main():
    titles = []


    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  

        for row in reader:
            if not row:
                continue
            title = (row[0] or "").strip()
            if title:
                titles.append(title)


    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()

        for i, title in enumerate(titles, 1):
            thumb = wikimedia_thumbnail_for_place(title)

            row = {h: "" for h in HEADERS}
            row["Title"] = title
            row["Thumbnail"] = thumb

            writer.writerow(row)
            print(f"[{i}/{len(titles)}] {title} -> {thumb}")

            time.sleep(0.6)

    print("\nDone:", OUTPUT_CSV)


if __name__ == "__main__":
    main()
