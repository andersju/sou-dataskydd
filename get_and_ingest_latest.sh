#!/bin/bash
set -e

YEAR=$(date +%Y)

source ~/souenv/bin/activate
cd ~/sou-dataskydd
python get_sou_riksdagen.py "http://data.riksdagen.se/dataset/dokument/sou-${YEAR}-.json.zip" \
 && python ingest.py files-queue true
