import codecs
import logging
import os
import re
import csv
import json
import html
import plac
from questionscraper.spiders.helper import load_jl
from os import path
from bs4 import BeautifulSoup
from statistics import median


FORMAT_LIST = 'list'
FORMAT_CHECKBOXES = 'checkboxes'
FORMAT_PARAGRAPHS = 'paragraphs'

ANSWERS_ALL = 'answers_all'
ANSWERS_SPLIT = 'answers_split'
INTENT_ID = 'Intent-ID'
INTENT_TEXT = 'Intent-Text'
QUESTIONS = 'questions'
QUESTION = 'question'
TITLE = 'title'
ANSWERS = 'answers'
URL = 'url'

#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
logging.getLogger().setLevel(logging.DEBUG)


def read_tsv(path):
    with open(path) as tsvfile:
        reader = csv.DictReader(tsvfile, delimiter='\t')
        rows = list(reader)
    return rows


def answer_from_concat(answer_concat):
    #parts = answer_concat.split('-----')
    #parts = re.split(r'(^|\n)-----\s', answer_concat)
    parts = re.split(r'(^\s*|\s+)-----\s+([^\s]+) -----\s', answer_concat)
    urls = [parts[i].strip() for i in range(2, len(parts), 3)]
    _answers = [parts[i].strip() for i in range(3, len(parts), 3)]
    #answers = [[a.split('||')[0].split('##')[-1].strip() for a in re.split('\|\|\s+##', a_con)] for a_con in _answers]
    #_answers = re.split('\|\|\s+##', parts[2])
    try:
        res = {urls[i]: _answers[i] for i in range(len(urls))}
    except Exception as e:
        logging.error('parts: %s' % parts)
        raise e
    return res


def answers_from_intents(intents):
    for intent in intents:
        for q in intent[QUESTIONS]:
            for a in q[ANSWERS]:
                a[QUESTION] = q
                yield a


def answers_dict_from_intent(intent):
    res = {}
    for q in intent[QUESTIONS]:
        for a in q[ANSWERS]:
            if a[URL] in intent['relevant_answer_links']:
                a[QUESTION] = q
                res[a[URL]] = a
    return res


def prepare_for_html(content, format_as=FORMAT_LIST):
    if format_as == FORMAT_LIST:
        s = '<ul>%s</ul>' % html.escape(content)
        # add li elements
        s = s.replace('##', '<li><span class="sentence">').replace('||', '</span></li>')
    elif format_as == FORMAT_PARAGRAPHS:
        # s = content.replace('##', '<p><input type="checkbox" name="%s">' % meta['checkbox_name']).replace('||', '</p>')
        s = content.replace('##', '<p><span class="sentence">').replace('||', '</span></p>')
    elif format_as == FORMAT_CHECKBOXES:
        s_split = content.split('||')
        s = ''
        for i in range(len(s_split)):
            if s_split[i].strip() != '':
                if '[IMAGE]' in s_split[i] in s_split[i]:
                    s += s_split[i].replace('##', '<p><input type="checkbox" name="check" disabled>') + '</p>'
                else:
                    s += s_split[i].replace('##', '<p><input type="checkbox" name="check">') + '</p>'
        #s = content.replace('##', '<p><input type="checkbox" name="check">').replace('||', '</p>')
        #s = content.replace('##', '<p><span class="sentence">').replace('||', '</span></p>')
    else:
        s = html.escape(content)
    # replace links with captions
    s = re.sub(r'\[LINK\]{{\s*([^}]+)\s*}}{{\s*([^}]+)\s*}} *', r'<a href="\1" target="_blank">\2</a> ',
                           s)
    # replace remaining links with captions
    s = re.sub(r'\[LINK\]{{\s*([^}]+)\s*}} *', r'<a href="\1" target="_blank">\1</a> ', s)
    # replace profile links (must have captions)
    s = re.sub(r'\[LINK_PROFILE\]{{\s*([^}]+)\s*}}{{\s*([^}]+)\s*}}',
                           r'<a class="profile-link" href="\1" target="_blank">\2</a>', s)
    # replace images
    s = re.sub(r'\[IMAGE\]{{\s*([^}]+)\s*}}', r'<img src="\1" />', s)

    # replace quotes. That separates the list (add closing and opening ul tags)
    if '[BLOCKQUOTE]' in s:
        s = re.sub(r'schrieb:\s*', 'schrieb:<br/>', s)
    # interrupt the list for blockquotes, if lists are is used
    if format_as == FORMAT_LIST:
        s = re.sub(r'\[BLOCKQUOTE\]{{\s*([^}]+)\s*}}', r'</ul><blockquote>\1</blockquote><ul>', s)
    else:
        s = re.sub(r'\[BLOCKQUOTE\]{{\s*([^}]+)\s*}}', r'<blockquote>\1</blockquote>', s)

    # replace emojis
    # TODO: get list of all emojis
    # see http://graphemica.com/%F0%9F%98%80
    #s = s.replace('🙂', '&#128578;').replace('💕', '&#128578;').replace('😀', '&#128578;')
    for emoji in ['🙂', '💕', '😀']:
        s = s.replace(emoji, '&#%i;' % ord(emoji))
    #s = s.replace('🙂', '').replace('💕', '').replace('😀', '')
    return s


