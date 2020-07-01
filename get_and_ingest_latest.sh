#!/bin/bash
set -e

YEAR=$(date +%Y)

source ~/souenv/bin/activate
cd ~/sou-dataskydd
python get_and_ingest.py get "http://data.riksdagen.se/dataset/dokument/sou-${YEAR}-.json.zip" \
 && python get_and_ingest.py get "http://data.riksdagen.se/dataset/dokument/ds-${YEAR}-.json.zip" \
 && python get_and_ingest.py ingest
