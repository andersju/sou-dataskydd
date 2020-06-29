#!/usr/bin/env python
# Python 3.6+

import elasticsearch
from flask import Flask, request, render_template, send_from_directory
from flask_paginate import Pagination
from elasticsearch import Elasticsearch
from elasticsearch_dsl import FacetedSearch, RangeFacet
from elasticsearch_dsl.connections import connections
from bleach import clean
from markupsafe import Markup
from operator import itemgetter

connections.create_connection(hosts=['localhost'])
es = Elasticsearch()
app = Flask(__name__, static_folder='static')


# https://stackoverflow.com/a/14625619
@app.route('/robots.txt')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


# https://stackoverflow.com/a/27119458
@app.template_filter('clean')
def do_clean(text, **kw):
    """Perform clean and return a Markup object to mark the string as safe.
    This prevents Jinja from re-escaping the result."""
    return Markup(clean(text, **kw))


@app.template_filter('build_query_string')
def build_query_string(query_dict):
    new_params = []
    for key, itemlist in query_dict.lists():
        for item in itemlist:
            if key in ['q', 'year']:
                new_params.append(f"{key}={item}")
    return "&".join(new_params)


class SouSearch(FacetedSearch):
    index = 'sou'  # Index to search
    fields = ['number^2', 'title^3', 'full_text']  # Fields to search

    facets = {
        'year': RangeFacet(field='year', ranges=[
            ('1922-1929', (1922, 1930)),
            ('1930-1939', (1930, 1940)),
            ('1940-1949', (1940, 1950)),
            ('1950-1959', (1950, 1960)),
            ('1960-1969', (1960, 1970)),
            ('1970-1979', (1970, 1980)),
            ('1980-1989', (1980, 1990)),
            ('1990-1999', (1990, 2000)),
            ('2000-2009', (2000, 2010)),
            ('2010-2019', (2010, 2020)),
            ('2020-2029', (2020, 2030)),
            ]),
    }

    def highlight(self, search):
        return search.highlight('title', 'full_text', fragment_size=150, number_of_fragments=4)

    def search(self):
        s = super(SouSearch, self).search()
        # Don't include the actual full SOU text in result; we only need the highlighted extract
        return s.source(excludes=["full_text"])

    def query(self, search, query):
        if query:
            if self.fields:
                return search.query('query_string', fields=self.fields, query=query, default_operator='and')
            else:
                return search.query('query_string', query=query, default_operator='and')
        return search


@app.route('/')
def index():
    hits_per_page = 12

    q = request.args.get('q', '')
    year = request.args.getlist('year')

    # If there's no query and no sort option explicitly set - e.g. if user just
    # arrived - sort by year/number in descending order
    if not q and not request.args.get('sort_by'):
        sort_by = 'number_sort'
    else:
        sort_by = request.args.get('sort_by', '_score')
    order_by = request.args.get('order_by', 'desc')

    # Sort by score (relevance) by default, and don't let users sort by
    # anything other than what's specified belove
    if sort_by not in ['number_sort', 'title_sort', '_score']:
        sort_by = '_score'

    sort = [{sort_by: {'order': order_by}}]

    # The following is to make sure we can create appropriate sort links.
    # If current sort is asc, then clicking again should make it desc, and
    # vice versa.
    if request.args.get('order_by') == 'asc':
        order_by_next = 'desc'
    elif request.args.get('order_by') == 'desc':
        order_by_next = 'asc'
    else:
        order_by_next = 'asc'

    # Display name, actual sort field, default order
    sort_options = [
        ('relevans', '_score', 'desc'),
        ('år och nummer', 'number_sort', 'asc'),
        ('titel', 'title_sort', 'asc'),
    ]

    # Dictionary of possible facets
    filters = {'year': year}

    try:
        # Figure out total number of hits (but don't actually fetch them)
        rs_count = SouSearch(q, filters=filters, sort=sort)
        response_count = rs_count[0:0].execute()
        # What page are we on?
        page = request.args.get('page', type=int, default=1)
        # Create a pagination object based on the number of hits and the current page number
        pagination = Pagination(page=page, total=response_count.hits.total.value,
                                record_name='sou', per_page=hits_per_page, bs_version=4, inner_window=1, outer_window=0)

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

        return render_template("sou/front.html", response=response, total=response.hits.total,
                               pagination=pagination, q=q, sort_options=sort_options, sort_by=sort_by,
                               order_by=order_by, order_by_next=order_by_next, sou_from=sou_from+1, sou_to=sou_to)
    except elasticsearch.exceptions.ConnectionError:
        return render_template("sou/error.html", error_title='Ett fel uppstod', error_message='Kunde inte ansluta till sökmotorn.'), 500
    except elasticsearch.exceptions.RequestError:
        return render_template("sou/error.html", error_title='Ogiltig sökfråga', error_message='Se över söksträngen och prova på nytt.'), 200
    except:
        return render_template("sou/error.html", error_message='Något gick galet.'), 500


if __name__ == '__main__':
    app.run()