def intents_split_to_dynamicContent(intents, nbr_posts, dynamicContent_loaded=None,
                                    only_intent_ids=None, format_as=FORMAT_LIST):
    if dynamicContent_loaded is None:
        dynamicContent_loaded = {}
    posts = [{'identifier': 'Post%i' % (i+1), 'type': 'TEXT', 'values': []} for i in range(nbr_posts)]
    if 'query' in dynamicContent_loaded:
        logging.warning('"query" is already in dynamicContent, OVERWRITE it.')
    if 'Post1' in dynamicContent_loaded:
        logging.warning('"Post1" is already in dynamicContent, OVERWRITE all "Post<n>".')
    # delete posts from loaded
    for p in posts:
        if p['identifier'] in dynamicContent_loaded:
            del dynamicContent_loaded[p['identifier']]
    query = {'identifier': 'query', 'type': 'TEXT', 'values': dynamicContent_loaded['query']['values'] if 'query' in dynamicContent_loaded else []}
    all_l = []
    for intent in intents:
        #if i == max_queries:
        #    break
        if only_intent_ids is not None and intent[INTENT_ID] not in only_intent_ids:
            continue
        query['values'].append('<div class=\"query\">%s</div>' % prepare_for_html(intent[INTENT_TEXT]))

        current_answers_split = [(url, intent[ANSWERS_SPLIT][url]) for url in intent[ANSWERS_SPLIT]]
        answers_html = []
        for current_url, current_answer in current_answers_split:
            try:
                answer_full = intent[ANSWERS_ALL][current_url]
                answer_splits = prepare_for_html(re.sub(r'\s*\(\d+\)\s*$', '', current_answer),
                                                 format_as=format_as)

                new_answer = '<div class="answer-content">%s</div>' % answer_splits
                question_title = '<div class="question-title">%s</div>' % answer_full[QUESTION][TITLE]

                accepted_by = answer_full.get('solution_accepted_by', None)
                accepted_by_text = answer_full.get('solution_accepted_by_text', None)
                if accepted_by:
                    new_answer = '<div class="answer solution"><div class="solution-header">Lösung akzeptiert von %s %s</div>%s</div>' \
                                 % (accepted_by, accepted_by_text, new_answer)
                else:
                    new_answer = '<div class="answer">%s</div>' % new_answer
                answers_html.append(question_title + new_answer)
            except Exception as e:
                logging.error('intent: %s,\tanswer url: %s' % (intent[INTENT_ID], current_url))
                raise e
        answers_html_with_parsed_text = [(html_doc, BeautifulSoup(html_doc, 'html.parser').get_text()) for html_doc in answers_html]
        ## use character count for sorting
        #answers_html_sorted = sorted(answers_html_with_parsed_text, key=lambda h_with_l: len(h_with_l[1]), reverse=True)
        # sort by umber of block elements, but give <div>s more weight
        answers_html_sorted = sorted(answers_html_with_parsed_text, key=lambda h_with_l: 1.5 * h_with_l[0].count('<div') + h_with_l[0].count('<p') + h_with_l[0].count('<li'), reverse=True)
        # use words count as length
        l = sum(map(lambda x: len(x[1].strip().split()), answers_html_with_parsed_text))
        for post_pos in range(nbr_posts):
            if post_pos < len(answers_html_sorted):
                posts[post_pos]['values'].append(answers_html_sorted[post_pos][0])
            else:
                posts[post_pos]['values'].append('')
        all_l.append(l)
    logging.info('lengths of all posts for all %i intents: %s' % (len(all_l), str(all_l)))
    new_dynamic_content = {dc['identifier']: dc for dc in posts + [query]} #, summary_good, summary_bad]}
    new_dynamic_content.update(dynamicContent_loaded)
    return list(new_dynamic_content.values())


