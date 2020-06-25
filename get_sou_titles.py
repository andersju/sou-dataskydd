#!/usr/bin/env python
# Python 3.6+

import json
import urllib.request
from bs4 import BeautifulSoup

sou_dict = {}

for year in range(1923, 2021):
    print(year)
    with urllib.request.urlopen(f"https://lagen.nu/dataset/forarbeten?sou={year}") as url:
        data = url.read().decode()

    soup = BeautifulSoup(data, 'html.parser')
    for dt in soup.findAll('dt'):
        sou_number = dt.text.strip()
        sou_title = dt.find_next_sibling('dd').text.strip()
        print(f"Adding {sou_number} {sou_title}")
        sou_dict[sou_number] = sou_title

with open('sou_names.json', 'w') as f:
    json.dump(sou_dict, f, ensure_ascii=False, indent=4, sort_keys=True)
