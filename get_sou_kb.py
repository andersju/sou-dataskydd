#!/usr/bin/env python
# Python 3.6+

import fitz # PyMuPDF
import json
import os
import re
import sys
import urllib.request
from unidecode import unidecode
from bs4 import BeautifulSoup
from pathlib import Path
from urllib import parse

ARCHIVE_PATH = './files'


def get_sou_kb(link):
    sou_number = link.get_text()
    year = sou_number[:4]
    title = link.findNextSibling(text=True).strip()
    url = link.get('href')
    urn = parse.parse_qs(parse.urlsplit(url).query)['urn'][0]

    try:
        int(year)
    except ValueError:
        sys.exit(f"Invalid year for {sou_number}")

    characters_to_keep = re.compile('[^a-zA-Z0-9_-]')

    filename_sou = unidecode(sou_number).replace(" ", "_").replace(":", "-")
    filename_sou = re.sub(characters_to_keep, '', filename_sou)

    filename_title = unidecode(title).replace(" ", "_")
    filename_title = re.sub(characters_to_keep, '', filename_title)
    filename_title = (filename_title[:50]) if len(filename_title) > 50 else filename_title

    filename = f"{filename_sou}-{filename_title}.pdf"

    if os.path.isfile(f"{ARCHIVE_PATH}/{filename}.json"):
        print(f"{filename}.json already exists; skipping")
        return

    print(f"SOU   : {sou_number}")
    print(f"Year  : {year}")
    print(f"Title : {title}")
    print(f"URL   : {url}")
    print(f"URN   : {urn}")

    Path(ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(url) as pdf_page:
        pdf_page_data = pdf_page.read().decode()

    pdf_page_soup = BeautifulSoup(pdf_page_data, 'html.parser')
    url_pdf = pdf_page_soup.a.get('href')

    print(f"Downloading {url_pdf} to {ARCHIVE_PATH}/{filename}")
    urllib.request.urlretrieve(url_pdf, f"{ARCHIVE_PATH}/{filename}")
    print(f"Saved to {ARCHIVE_PATH}/{filename}")

    print("Extracting text from PDF")
    doc = fitz.open(f"{ARCHIVE_PATH}/{filename}")
    text = ''
    for page in doc:
        text += page.getText()

    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r"- (?!och)", "", text)

    metadata = {
        "sou_number": sou_number,
        "year": year,
        "title": title,
        "url": url,
        "url_pdf": url_pdf,
        "urn": urn,
        "filename": filename,
        "full_text": text,
    }

    print(f"Saving metadata to {ARCHIVE_PATH}/{filename}.json")
    with open(f"{ARCHIVE_PATH}/{filename}.json", 'w') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4, sort_keys=True)

    print(f"Removing {ARCHIVE_PATH}/{filename}\n")
    os.remove(f"{ARCHIVE_PATH}/{filename}")


def scrape_kb():
    with urllib.request.urlopen('https://regina.kb.se/sou/') as url:
        data = url.read().decode()

    soup = BeautifulSoup(data, 'html.parser')
    links = soup.find_all('a')

    for link in links:
        url = link.get('href')
        if 'urn.kb.se' in url:
            get_sou_kb(link)


def main():
    scrape_kb()


if __name__ == '__main__':
    main()