def create_multiple_jobs(intents, summary, summary_out_fn, format_as):
    nbr_words_query_median = median((len(intent[INTENT_TEXT].split()) for intent in intents))
    nbr_words_posts_median = median((intent['nbr_words_relevant'] for intent in intents))

    intents_selected = [[], [], [], []]
    for intent in intents:
        nbr_words_query = len(intent[INTENT_TEXT].split())
        nbr_words_posts = intent['nbr_words_relevant']
        if nbr_words_query < nbr_words_query_median and nbr_words_posts < nbr_words_posts_median:
            intents_selected[0].append(intent)
        elif nbr_words_query < nbr_words_query_median and nbr_words_posts >= nbr_words_posts_median:
            intents_selected[1].append(intent)
        elif nbr_words_query >= nbr_words_query_median and nbr_words_posts < nbr_words_posts_median:
            intents_selected[2].append(intent)
        elif nbr_words_query >= nbr_words_query_median and nbr_words_posts >= nbr_words_posts_median:
            intents_selected[3].append(intent)
        else:
            raise AssertionError('This should not happen.')

    dcs = [intents_split_to_dynamicContent(
        current_intents, nbr_posts=10, format_as=format_as,
        #only_intent_ids=only_intent_ids.strip().split(',') if only_intent_ids is not None else None,
        #dynamicContent_loaded={dc['identifier']: dc for dc in summary.get('dynamicContent', {})}
    ) for current_intents in
        intents_selected]
    # summary['dynamicContent'] = intents_split_to_dynamicContent(intents, nbr_posts=10,
    #                                                            #max_queries=max_queries,
    #                                                            format_as=format_as,
    #                                                            only_intent_ids=only_intents.strip().split(',') if only_intents is not None else None,
    #                                                            dynamicContent_loaded={dc['identifier']: dc for dc in summary.get('dynamicContent', {})})
    # with open('scrape_10/Summary_content.json', 'w') as f:

    for i, dc in enumerate(dcs):
        summary['dynamicContent'] = dc
        with codecs.open('%s.%i' % (summary_out_fn, i), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=4)
            # f.write(json_string)
            f.flush()


