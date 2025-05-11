import requests
from bs4 import BeautifulSoup, FeatureNotFound
import pandas as pd
import re
import unicodedata
import time
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from urllib.parse import urlparse, parse_qs
import os

"""
This is modified/adapted from the following Source. I found that there were a few things not working, and I also added one.
1. Title Was not Being pulled
2. Footnotes weren't being pulled (they are filled dynamically with URI and a POST request)
3. I added the quote at the beginning to also be pulled.
4. I am removing from the speaker section the phrase "By " so that it just has the speakers name
https://www.reddit.com/r/latterdaysaints/comments/1f8lbpj/i_built_a_script_to_scrape_and_clean_general/
https://github.com/johnmwood/LDS-Conference-Scraper
"""

def get_soup_overview(url):
    """Create a tree structure (BeautifulSoup) out of a GET request's HTML."""
    try:
        r = requests.get(url, allow_redirects=True)
        r.raise_for_status()
        # print(f"Successfully fetched overview page: {r.url}")
        return BeautifulSoup(r.content, "html5lib")
    except requests.RequestException as e:
        print(f"Error fetching overview page {url}: {e}")
        return None

def is_decade_page(url):
    """Check if a page is a decade selection page based on URL pattern."""
    return bool(re.search(r"/study/general-conference/\d{4}\d{4}", url))

def scrape_conference_pages(main_page_url):
    """
    Retrieve a list of URLs for each conference (year/month) from the main page.
    Handles both direct conference links and decade overview pages.
    """
    soup = get_soup_overview(main_page_url)
    if soup is None:
        print(f"Failed to fetch content from {main_page_url}")
        return []

    all_conference_links = []

    # Find all the links that match the conference year/month or decade patterns
    links = [
        "https://www.churchofjesuschrist.org" + a["href"]
        for a in soup.find_all("a", href=True)
        if re.search(r"/study/general-conference/(\d{4}/(04|10)|\d{4}\d{4})", a["href"])
    ]

    for link in links:
        if is_decade_page(link):
            # If it's a decade page, scrape the individual year/month links from that page
            decade_soup = get_soup_overview(link)
            if decade_soup:
                year_links = [
                    "https://www.churchofjesuschrist.org" + a["href"]
                    for a in decade_soup.find_all("a", href=True)
                    if re.search(r"/study/general-conference/\d{4}/(04|10)", a["href"])
                ]
                all_conference_links.extend(year_links)
        else:
            # If it's a direct conference link, add it to the list
            all_conference_links.append(link)

    print(f"Total conference links found: {len(all_conference_links)}")
    # print("Sample conference links:", all_conference_links[:5])
    return all_conference_links

def scrape_talk_urls(conference_url):
    """Retrieve a list of URLs for each talk in a specific conference."""
    soup = get_soup_overview(conference_url)
    if soup is None:
        return []

    # Find links that match the talk pattern (year/month/talk-title)
    # The regex ensures that only links ending with a talk title after the month are returned
    talk_links = [
        "https://www.churchofjesuschrist.org" + a["href"]
        for a in soup.find_all("a", href=True)
        if re.search(r"/study/general-conference/\d{4}/(04|10)/[^/]+$", a["href"])
    ]

    # Remove duplicate links
    talk_links = list(set(talk_links))

    # print(f"Found {len(talk_links)} talk links in {conference_url}") 
    # if talk_links:
        # print("Sample talk links:", talk_links[:3]) 
    return talk_links


def get_html_and_initial_state(url):
    """
    Fetches HTML content from a URL and extracts __INITIAL_STATE__ data.
    The __INITIAL_STATE__ often contains dynamic data like footnotes.
    """
    try:
        r = requests.get(url, allow_redirects=True)
        r.raise_for_status()
        # print(f"Successfully fetched talk page: {r.url}") 

        html_text = r.text
        initial_state_data = None

        # Attempt to extract __INITIAL_STATE__ using regex first (more direct)
        # This regex looks for the variable assignment window.__INITIAL_STATE__ = "..." ;
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*"(.*?)"\s*;', html_text, re.DOTALL)

        if match:
            encoded_state = match.group(1) # Capture the content within the quotes
            try:
                decoded_state_bytes = base64.b64decode(encoded_state)
                decoded_state_str = decoded_state_bytes.decode('utf-8')
                initial_state_data = json.loads(decoded_state_str)
                # print("Successfully parsed initial state JSON using regex.") 
            except (base64.errors.B64DecodeError, json.JSONDecodeError, Exception) as e:
                print(f"Error processing __INITIAL_STATE__ content with regex for {url}: {e}")
        else:
            # Fallback to BeautifulSoup if regex fails (less reliable but a fallback)
            try:
                # Create a BeautifulSoup object just for finding the script tag by ID
                temp_soup = BeautifulSoup(html_text, "html.parser") # Use html.parser as a fallback parser
                initial_state_script = temp_soup.find('script', id='__INITIAL_STATE__')

                if initial_state_script and initial_state_script.string:
                    # print(f"Found __INITIAL_STATE__ script tag using BeautifulSoup fallback for {url}.") 
                    encoded_state = initial_state_script.string.strip()
                    # Remove trailing semicolon if present
                    if encoded_state.endswith(';'):
                        encoded_state = encoded_state[:-1]
                    decoded_state_bytes = base64.b64decode(encoded_state)
                    decoded_state_str = decoded_state_bytes.decode('utf-8')
                    initial_state_data = json.loads(decoded_state_str)
                    # print("Successfully parsed initial state JSON using BeautifulSoup fallback.") 
                # else:
                    # print(f"Could not find __INITIAL_STATE__ script tag using BeautifulSoup fallback or it was empty for {url}.") 

            except Exception as e:
                 print(f"Error with BeautifulSoup fallback for {url}: {e}")


        return html_text, initial_state_data # Return both raw html and parsed state data

    except requests.RequestException as e:
        print(f"Error fetching talk page {url}: {e}")
        return None, None # Return None for both if initial fetch fails

