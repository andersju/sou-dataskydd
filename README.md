# sou.dataskydd.net

This repo contains the code for [sou.dataskydd.net](https://sou.dataskydd.net), a service that lets you do
full-text search on all the [_Swedish Government Official Reports_](https://en.wikipedia.org/wiki/Statens_offentliga_utredningar)
(Statens Offentliga Utredningar, SOU) that have been published from 1922 to
today.

Linköping University (LiU) provides a [similar service](https://ep.liu.se/databases/sou/default.aspx),
but 1) it doesn't provide highlighted extracts, and 2) it cannot sort by relevance, making it
considerably less useful than it could have been. So, I figured I could hack up something better with a little
Flask and ElasticSearch.

There are three parts: a couple of scripts to fetch SOUs and turn them into appropriately formatted JSON
files; a script to ingest said files into ElasticSearch; and a single-file Flask app for the web service.
As of now the code is "quick weekend project" quality, but perhaps that will change.

## Requirements

* Python 3.6+
* ElasticSearch 7.x

## Getting started

Clone this repository. Make sure ElasticSearch is up and running. Default configuration is fine.

Use virtualenv, venv or similar to install the required Python modules (`pip install -r requirements.txt`).

### Fetch files

There are two sources for SOUs. KB (National Library of Sweden) [provides OCR'd PDFs](https://regina.kb.se/sou/)
of the 6129 SOUs published between 1922 and 1999. Riksdagen - the Swedish parliament - has everything from 1990
and onwards in various formats (XML, JSON, SQL, etc.) on [data.riksdagen.se](https://data.riksdagen.se/data/dokument/),
but it's unclear to me how complete the 1990-2000 SOUs are. LiU, for their part, uses KB's material for 1922-1996
and the parliament's open data for 1997 and onwards.

`get_sou_kb.py` scrapes [KB's sou page](https://regina.kb.se/sou/). It figures out SOU number/year/title/URL/URN,
downloads the PDF, extracts the text, dumps the aforementioned metadata and text into a JSON file in `files-queue/`
and then removes the PDF to save space (some scanned SOUs can be hundreds of MB!). This can take a *long* time.

`get_sou_riksdagen.py` takes a URL to a zip with JSON files as an argument, e.g.:

    ./get_sou_riksdagen.py https://data.riksdagen.se/dataset/dokument/sou-2005-2009.json.zip
    
The zip file is downloaded to a temporary directory and extracted. The script goes through each JSON file and
extracts various data (number, year, title, URL, etc). If the SOU already exists in `files/`, it's skipped;
otherwise, the full text (which is in HTML) is extracted from the JSON and mangled through BeautifulSoup to get
rid of HTML elements. The data is then dumped into a new JSON file in `files-queue/`.

`ingest.py` takes a directory an argument. It first creates an ElasticSearch index for the SOUs, if it
doesn't already exist. It goes through each JSON file in the specified directory and indexes it. The document
 `_id` used is specified by the JSON file, so indexing the same document twice is fine - it'll just be overwritten.
 
 If `ingest.py` is called with `true` as its second argument, e.g.:
 
     ./get_sou_riksdagen.py https://data.riksdagen.se/dataset/dokument/sou-2005-2009.json.zip true
     
 ...then, if indexing succeeded, the JSON file will be moved from `files-queue` to `files`.
 
 ### Run Flask app
 
Make sure static directories exist and then generate CSS:
 
     mkdir -p static/css
     sassc scss/style.scss static/css/style.css
 
 If the ElasticSearch server is up and running, everything should now Just Work (tm):
 
     ./app.py
     
You probably want to use something like [gunicorn](https://gunicorn.org/) or [bjoern](https://github.com/jonashaag/bjoern)
in production, though. Gunicorn is specified by `requirements.txt`, so you can simply do:

    gunicorn app:app

### Misc.

Riksdagen's open data is missing the titles for nearly all of the 1000+ SOUs published 2000-2004. Which means
these titles are missing on both Riksdagen's own search service, as well as on LiU's service. I noticed that
lagen.nu has easily parsed lists with correct titles for all SOUs, so `get_sou_titles.py` fetches these and
puts them in a JSON file (`sou_names.json`), which is then used by `get_sou_riksdagen.py` for the titles for
SOUs from this range of years.

### Contact & credits

Written by [Anders Jensen-Urstad](https://anders.unix.se) for [Dataskydd.net](https://dataskydd.net).

Apart from ElasticSearch, Flask and various other Python modules specified in `requirements.txt`, CJ Patoilo's
minimalist CSS framework [Milligram](https://milligram.io/) is used.