def create_single_job(intents, summary, summary_out_fn, format_as):
    summary['dynamicContent'] = intents_split_to_dynamicContent(intents, nbr_posts=10,
                                                                format_as=format_as,
                                                                #only_intent_ids=only_intent_ids.strip().split(',') if only_intent_ids is not None else None,
                                                                dynamicContent_loaded={dc['identifier']: dc for dc in summary.get('dynamicContent', {})})
    #with open('scrape_10/Summary_content.json', 'w') as f:
    with codecs.open(summary_out_fn, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
        #f.write(json_string)
        f.flush()


def main(mode: ("create one or multiple jobs", 'positional', None, str, ['single', 'multiple', 'test']),
         base_path: ("Path to the base directory", 'option', 'p')='scrape_10',
         tsv_sentences_fn: ("tsv file containing the split sentences", 'option', 's')='ARNE_LEO-Training-Example-Summaries-Intents.tsv',
         intents_all_fn: ("Jsonline file containing all intent data", 'option', 't')='intents_questions_10_merged.jl',
         summary_in_fn: ("Json file that will be used as template", 'option', 'i')='Summary.template.json',
         summary_out_fn: ("Json file that will be used as template", 'option', 'o') = 'Summary.json',
         column_split_content: ("Column in the tsv sentences file that contains the split sentences", 'option', 'c')='answers_plain_marked_relevant_NEW',
         format_as: ("How to format the sentence entries", 'option', 'f', str, [FORMAT_LIST, FORMAT_PARAGRAPHS, FORMAT_CHECKBOXES])=FORMAT_LIST,
         #max_queries: ("maximal number of queries. defaults to take all (-1)", 'option', 'm', int)=-1,
         intent_ids_whitelist: ("use only intents with these ids", 'option', 'w', str)=None,
         intent_ids_blacklist: ("use only intents with these ids", 'option', 'b', str)=""
         ):

    if mode == 'test':
        with open(path.join(base_path, 'test.txt')) as f:
            test_text = '\n'.join(f.readlines())
        answer_from_concat(test_text)
        return

    blacklist = {'SEGMENTED': ['not-segmented', '', None], 'Scrapen?': ['0']}
    _intent_ids_blacklist = intent_ids_blacklist.strip().split(',')
    _intent_ids_whitelist = intent_ids_whitelist.strip().split(',') if intent_ids_whitelist is not None else ()
    intents_all = {intent[INTENT_ID]: intent for intent in load_jl(path.join(base_path, intents_all_fn))}
    intents = []
    for intent in read_tsv(path.join(base_path, tsv_sentences_fn)):
        intent_id = intent[INTENT_ID]
        content_segmented = intent[column_split_content]
        if content_segmented and content_segmented.strip() \
                and not any(intent[k] in blacklist[k] or (intent[k] is not None and intent[k].strip() in blacklist[k]) for k in blacklist) \
                and intent_id not in _intent_ids_blacklist \
                and intent_ids_whitelist is None or intent_id in _intent_ids_whitelist:
            try:
                intent.update(intents_all[intent_id])
                intent[ANSWERS_ALL] = answers_dict_from_intent(intents_all[intent_id])
                intent[ANSWERS_SPLIT] = answer_from_concat(intent[column_split_content])
                #intents[intent_id] = intent
                intents.append(intent)
                logging.info('take intent: %s' % intent_id)
            except Exception as e:
                logging.error('intent: %s' % intent_id)
                raise(e)
        else:
            logging.warning('skipped intent: %s' % intent_id)

    logging.info('collected %i segmented intents' % len(intents))
    # debug
    #logging.debug('all_intent_names:')
    #for int_name in sorted([intent[INTENT_ID] for intent in intents]):
    #    logging.debug(int_name)
    #all_answer_urls = []
    #for intent in intents:
    #    all_answer_urls.extend(intent[ANSWERS_ALL].keys())
    #logging.debug('all_answer_urls (%i):' % len(set(all_answer_urls)))
    #for asw_url in sorted(list(set(all_answer_urls))):
    #    logging.debug(asw_url)

    with open(summary_in_fn) as f:
        summary = json.load(f)

    #answers_all = {a[URL]: a for a in answers_from_intents(intents)}
    #print('stats for answers_all:')
    #print('distinct posts: %i' % len(answers_all))
    #print('distinct posts with image: %i' % len([url for url in answers_all if answers_all[url]['has_image']]))
    #print('distinct posts with quote: %i' % len([url for url in answers_all if answers_all[url]['has_quote']]))
    #print('distinct posts with link: %i' % len([url for url in answers_all if answers_all[url]['has_link']]))

    if mode == 'single':
        create_single_job(intents, summary, summary_out_fn, format_as)
    elif mode == 'multiple':
        create_multiple_jobs(intents, summary, summary_out_fn, format_as)
    else:
        raise AssertionError('This should not happen.')


if __name__ == "__main__":
    plac.call(main)
