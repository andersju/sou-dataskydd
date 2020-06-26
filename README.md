# sou.dataskydd.net

This repo contains the code for [sou.dataskydd.net](https://sou.dataskydd.net), a service that lets you do
full-text search on all the [_Swedish Government Official Reports_](https://en.wikipedia.org/wiki/Statens_offentliga_utredningar)
(Statens Offentliga Utredningar, SOU) that have been published from 1922 to
today.

Linköping University (LiU) provides a [similar service](https://ep.liu.se/databases/sou/default.aspx),
but 1) it doesn't provide highlighted extracts, and 2) it cannot sort by relevance, making it
considerably less useful than it could have been. So, I figured I could hack up something better with a little
Flask and Elasticsearch.

There are three parts: a couple of scripts to fetch SOUs and turn them into appropriately formatted JSON
files; a script to ingest said files into Elasticsearch; and a single-file Flask app for the web service.
As of now the code is "quick weekend project" quality, but perhaps that will change.

## Requirements

* Python 3.6+
* ElasticSearch 7.x

## Getting started

Clone this repository. Make sure Elasticsearch is up and running. Default configuration is fine.

Use virtualenv, venv or similar to install the required Python modules (`pip install -r requirements.txt`).

### Fetch files

There are two sources for SOUs. KB (National Library of Sweden) [provides OCR'd PDFs](https://regina.kb.se/sou/)
of the 6129 SOUs published between 1922 and 1999. Riksdagen - the Swedish parliament - has everything from 1990
and onwards in various formats (XML, JSON, SQL, etc.) on [data.riksdagen.se](https://data.riksdagen.se/data/dokument/),
or so they claim. LiU, for their part, uses KB's material for 1922-1996 and the parliament's open data for 1997 and onwards.
Turns out data.riksdagen.se's 1990-1999 dataset (as of 2020-06-26) does not have anything from 1990-1993, only a few
documents from 1994-1996, and is missing quite a few documents from 1997-1998 and about 20 from 1999. So, sou.dataskydd.net
uses KB's scanned PDFs for the period 1922-1999.

`get_sou_kb.py` scrapes [KB's sou page](https://regina.kb.se/sou/). It figures out SOU number/year/title/URL/URN,
downloads the PDF, extracts the text, dumps the aforementioned metadata and text into a JSON file in `files-queue/`
and then removes the PDF to save space (some scanned SOUs can be hundreds of MB!). This can take a *long* time.

`get_sou_riksdagen.py` takes a URL to a zip with JSON files as an argument, e.g.:

    ./get_sou_riksdagen.py https://data.riksdagen.se/dataset/dokument/sou-2005-2009.json.zip

The zip file is downloaded to a temporary directory and extracted. The script goes through each JSON file and
extracts various data (number, year, title, URL, etc). If the SOU already exists in `files/`, it's skipped;
otherwise, the full text (which is in HTML) is extracted from the JSON and mangled through BeautifulSoup to get
rid of HTML elements. The data is then dumped into a new JSON file in `files-queue/`.

`ingest.py` takes a directory an argument. It first creates an Elasticsearch index for the SOUs, if it
doesn't already exist. It goes through each JSON file in the specified directory and indexes it. The document
 `_id` used is specified by the JSON file, so indexing the same document twice is fine - it'll just be overwritten.

 If `ingest.py` is called with `true` as its second argument, e.g.:

     ./get_sou_riksdagen.py https://data.riksdagen.se/dataset/dokument/sou-2005-2009.json.zip true

 ...then, if indexing succeeded, the JSON file will be moved from `files-queue` to `files`.

 ### Run Flask app

Make sure static directories exist and then generate CSS:

     mkdir -p static/css
     sassc scss/style.scss static/css/style.css

 If the Elasticsearch server is up and running, everything should now Just Work (tm):

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

### Complete recipe

Mainly for my own use. Ansible, Docker et al could be of use, but let's stay simple here. Assumptions:

* Fresh minimal Ubuntu 20.04 server. No users created (yet) except root. Typical regular VPS/dedicated server.
* DNS record set up (sou.dataskydd.net has an A record pointing to the server)

```sh
# On server, as root:
adduser andersju
usermod -aG sudo andersju

# On local computer:
ssh-copy-id andersju@sou.dataskydd.net
# Make sure logging in with pubkey works:
ssh andersju@sou.dataskydd.net

# Back on the server:
sudo vi /etc/ssh/sshd_config # set PasswordAuthentication to no
sudo systemctl restart sshd

# Install ufw
sudo apt install ufw
# Only ssh, http and https ports should be open
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
# Enable firewall
sudo ufw enable

# Install other necessary/useful things
sudo apt install git tmux python3-pip python3-venv sassc

# Install Elasticsearch as per Elasticsearch 7.8 docs:
# https://www.elastic.co/guide/en/elasticsearch/reference/7.8/deb.html#deb-repo
sudo apt-get install apt-transport-https
echo "deb https://artifacts.elastic.co/packages/7.x/apt stable main" | sudo tee -a /etc/apt/sources.list.d/elastic-7.x.list
sudo apt-get update && sudo apt-get install elasticsearch
# In case of complaint about missing public key:
# sudo apt install gnupg
# sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys <key>
# ...and then try apt-get update/install again
sudo systemctl enable elasticsearch
sudo systemctl start elasticsearch

# Create user that'll run the Flask app and fetch/ingest SOUs
sudo useradd -m sou -s /bin/bash
# Become sou
sudo -i -u sou
# Create virtual environment
python3 -m venv souenv
source souenv/bin/activate
pip install wheel
git clone https://github.com/andersju/sou-dataskydd.git
cd sou-dataskydd
pip install -r requirements.txt
mkdir -p static/css
sassc scss/style.scss static/css/style.css
# Confirm that it works:
gunicorn app:app # ...and then ctrl-c
```

Create a systemd service, `/etc/systemd/system/sou.service`, with the following:
```
[Unit]
Description=SOU

[Service]
Type=simple
User=sou
Group=sou
Restart=always
WorkingDirectory=/home/sou/sou-dataskydd
Environment="PATH=/home/sou/souenv/bin"
ExecStart=/home/sou/souenv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Now, as regular user (not sou!), try it:
```sh
sudo systemctl start sou
sudo systemctl status sou # to make sure things look fine
sudo systemctl enable sou
```

At this point I'd normally install nginx for use as a reverse proxy, and certbot for Let's Encrypt certificates,
but let's try [Caddy](https://caddyserver.com/) (a web server that handles Let's Encrypt certs automatically)
for a change:

```sh
# From https://caddyserver.com/docs/download
echo "deb [trusted=yes] https://apt.fury.io/caddy/ /" \
    | sudo tee -a /etc/apt/sources.list.d/caddy-fury.list
sudo apt update
sudo apt install caddy
# Caddy should've started automatically. Verify: curl localhost
```

Edit `/etc/caddy/Caddyfile` and make sure it has only the following lines:
```
sou.dataskydd.net
reverse_proxy 127.0.0.1:5000
```

Then `sudo systemctl restart caddy` et voilà, https://sou.dataskydd.net should work in a moment, certificate
and all, and with automatic redirect from http://. Neat!

All that's left is to fetch SOU files and ingest them into Elasticsearch. For example, as user sou:

```sh
source ~/souenv/bin/activate
cd ~/sou-dataskydd
python get_sou_riksdagen.py http://data.riksdagen.se/dataset/dokument/sou-2015-.json.zip
python ingest.py files-queue true
```

### TODO/ideas

* data.riksdagen.se has an XML feed. Use it for updates?
*

### Contact & credits

Written by [Anders Jensen-Urstad](https://anders.unix.se) for [Dataskydd.net](https://dataskydd.net).

Apart from Elasticsearch, Flask and various other Python modules specified in `requirements.txt`, CJ Patoilo's
minimalist CSS framework [Milligram](https://milligram.io/) is used.