def parse_scripture_uri(uri):
    """
    Parses a scripture URI like /study/scriptures/bofm/mosiah/3?lang=eng&id=p19#p19
    into 'Book Chapter:Verse' format.
    """
    if not uri or '/study/scriptures/' not in uri:
        return None # Not a scripture URI

    try:
        # Remove the /study/ prefix
        path = uri.replace('/study/scriptures/', '')

        # Split by ? or # to get the core path and parameters/fragment
        parts = re.split(r'[?#]', path)
        core_path = parts[0] # e.g., bofm/mosiah/3

        # Split the core path into book and chapter
        path_segments = core_path.split('/')
        if len(path_segments) < 2:
            # Handle cases like just /study/scriptures/bofm (if they exist)
            if len(path_segments) == 1 and path_segments[0]:
                 book_short = path_segments[0]
                 chapter = None
            else:
                return None # Not in expected book/chapter format

        else:
            book_short = path_segments[-2] # e.g., mosiah
            chapter = path_segments[-1] # e.g., 3


        # Attempt to get the verse/paragraph ID from the query parameters or fragment
        verse = None
        if len(parts) > 1:
            params_fragment = parts[1]
            # Check for id=p# pattern in query string
            query_match = re.search(r'id=p(\d+)', params_fragment)
            if query_match:
                verse = query_match.group(1)
            else:
                # Check for p# pattern in fragment (after #)
                fragment_match = re.search(r'p(\d+)', params_fragment)
                if fragment_match:
                    verse = fragment_match.group(1)

        # Mapping of short book codes to full names
        book_map = {
            'bofm': 'Book of Mormon',
            'ot': 'Old Testament',
            'nt': 'New Testament',
            'dc-testament': 'Doctrine and Covenants',
            'pgp': 'Pearl of Great Price',
            'gen': 'Genesis', 'ex': 'Exodus', 'lev': 'Leviticus', 'num': 'Numbers', 'deut': 'Deuteronomy',
            'josh': 'Joshua', 'judg': 'Judges', 'ruth': 'Ruth', '1-sam': '1 Samuel', '2-sam': '2 Samuel',
            '1-kgs': '1 Kings', '2-kgs': '2 Kings', '1-chr': '1 Chronicles', '2-chr': '2 Chronicles',
            'ezra': 'Ezra', 'neh': 'Nehemiah', 'esth': 'Esther', 'job': 'Job', 'ps': 'Psalms',
            'prov': 'Proverbs', 'eccl': 'Ecclesiastes', 'song': 'Song of Solomon', 'isa': 'Isaiah',
            'jer': 'Jeremiah', 'lam': 'Lamentations', 'ezek': 'Ezekiel', 'dan': 'Daniel', 'hosea': 'Hosea',
            'joel': 'Joel', 'amos': 'Amos', 'obad': 'Obadiah', 'jonah': 'Jonah', 'micah': 'Micah',
            'nahum': 'Nahum', 'hab': 'Habakkuk', 'zeph': 'Zephaniah', 'hag': 'Haggai', 'zech': 'Zechariah',
            'mal': 'Malachi',
            'matt': 'Matthew', 'mark': 'Mark', 'luke': 'Luke', 'john': 'John', 'acts': 'Acts', 'rom': 'Romans',
            '1-cor': '1 Corinthians', '2-cor': '2 Corinthians', 'gal': 'Galatians', 'eph': 'Ephesians',
            'philip': 'Philippians', 'col': 'Colossians', '1-thes': '1 Thessalonians', '2-thes': '2 Thessalonians',
            '1-tim': '1 Timothy', '2-tim': '2 Timothy', 'titus': 'Titus', 'philem': 'Philemon', 'heb': 'Hebrews',
            'james': 'James', '1-pet': '1 Peter', '2-pet': '2 Peter', '1-jn': '1 John', '2-jn': '2 John',
            '3-jn': '3 John', 'jude': 'Jude', 'rev': 'Revelation',
            '1-ne': '1 Nephi', '2-ne': '2 Nephi', 'jacob': 'Jacob', 'enos': 'Enos', 'jarom': 'Jarom',
            'omni': 'Omni', 'w-of-m': 'Words of Mormon', 'mosiah': 'Mosiah', 'alma': 'Alma', 'hel': 'Helaman',
            '3-ne': '3 Nephi', '4-ne': '4 Nephi', 'morm': 'Mormon', 'ether': 'Ether', 'moro': 'Moroni',
            'dc': 'Doctrine and Covenants', 'js-h': 'Joseph Smith—History', 'js-m': 'Joseph Smith—Matthew',
            'a-of-f': 'Articles of Faith', 'abr': 'Abraham', 'fac': 'Facsimile'
        }
        book_full = book_map.get(book_short, book_short) # Use full name if found, otherwise use short

        if chapter and verse:
            return f"{book_full} {chapter}:{verse}"
        elif chapter:
            return f"{book_full} {chapter}" # Return just book and chapter if no verse found
        elif book_full:
            return book_full # Return just the book if no chapter/verse
        else:
            return None # Still not in a recognized format

    except Exception as e:
        print(f"Error parsing URI {uri}: {e}")
        return None # Return None if parsing fails


