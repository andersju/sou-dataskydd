#!/usr/bin/env python
# Python 3.6+
#
# ES code based on https://github.com/elastic/elasticsearch-py/blob/master/examples/bulk-ingest/bulk-ingest.py

import json
import os
import re
import sys
import urllib.request
import zipfile
import sqlite3
import logging
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import TransportError
from elasticsearch.helpers import streaming_bulk
import time

from urllib import parse
import fitz # PyMuPDF

from bs4 import BeautifulSoup


DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), 'sou.sqlite3')
ES_INDEX_NAME = 'sou2'
LOG_FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=LOG_FORMAT)
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)


def create_es_index(client, index, reset=False):
    create_index_body = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "default": {
                        "type": "swedish"
                    },
                    "default_search": {
                        "type": "swedish"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "year":                {"type": "integer"},   # eg. 1922
                "number":              {"type": "keyword" },  # e.g. 50
                "id_year_number":      {"type": "text"},   # e.g. 1922:50
                "year_number_sort":    {"type": "keyword"},
                "title":               {"type": "text"},
                "title_sort":          {"type": "keyword"},
                "url":                 {"type": "keyword"},
                "url_pdf":             {"type": "keyword"},
                "urn":                 {"type": "keyword"},
                "type":                {"type": "keyword"},
                "related_id":          {"type": "keyword"},
                "full_text": {
                    "type": "text",
                    "term_vector": "with_positions_offsets",
                    "store": True,
                },
            }
        },
    }

    try:
        if reset:
            client.indices.delete(index=index)
        client.indices.create(index=index, body=create_index_body)
    except TransportError as e:
        if e.error == "resource_already_exists_exception":
            pass
        else:
            raise


# https://stackoverflow.com/a/3300514
def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def generate_es_actions(con, reindex):
    cur = con.cursor()
    cur.row_factory = dict_factory
    if reindex:
        cur.execute("SELECT * FROM document")
    else:
        cur.execute("SELECT * FROM document WHERE is_indexed = 0")
    for data in cur:
        # For number_sort we pad with zeros for easy sorting. However, some early SOUs have
        # numbers like "1922:1 första serien" (separate from "1922:1"), so to get padding right
        # we also remove any non-digits from the serial number part.
        number_sort_serial = re.sub(r'\D', '', data['number']).zfill(3)

        yield {
            "_id": data['id'],
            "year": data["year"],
            "number": data["number"],
            "id_year_number": f"{data['id']} {data['year']}:{data['number']}",
            "year_number_sort": f"{data['year']}:{number_sort_serial}",  # for sorting purposes
            "title": data["title"],
            "title_sort": data["title"],
            "url": data["url"] if 'url' in data else '',
            "url_pdf": data["url_pdf"] if 'url_pdf' in data else '',
            "url_html": data["url_html"] if 'url_html' in data else '',
            "urn": data["urn"] if 'urn' in data else '',
            "full_text": data["full_text"],
            "type": data["type"],
            "related_id": data["related_id"]
        }
    cur.close()
    pass


def reset_es_index(index_name):
    log.info(f"Deleting and creating Elasticsearch index {index_name}")
    client = Elasticsearch()
    create_es_index(client, index_name, True)


def ingest_documents(con, index_name, reindex=False):
    log.info("Starting ingest")
    cur = con.cursor()
    doc_count = cur.execute('SELECT COUNT(*) AS count FROM document WHERE is_indexed = 0').fetchone()[0]
    cur.close()
    if doc_count == 0 and not reindex:
        log.info("Nothing to ingest")
        return

    start = time.time()
    client = Elasticsearch()
    create_es_index(client, index_name)

    indexed_doc_count = 0
    for ok, result in streaming_bulk(
            client=client,
            index=index_name,
            actions=generate_es_actions(con, reindex),
            chunk_size=25,
    ):
        action, result = result.popitem()
        doc_id = "/%s/doc/%s" % (client, result["_id"])

        if not ok:
            log.warning("Failed to %s document %s: %r" % (action, doc_id, result))
        else:
            log.info(f"Successfully indexed {result['_id']}")
            indexed_doc_count += 1
            cur = con.cursor()
            cur.execute('UPDATE document SET is_indexed = 1 WHERE id = ?', [result['_id']])
            con.commit()
            cur.close()

    end = time.time()
    log.info(f"Indexed {indexed_doc_count} documents in {end - start} s")


def init_db(db_path=DEFAULT_DB_PATH):
    # id of type text because 1) convenience, and 2) performance is completely irrelevant here
    sql = """
CREATE TABLE IF NOT EXISTS document (
    id TEXT PRIMARY KEY,
    dok_id TEXT,
    urn TEXT,
    year INT NOT NULL,
    number TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    full_text TEXT,
    related_id TEXT,
    is_indexed INT NOT NULL DEFAULT 0
);
"""
    con = sqlite3.connect(db_path)
    con.execute('PRAGMA journal_mode=wal')
    cur = con.cursor()
    cur.executescript(sql)
    cur.close()
    return con


