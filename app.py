#!/usr/bin/env python
# Python 3.6+

import elasticsearch
from flask import Flask
from flask import request
from flask import render_template
from flask_paginate import Pagination
from elasticsearch import Elasticsearch
from elasticsearch_dsl import FacetedSearch, RangeFacet
from elasticsearch_dsl.connections import connections
from urllib.parse import quote
from bleach import clean
from markupsafe import Markup
from operator import itemgetter

connections.create_connection(hosts=['localhost'])
es = Elasticsearch()
app = Flask(__name__)


# https://stackoverflow.com/a/27119458
@app.template_filter('clean')
def do_clean(text, **kw):
    """Perform clean and return a Markup object to mark the string as safe.
    This prevents Jinja from re-escaping the result."""
    return Markup(clean(text, **kw))


@app.template_filter('url_encode')
def url_encode(url):
    return quote(url)


@app.template_filter('build_query_string')
def build_query_string(query_dict):
    new_params = []
    for key, itemlist in query_dict.lists():
        for item in itemlist:
            if key in ['q', 'year']:
                new_params.append(f"{key}={item}")
    return "&".join(new_params)


class SouSearch(FacetedSearch):
    # Index to search
    index = 'sou'
    # Fields to search
    fields = ['number^2', 'title^3', 'full_text']

    facets = {
        'year': RangeFacet(field='year', ranges=[
            ('1922-1929', (1922, 1929)),
            ('1930-1939', (1930, 1939)),
            ('1940-1949', (1940, 1949)),
            ('1950-1959', (1950, 1959)),
            ('1960-1969', (1960, 1969)),
            ('1970-1979', (1970, 1979)),
            ('1980-1989', (1980, 1989)),
            ('1990-1999', (1990, 1999)),
            ('2000-2009', (2000, 2009)),
            ('2010-2019', (2010, 2019)),
            ('2020-2029', (2020, 2029)),
            ]),
    }

    def highlight(self, search):
        return search.highlight('title', 'full_text', fragment_size=150, number_of_fragments=4)

    def search(self):
        s = super(SouSearch, self).search()
        # Don't include the actual full SOU text in result; we only need the highlighted extract
        return s.source(excludes=["full_text"])


@app.route('/')
def index():
    hits_per_page = 12

    q = request.args.get('q', '')
    year = request.args.getlist('year')

    if not q and not request.args.get('sort_by'):
        sort_by = 'number_sort'
    else:
        sort_by = request.args.get('sort_by', '_score')
    order_by = request.args.get('order_by', 'desc')

    if sort_by not in ['number_sort', 'title_sort', '_score']:
        sort_by = '_score'

    sort = [{sort_by: {'order': order_by}}]

    if request.args.get('order_by') == 'asc':
        order_by_next = 'desc'
    elif request.args.get('order_by') == 'desc':
        order_by_next = 'asc'
    else:
        order_by_next = 'asc'

    sort_options = [
        ('relevans', '_score', 'desc'),
        ('år och nummer', 'number_sort', 'asc'),
        ('titel', 'title_sort', 'asc'),
    ]

    filters = {'year': year}

    try:
        # Figure out total number of hits (but don't actually fetch them)
        rs_count = SouSearch(q, filters=filters, sort=sort)
        response_count = rs_count[0:0].execute()
        # What page are we on?
        page = request.args.get('page', type=int, default=1)
        # Create a pagination object based on the number of hits and the current page number
        pagination = Pagination(page=page, total=response_count.hits.total.value, record_name='sou', per_page=hits_per_page, bs_version=4)

        # Make sure page number stays within the realm of possibility
        if page > pagination.total_pages > 0:
            page = pagination.total_pages

        # Figure out which results we should fetch from ES
        sou_from = (page-1)*hits_per_page
        sou_to = page*hits_per_page

        # Now fetch them
        rs = SouSearch(q, filters=filters, sort=sort)
        response = rs[sou_from:sou_to].execute()

        # Sort year facet by year (asc) rather than by total number of hits
        # TODO: let ES do that instead
        response.facets.year = [t for t in response.facets.year if t[1] > 1]
        response.facets.year = sorted(response.facets.year, key=itemgetter(0), reverse=True)

        return render_template("sou/front.html", response=response, total=response.hits.total, pagination=pagination, q=q, sort_options=sort_options, sort_by=sort_by, order_by=order_by, order_by_next=order_by_next, sou_from=sou_from+1, sou_to=sou_to)
    except elasticsearch.exceptions.ConnectionError:
        return render_template("sou/error.html", error_message='Kunde inte ansluta till sökmotorn.'), 500
    except:
        return render_template("sou/error.html", error_message='Något gick galet.'), 500


if __name__ == '__main__':
    app.run()