def scrape_talk_data(url):
    """
    Scrapes a single talk for metadata, content, and footnotes.
    Embeds relevant footnote details (ID, number, parsed scripture references)
    directly into the paragraph data they reference. Does NOT return a separate
    list of all footnotes in the main talk data.
    """
    try:
        html_content, initial_state_data = get_html_and_initial_state(url)

        if html_content is None:
            return {}

        # Create BeautifulSoup object for parsing the main content HTML
        try:
            # Try different parsers for the main content
            try:
                soup = BeautifulSoup(html_content, "lxml")
                # print("Using lxml parser for main content.") 
            except (ImportError, FeatureNotFound):
                # print("lxml not found or available for main content, falling back to html.parser.") 
                soup = BeautifulSoup(html_content, "html.parser")
                # print("Using html.parser for main content.") 
        except Exception as e:
             print(f"Error creating BeautifulSoup object for main content for {url}: {e}")
             return {} # Return empty if main content parsing fails


        # This ensures the footnote data is available when processing paragraphs
        footnote_lookup = {} # Dictionary for quick lookup by footnote_id

        if initial_state_data:
            try:
                parsed_url = urlparse(url)

                # Extract language code from query parameters
                query_params = parse_qs(parsed_url.query)
                language_code = query_params.get('lang', ['eng'])[0]  # default 'eng'

                # Construct the talk_uri_key used in the initial state JSON structure
                # The path in contentStore is /lang_code/path/after/study
                path_after_study = parsed_url.path.replace('/study', '')
                # Ensure we don't double-prepend the language code if it's already there
                if path_after_study.startswith(f'/{language_code}'):
                    talk_uri_key = path_after_study
                else:
                    talk_uri_key = f'/{language_code}{path_after_study}'

                # Navigate the JSON structure to find the footnotes data
                footnotes_data_from_state = (
                    initial_state_data
                    .get('reader', {})
                    .get('contentStore', {})
                    .get(talk_uri_key, {})
                    .get('content', {})
                    .get('footnotes', {})
                )

                # Build the lookup dictionary from the extracted data
                for note_id, note_details in footnotes_data_from_state.items():
                    # Ensure note_details is a dictionary before accessing its items
                    if isinstance(note_details, dict):
                        # Extract the dynamic URIs from the 'referenceUris' list within note_details
                        dynamic_uris = [
                            ref.get('href')
                            for ref in note_details.get('referenceUris', [])
                            if isinstance(ref, dict) and ref.get('href')
                        ]

                        # Parse dynamic URIs to get scripture references
                        parsed_references = [parse_scripture_uri(uri) for uri in dynamic_uris]
                        # Filter out any None results if parsing failed or it wasn't a scripture URI
                        parsed_references = [ref for ref in parsed_references if ref]

                        # Store only the necessary details in the lookup
                        footnote_lookup[note_id] = {
                            'footnote_id': note_id,  # Keep ID for reference
                            'footnote_number': note_details.get('marker', '').rstrip('.'),  # e.g., '1'
                            'parsed_scripture_references': parsed_references,  # e.g., ['Mosiah 3:19']
                        }

            except Exception as e:
                print(f'Error processing footnotes from initial state for {url}: {e}')
        # else:
            # print(f'Initial state data not available to extract footnotes for {url}. No footnotes will be linked.')

        # --- Extract Talk Metadata ---
        article_tag = soup.find('article', {'id': 'main'})

        title_tag = article_tag.find('h1') if article_tag else None
        title = title_tag.text.strip() if title_tag else 'No Title Found'

        header_div = article_tag.find('header') if article_tag else None

        quote = 'No Quote Found'
        conference = 'No Conference Found'
        speaker = 'No Speaker Found'
        calling = 'No Calling Found'

        if header_div:
            quote_tag = header_div.find('p', {'class': 'kicker'})
            quote = quote_tag.text.strip() if quote_tag else 'No Quote Found'

            conference_tag = header_div.find('div', class_=lambda c: c and 'catalogTitle' in c)
            conference = conference_tag.text.strip() if conference_tag else 'No Conference Found'

            byline_div = header_div.find('div', class_='byline')
            if byline_div:
                author_tag = byline_div.find('p', class_='author-name')
                speaker_raw = author_tag.text.strip() if author_tag else 'No Speaker Found'
                speaker = speaker_raw[3:].strip() if speaker_raw.lower().startswith('by ') else speaker_raw

                calling_tag = byline_div.find('p', {'class': 'author-role'})
                calling = calling_tag.text.strip() if calling_tag else 'No Calling Found'

        content_array_div = article_tag.find('div', {'class': 'body-block'}) if article_tag else None
        content_with_embedded_footnotes = []

        if content_array_div:
            paragraphs = content_array_div.find_all('p')
            for idx, para in enumerate(paragraphs, start=1):
                paragraph_text = para.get_text(strip=True)
                if not paragraph_text:
                    continue

                footnote_markers = para.find_all('a', class_='note-ref', attrs={'data-scroll-id': True})

                linked_footnotes_for_paragraph = []
                for marker in footnote_markers:
                    note_id = marker.get('data-scroll-id')
                    if note_id and note_id in footnote_lookup:
                        footnote_details = footnote_lookup[note_id]
                        linked_footnotes_for_paragraph.append({
                            'footnote_id': footnote_details.get('footnote_id'),
                            'footnote_number': footnote_details.get('footnote_number'),
                            'parsed_scripture_references': footnote_details.get('parsed_scripture_references', []),
                        })

                content_with_embedded_footnotes.append({
                    'paragraph_number': idx,
                    'paragraph': paragraph_text,
                    'linked_footnotes': linked_footnotes_for_paragraph,
                })

        year_match = re.search(r'/((?:19|20)\d{2})/', url)
        year = year_match.group(1) if year_match else 'No Year Found'
        season = 'April' if '/04/' in url else 'October'

        return {
            'title': title,
            'speaker': speaker,
            'calling': calling,
            'year': year,
            'season': season,
            'url': url,
            'content': content_with_embedded_footnotes,
            'quote': quote,
        }
    except Exception as e:
        print(f'Failed to scrape {url}: {e}')
        return {}