def add_document_to_db(con, data, titles):
    dok_id = data['dokumentstatus']['dokument']['dok_id'].upper()
    year = data['dokumentstatus']['dokument']['rm']
    number = data['dokumentstatus']['dokument']['nummer']
    year_number = f"{year}:{number}"
    doc_type = data['dokumentstatus']['dokument']['typ']
    related_id = data['dokumentstatus']['dokument']['relaterat_id']

    title = data['dokumentstatus']['dokument']['titel']
    # Nearly all SOUs 2000-2004 from data.riksdagen.se are missing their titles in their metadata,
    # so for those, let's use an alternative title source...
    if 2000 <= int(year) <= 2004:
        doc_key = f"{doc_type.upper()} {year_number}"
        if doc_key in titles:
            title = titles[doc_key]

    # https://stackoverflow.com/a/22800287
    soup = BeautifulSoup(data['dokumentstatus']['dokument']['html'], 'lxml')
    for script in soup(["script", "style"]):
        script.decompose()

    text = soup.get_text()
    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r"- (?!och)", "", text)

    url_pdf = None
    bilagor = data['dokumentstatus']['dokbilaga']['bilaga']
    if isinstance(bilagor, list):
        for bilaga in bilagor:
            if bilaga['dok_id'].upper() == dok_id:
                # pdf_filename = bilaga['filnamn']
                url_pdf = bilaga['fil_url']
                break
    elif isinstance(bilagor, dict):
        # pdf_filename = bilagor['filnamn']
        url_pdf = bilagor['fil_url']

    if not url_pdf:
        log.warning(f"Couldn't process {dok_id}: couldn't find PDF info.")
        return

    sql = """
        INSERT INTO document
            (id, year, number, title, source, full_text, url, type, related_id)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    cur = con.cursor()
    cur.execute(sql, (dok_id, year, number, title, 'riksdagen', text, url_pdf, doc_type, related_id))
    con.commit()


def get_and_process_json(con, url):
    log.info(f"Starting processing of {url}")
    with open('titles.json', 'r') as f:
        doc_titles = json.load(f)

    local_filename, headers = urllib.request.urlretrieve(url)
    log.info(f"{local_filename} downloaded")

    cur = con.cursor()
    cur.row_factory = lambda cursor, row: row[0]
    with zipfile.ZipFile(local_filename, 'r') as zip_file:
        # Get list of filenames in zip, without filename extension, and uppercased.
        # E.g. ['h8b41.json', 'h8b411.json'] => ['H8B41', 'H8B411']
        zip_dok_ids = list(map(lambda x: os.path.splitext(x)[0].upper(), zip_file.namelist()))
        sql = f"SELECT dok_id FROM document WHERE dok_id in ({','.join(['?']*len(zip_dok_ids))})"
        existing_ids = cur.execute(sql, zip_dok_ids).fetchall()

        # Skip dok_ids that already exist in the database
        for dok_id in iter([dok_id for dok_id in zip_dok_ids if dok_id not in existing_ids]):
            log.info(f"Processing {dok_id}")
            with zip_file.open(f"{dok_id.lower()}.json", 'r') as f:
                read_data = f.read()
                data = json.loads(read_data.decode('utf-8-sig'))
                add_document_to_db(con, data, doc_titles)
    os.remove(local_filename)


def get_sou_kb(con, link):
    sou_number = link.get_text()
    year = sou_number[:4]
    title = link.findNextSibling(text=True).strip()
    url = link.get('href')
    urn = parse.parse_qs(parse.urlsplit(url).query)['urn'][0]

    cur = con.cursor()
    sql = "SELECT urn FROM document WHERE urn = ?"
    data = cur.execute(sql, [urn]).fetchone()
    if data is not None:
        log.info(f"{urn} already exists, skipping")
        return

    try:
        int(year)
    except ValueError:
        sys.exit(f"Invalid year for {sou_number}")

    log.info(f"Processing {sou_number} {title} ({urn})")
    with urllib.request.urlopen(url) as pdf_page:
        pdf_page_data = pdf_page.read().decode()

    pdf_page_soup = BeautifulSoup(pdf_page_data, 'html.parser')
    url_pdf = pdf_page_soup.a.get('href')

    local_filename, headers = urllib.request.urlretrieve(url_pdf)
    log.info(f"{local_filename} downloaded")

    doc = fitz.open(local_filename)
    text = ''
    for page in doc:
        text += page.getText()

    text = text.replace('\r', ' ').replace('\n', ' ')
    text = re.sub(r"- (?!och)", "", text)

    sql = """
            INSERT INTO document
                (id, year, number, title, source, full_text, url, type)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)"""

    cur.execute(sql, (urn, year, sou_number[5:], title, 'kb', text, url, 'sou'))
    con.commit()
    os.remove(local_filename)


def scrape_kb(con):
    log.info('Starting KB scraping')
    with urllib.request.urlopen('https://regina.kb.se/sou/') as url:
        data = url.read().decode()

    soup = BeautifulSoup(data, 'html.parser')
    links = soup.find_all('a')

    for link in links:
        if 'urn.kb.se' in link.get('href'):
            get_sou_kb(con, link)


def usage():
    print(f"Usage:\n"
          f"\t{sys.argv[0]} get <url to json zip>\n"
          f"\t{sys.argv[0]} scrape-kb\n"
          f"\t{sys.argv[0]} ingest [all]\n"
          f"\t{sys.argv[0]} reset-index")

    sys.exit(1)


def main():
    argc = len(sys.argv)
    if argc < 2:
        usage()

    con = init_db()
    if sys.argv[1] == 'get':
        if argc != 3:
            usage()
        get_and_process_json(con, sys.argv[2])
    elif sys.argv[1] == 'scrape-kb':
        scrape_kb(con)
    elif sys.argv[1] == 'ingest':
        reindex = True if argc == 3 and sys.argv[2] == 'all' else False
        ingest_documents(con, ES_INDEX_NAME, reindex)
    elif sys.argv[1] == 'reset-index':
        reset_es_index(ES_INDEX_NAME)
    else:
        con.close()
        usage()

    con.close()


if __name__ == '__main__':
    main()
