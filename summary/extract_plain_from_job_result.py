import csv
import json
import re

import plac
from bs4 import BeautifulSoup

COLUMN_QUERY = 'DynamicContent.query'
COLUMN_POST_REGEX = r'DynamicContent.Post\d+$'


def html_post_to_plain(post):
    sentences = BeautifulSoup(post, 'html.parser').select('.sentence')
    text = ' '.join([s.text.strip() for s in sentences if s.select_one('img') is None and s.text.strip() != ''])
    return text


def main(tsv_in, json_out):
    """
    Takes a Crowdee Job result tsv, gets all queries and posts and removes html annotations.
    Only sentences (marked with <div class="sentence">) that do not contain <img> tags are taken from the post columns.

    :param tsv_in: Path to Crowdee Job result tsv file
    :param json_out: Path to output json
    :return:
    """
    rows = list(csv.DictReader(open(tsv_in, encoding='utf8'), delimiter='\t'))
    # sanity check that posts are same for same query
    html_data = {}
    for row in rows:
        query = row[COLUMN_QUERY]
        post_keys = sorted([k for k in row if re.match(COLUMN_POST_REGEX, k)])
        posts = [row[k] for k in post_keys]
        prev_posts = html_data.get(query, None)
        assert not prev_posts or posts == prev_posts, 'posts do not equal'
        html_data[query] = posts

    data = [{'query': BeautifulSoup(html_query, 'html.parser').text,
             'text': '\n\n'.join([html_post_to_plain(p) for p in html_data[html_query] if p.strip() != ''])}
            for html_query in html_data]

    json.dump(data, open(json_out, 'w', encoding='utf8'), indent=4, ensure_ascii=False)
    print('done')


if __name__ == "__main__":
    plac.call(main)
