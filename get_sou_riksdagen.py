#!/usr/bin/env python
# Python 3.6+

import glob
import json
import os
import re
import sys
import urllib.request
import zipfile
import tempfile
import shutil
from bs4 import BeautifulSoup
from pathlib import Path

ARCHIVE_PATH = './files'
QUEUE_PATH = './files-queue'


def download_json(url):
    temp_dir = tempfile.TemporaryDirectory()
    print(f"Downloading {url}")
    local_filename, headers = urllib.request.urlretrieve(url)
    print(f"{local_filename} downloaded")
    with zipfile.ZipFile(local_filename, 'r') as zip_ref:
        zip_ref.extractall(temp_dir.name)
    os.remove(local_filename)
    return temp_dir


def process_json_directory(temp_dir):
    with open('sou_names.json', 'r') as f:
        sou_names = json.load(f)

    for filename in glob.glob(os.path.join(temp_dir.name, '*.json')):
        with open(os.path.join(os.getcwd(), filename), 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            riksdagen_dok_id = data['dokumentstatus']['dokument']['dok_id']
            year = data['dokumentstatus']['dokument']['rm']
            number = data['dokumentstatus']['dokument']['nummer']
            sou_number = f"{year}:{number}"
            title = data['dokumentstatus']['dokument']['titel']
            url_html = data['dokumentstatus']['dokument']['dokument_url_html']
            related_id = data['dokumentstatus']['dokument']['relaterat_id']
            doc_id = f"{year}-{number}-data.riksdagen.se-{riksdagen_dok_id}"
            filename = f"{doc_id}.pdf"

            # Nearly all SOUs 2000-2004 from data.riksdagen.se are missing their titles in their metadata,
            # so for those, let's use an alternative title source...
            if 2000 <= int(year) <= 2004:
                sou_key = f"SOU {sou_number}"
                if sou_key in sou_names:
                    title = sou_names[sou_key]

            if os.path.isfile(f"{ARCHIVE_PATH}/{filename}.json"):
                print(f"{ARCHIVE_PATH}/{filename}.json already exists; skipping")
                continue

            print(f"Processing {sou_number} {title}")

            # https://stackoverflow.com/a/22800287
            soup = BeautifulSoup(data['dokumentstatus']['dokument']['html'], 'lxml')
            for script in soup(["script", "style"]):
                script.decompose()

            text = soup.get_text()
            text = text.replace('\r', ' ').replace('\n', ' ')
            text = re.sub(r"- (?!och)", "", text)

            bilagor = data['dokumentstatus']['dokbilaga']['bilaga']
            if isinstance(bilagor, list):
                for bilaga in bilagor:
                    if bilaga['dok_id'] == riksdagen_dok_id:
                        #pdf_filename = bilaga['filnamn']
                        url_pdf = bilaga['fil_url']
                        break
            elif isinstance(bilagor, dict):
                #pdf_filename = bilagor['filnamn']
                url_pdf = bilagor['fil_url']
            else:
                sys.exit(f"Something went wrong with {doc_id}, couldn't find PDF info. File {filename}")

            print(f"SOU     : {sou_number}")
            print(f"Year    : {year}")
            print(f"Title   : {title}")
            print(f"URL     : {url_pdf}")
            print(f"Filename: {filename}")
            print(f"riksdagen_dok_id  : {riksdagen_dok_id}")

            metadata = {
                "id": doc_id,
                "sou_number": sou_number,
                "year": year,
                "title": title,
                #"url": url,
                "url_pdf": url_pdf,
                "url_html": url_html,
                "filename": filename,
                "full_text": text,
                "related_id": related_id
            }

            print(f"Saving metadata to {QUEUE_PATH}/{filename}.json\n")
            with open(f"{QUEUE_PATH}/{filename}.json", 'w') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4, sort_keys=True)

    # Remove temporary directory
    shutil.rmtree(temp_dir.name)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <url>")
        sys.exit(1)

    Path(QUEUE_PATH).mkdir(parents=True, exist_ok=True)
    temp_dir = download_json(sys.argv[1])
    process_json_directory(temp_dir)


if __name__ == '__main__':
    main()
