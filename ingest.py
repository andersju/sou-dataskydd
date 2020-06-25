#!/usr/bin/env python
# Python 3.6+
# Based on https://github.com/elastic/elasticsearch-py/blob/master/examples/bulk-ingest/bulk-ingest.py

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import TransportError
from elasticsearch.helpers import bulk, streaming_bulk
from pathlib import Path
import glob
import json
import os
import re
import sys
import time

ARCHIVE_PATH = './files'


def create_sou_index(client, index):
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
                "year": {
                    "type": "integer"  # eg. 1922
                },
                "number": {
                    "type": "keyword"  # e.g. 1922:50
                },
                "serial": {
                    "type": "keyword",  # e.g. 50
                },
                "title_sort": {
                    "type": "keyword",
                },
                "number_sort": {
                    "type": "keyword"
                },
                "title": {
                    "type": "text"
                },
                "url": {
                    "type": "keyword",
                },
                "url_pdf": {
                    "type": "keyword",
                },
                "urn": {
                    "type": "keyword",
                },
                "full_text": {
                    "type": "text",
                    "term_vector": "with_positions_offsets",
                    "store": True,
                }
            }
        },
    }

    try:
        #client.indices.delete(index=index)
        client.indices.create(index=index, body=create_index_body)
    except TransportError as e:
        if e.error == "resource_already_exists_exception":
            pass
        else:
            raise


def generate_actions(json_path):
    for filename in glob.glob(os.path.join(json_path, '*.json')):
        with open(os.path.join(os.getcwd(), filename), 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            print(data['title'])

            # For number_sort we pad with zeros for easy sorting. However, some early SOUs have
            # numbers like "1922:1 första serien" (separate from "1922:1"), so to get padding right
            # we also remove any non-digits from the serial number part.
            number_sort_serial = re.sub(r'\D', '', data['sou_number'][5:]).zfill(3)

            if 'id' in data:
                doc_id = data['id']
            else:
                doc_id = "".join(filter(str.isalnum, data["sou_number"]))

            yield {
                "_id": doc_id,
                "year": data["year"],
                "number": data["sou_number"],
                "serial": data["sou_number"][5:],
                "number_sort": f"{data['year']}:{number_sort_serial}",  # for sorting purposes
                "title": data["title"],
                "title_sort": data["title"],
                "url": data["url"] if 'url' in data else '',
                "url_pdf": data["url_pdf"] if 'url_pdf' in data else '',
                "url_html": data["url_html"] if 'url_html' in data else '',
                "urn": data["urn"] if 'urn' in data else '',
                "full_text": data["full_text"]
            }
    pass


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path with JSON files to import>")
        sys.exit(1)

    move_files = False
    if len(sys.argv) > 2 and sys.argv[2] == 'true':
        move_files = True

    # Make sure ARCHIVE_PATH exists
    Path(ARCHIVE_PATH).mkdir(parents=True, exist_ok=True)

    start = time.time()
    client = Elasticsearch()
    create_sou_index(client, 'sou')

    for ok, result in streaming_bulk(
            client=client,
            index='sou',
            actions=generate_actions(sys.argv[1]),
            chunk_size=25,
    ):
        action, result = result.popitem()
        doc_id = "/%s/doc/%s" % (client, result["_id"])
        if not ok:
            print("Failed to %s document %s: %r" % (action, doc_id, result))
        else:
            #print(f"Successfully processed {result['_id']}")
            #pprint(result)
            if move_files:
                from_file = os.path.join(sys.argv[1], f"{result['_id']}.pdf.json")
                to_file = os.path.join(ARCHIVE_PATH, f"{result['_id']}.pdf.json")
                os.rename(from_file, to_file)

    end = time.time()
    print(end - start)


if __name__ == "__main__":
    main()
