import codecs
import re
import csv
import json
import html
from questionscraper.spiders.helper import load_jl
from os import path


def read_tsv(path):
    with open(path) as tsvfile:
        reader = csv.DictReader(tsvfile, delimiter='\t')
        rows = list(reader)
    return rows


def answer_from_concat(answer_concat):
    parts = answer_concat.split('-----')
    urls = [parts[i].strip() for i in range(1, len(parts), 2)]
    _answers = [parts[i].strip() for i in range(2, len(parts), 2)]
    #answers = [[a.split('||')[0].split('##')[-1].strip() for a in re.split('\|\|\s+##', a_con)] for a_con in _answers]
    #_answers = re.split('\|\|\s+##', parts[2])
    return {urls[i]: _answers[i] for i in range(len(urls))}


def answers_from_intents(intents):
    for intent in intents:
        for q in intent['questions']:
            for a in q['answers']:
                a['question'] = q
                yield a


def prepare_for_html(s):
    #s = html.escape(s)
    s = re.sub(r'\[\s*([^\]]+)\s*\]', r'<a href="\1" target="_blank">\1</a>', s)
    return s


def intents_split_to_dynamicContent(intents_split, answers_all, num_posts, num_queries, query_nbr=None):
    posts = [{'identifier': 'Post%i' % (i+1), 'type': 'TEXT', 'values': []} for i in range(num_posts)]
    query = {'identifier': 'query', 'type': 'TEXT', 'values': []}
    for i, intent_id in enumerate(intents_split):
        if i == num_queries:
            break
        if query_nbr is not None and i != query_nbr:
            continue
        query['values'].append('<div class=\"query\">%s</div>' % prepare_for_html(intents_split[intent_id]['Intent-Text']))
        current_answers_split_sorted = sorted([(url, intents_split[intent_id]['answers_split'][url]) for url in
                                               intents_split[intent_id]['answers_split']], key=lambda x: len(''.join(x[1])))

        for post_pos in range(num_posts):
            new_answer = ''
            #keys = list(intents_split[intent_id]['answers_split'].keys())
            if post_pos < len(current_answers_split_sorted):
                answer_full = answers_all[current_answers_split_sorted[post_pos][0]]
                answer_splits = '<ul>%s</ul>' % html.escape(current_answers_split_sorted[post_pos][1])
                # add li elements
                answer_splits = answer_splits.replace('##', '<li>').replace('||', '</li>')
                # replace links with captions
                answer_splits = re.sub(r'\[LINK\]{{\s*([^}]+)\s*}}{{\s*([^}]+)\s*}}', r'<a href="\1" target="_blank">\2</a>', answer_splits)
                # replace remaining links with captions
                answer_splits = re.sub(r'\[LINK\]{{\s*([^}]+)\s*}}', r'<a href="\1" target="_blank">\1</a>', answer_splits)
                # replace profile links (must have captions)
                answer_splits = re.sub(r'\[LINK_PROFILE\]{{\s*([^}]+)\s*}}{{\s*([^}]+)\s*}}', r'<a class="profile-link" href="\1" target="_blank">\2</a>', answer_splits)
                # replace images
                answer_splits = re.sub(r'\[IMAGE\]{{\s*([^}]+)\s*}}', r'<img src="\1" />', answer_splits)

                # replace quotes. That separates the list (add closing and opening ul tags)
                answer_splits = re.sub(r'\[BLOCKQUOTE\]{{\s*([^}]+)\s*}}', r'</ul><blockquote>\1</blockquote><ul>', answer_splits)

                #replace emojies
                answer_splits = answer_splits.replace('🙂', '').replace('💕', '').replace('😀', '')

                new_answer = '<div class="answer-content">%s</div>' % answer_splits
                question_title = '<div class="question-title">%s</div>' % answer_full['question']['title']

                accepted_by = answer_full.get('solution_accepted_by', None)
                accepted_by_text = answer_full.get('solution_accepted_by_text', None)
                if accepted_by:
                    new_answer = '<div class="answer solution"><div class="solution-header">Lösung akzeptiert von %s %s</div>%s</div>' \
                                 % (accepted_by, accepted_by_text, new_answer)
                else:
                    new_answer = '<div class="answer">%s</div>' % new_answer
                new_answer = question_title + new_answer
            posts[post_pos]['values'].append(new_answer)

    return posts + [query]


if __name__ == "__main__":
    #soup = html.escape('k\u00f6nnen')
    #print(soup)
    path_base = 'scrape_10'
    tsv_sentences_fn = 'ARNE_LEO-Training-Example-Summaries-Intents.tsv'
    intents_all_fn = 'intents_questions_10_merged.jl'
    column_split_content = 'answers_plain_marked_relevant_NEW'

    intents = load_jl(path.join(path_base, intents_all_fn))
    answers_all = {a['url']: a for a in answers_from_intents(intents)}
    #print('stats for answers_all:')
    #print('distinct posts: %i' % len(answers_all))
    #print('distinct posts with image: %i' % len([url for url in answers_all if answers_all[url]['has_image']]))
    #print('distinct posts with quote: %i' % len([url for url in answers_all if answers_all[url]['has_quote']]))
    #print('distinct posts with link: %i' % len([url for url in answers_all if answers_all[url]['has_link']]))

    intents_split = {intent['Intent-ID']: {'Intent-Text': intent['Intent-Text'], 'answers_split': answer_from_concat(intent[column_split_content])} for intent in read_tsv(path.join(path_base, tsv_sentences_fn))}
    with open(path.join('summary', 'Summary.template.json')) as f:
        summary = json.load(f)
    summary['dynamicContent'] = intents_split_to_dynamicContent(intents_split, answers_all, num_posts=10, num_queries=10)#, query_nbr=6)
    #with open('scrape_10/Summary_content.json', 'w') as f:
    with codecs.open(path.join(path_base, 'Summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
        #f.write(json_string)
        f.flush()

