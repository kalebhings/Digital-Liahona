import requests
import json
import os
import time

# Correct base URL from the Open Scripture API documentation
BASE_URL = "https://openscriptureapi.org/api/scriptures/v1/lds/en"

# Directory to save JSON data
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Volumes to fetch
VOLUMES = [
    "bookofmormon",
    "oldtestament",
    "newtestament",
    "doctrineandcovenants",
    "pearlofgreatprice"
]

def fetch_volume_data(volume_id):
    """Fetch all metadata for a given volume from the Open Scripture API."""
    url = f"{BASE_URL}/volume/{volume_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for volume {volume_id}: {e}")
        return None

def fetch_chapter(volume_id, book_id, chapter_id):
    """Fetch a specific chapter for a book in a volume."""
    url = f"{BASE_URL}/volume/{volume_id}/{book_id}/{chapter_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        if response.status_code == 404:
            # 404 indicates the chapter doesn't exist, which we'll use to stop iterating
            return None
        print(f"Error fetching chapter {chapter_id} for {volume_id}/{book_id}: {e}")
        return None

def save_data(filename, data):
    """Save data to a JSON file with proper Unicode handling."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved data to {filename}")

def main():
    for volume_id in VOLUMES:
        # Create a directory for the volume
        volume_dir = os.path.join(DATA_DIR, volume_id)
        os.makedirs(volume_dir, exist_ok=True)

        # Step 1: Fetch volume metadata
        print(f"Fetching metadata for {volume_id}...")
        volume_data = fetch_volume_data(volume_id)
        if not volume_data:
            print(f"Failed to fetch metadata for {volume_id}. Skipping.")
            continue

        # Save the full volume data
        save_data(os.path.join(volume_dir, f"{volume_id}_data.json"), volume_data)

        # Step 2: Fetch chapters for each book
        books = volume_data.get("books", [])
        for book in books:
            book_id = book["_id"]
            book_title = book["title"]

            # Create a directory for the book
            book_dir = os.path.join(volume_dir, book_id)
            os.makedirs(book_dir, exist_ok=True)

            print(f"Fetching chapters for {volume_id}/{book_id} ({book_title})...")
            chapter_id = 1
            while True:
                chapter_data = fetch_chapter(volume_id, book_id, str(chapter_id))
                if not chapter_data:
                    # Stop if we get a 404 (no more chapters)
                    break

                # Save the chapter data
                save_data(os.path.join(book_dir, f"{book_id}_{chapter_id}.json"), chapter_data)
                chapter_id += 1
                time.sleep(0.1)  # Avoid hitting rate limits

if __name__ == "__main__":
    main()