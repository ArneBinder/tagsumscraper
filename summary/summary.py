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
    answers = [[a.split('||')[0].split('##')[-1].strip() for a in re.split('\|\|\s+##', a_con)] for a_con in _answers]
    #_answers = re.split('\|\|\s+##', parts[2])
    return {urls[i]: answers[i] for i in range(len(urls))}


def answers_from_intents(intents):
    for intent in intents:
        for q in intent['questions']:
            for a in q['answers']:
                a['question'] = q
                yield a


def prepare_for_html(s):
    s = html.escape(s)
    s = re.sub(r'\[\s*([^\]]+)\s*\]', r'<a href="\1" target="_blank">\1</a>', s)
    return s


def intents_split_to_dynamicContent(intents_split, answers_all, num_posts):
    posts = [{'identifier': 'Post%i' % (i+1), 'type': 'TEXT', 'values': []} for i in range(num_posts)]
    query = {'identifier': 'query', 'type': 'TEXT', 'values': []}
    for intent_id in intents_split:
        query['values'].append('<div class=\"query\">%s</div>' % prepare_for_html(intents_split[intent_id]['Intent-Text']))
        for i in range(num_posts):
            new_answer = ''
            keys = list(intents_split[intent_id]['answers_split'].keys())
            if i < len(keys):
                answer_full = answers_all[keys[i]]
                new_answer = '</li><li>'.join([prepare_for_html(s) for s in intents_split[intent_id]['answers_split'][keys[i]]])
                new_answer = '<ul><li>%s</li></ul>' % new_answer
                new_answer = '<div class="answer-content">%s</div>' % new_answer
                question_title = '<div class="question-title">%s</div>' % answer_full['question']['title']


                accepted_by = answer_full.get('solution_accepted_by', None)
                accepted_by_text = answer_full.get('solution_accepted_by_text', None)
                if accepted_by:
                    new_answer = '<div class="answer solution"><div class="solution-header">Lösung akzeptiert von %s %s</div>%s</div>' \
                                 % (accepted_by, accepted_by_text, new_answer)
                else:
                    new_answer = '<div class="answer">%s</div>' % new_answer
                new_answer = question_title + new_answer
            posts[i]['values'].append(new_answer)
    return posts + [query]


if __name__ == "__main__":
    #soup = html.escape('k\u00f6nnen')
    #print(soup)
    path_base = 'scrape_10'
    tsv_sentences_fn = 'ARNE_LEO-Training-Example-Summaries-Intents.tsv'
    intents_all_fn = 'intents_questions_10_merged.jl'

    intents = load_jl(path.join(path_base, intents_all_fn))
    answers_all = {a['url']: a for a in answers_from_intents(intents)}
    #print('stats for answers_all:')
    #print('distinct posts: %i' % len(answers_all))
    #print('distinct posts with image: %i' % len([url for url in answers_all if answers_all[url]['has_image']]))
    #print('distinct posts with quote: %i' % len([url for url in answers_all if answers_all[url]['has_quote']]))
    #print('distinct posts with link: %i' % len([url for url in answers_all if answers_all[url]['has_link']]))

    intents_split = {intent['Intent-ID']: {'Intent-Text': intent['Intent-Text'], 'answers_split': answer_from_concat(intent['answers_plain_marked_relevant'])} for intent in read_tsv(path.join(path_base, tsv_sentences_fn))}
    with open(path.join('summary', 'Summary.template.json')) as f:
        summary = json.load(f)
    summary['dynamicContent'] = intents_split_to_dynamicContent(intents_split, answers_all, 10)
    #with open('scrape_10/Summary_content.json', 'w') as f:
    with codecs.open(path.join(path_base, 'Summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
        #f.write(json_string)
        f.flush()