def scrape_talk_data_parallel(urls):
    """Scrapes all talks in parallel using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=10) as executor:  # Adjust `max_workers` as needed
        results = list(tqdm(executor.map(scrape_talk_data, urls), total=len(urls), desc="Scraping talks in parallel"))
    return [result for result in results if result]  # Filter out empty results

def main_scrape_process():
    """Main function to orchestrate the scraping process."""
    main_url = "https://www.churchofjesuschrist.org/study/general-conference?lang=eng"
    conference_urls = scrape_conference_pages(main_url)

    all_talk_urls = []
    for conference_url in tqdm(conference_urls, desc="Scraping conferences"):
        all_talk_urls.extend(scrape_talk_urls(conference_url))

    print(f"Total talks found: {len(all_talk_urls)}")

    conference_talks = scrape_talk_data_parallel(all_talk_urls)

    conference_df = pd.DataFrame(conference_talks)

    # Normalize Unicode and clean data
    # This loop applies normalization and cleaning to string columns
    for col in conference_df.columns:
        # Check if the column contains strings before applying string operations
        if conference_df[col].dtype == 'object': # Check for object dtype which often contains strings
            conference_df[col] = conference_df[col].apply(lambda x: unicodedata.normalize("NFD", x) if isinstance(x, str) else x)
            conference_df[col] = conference_df[col].apply(lambda x: x.replace("\t", "") if isinstance(x, str) else x)

    conference_df.to_json("conference_talks.json", orient="records", indent=4)
    print("Data also saved to 'conference_talks.json'.")


if __name__ == "__main__":
    start = time.time()
    main_scrape_process()
    end = time.time()
    print(f"Total time taken: {end - start} seconds")
