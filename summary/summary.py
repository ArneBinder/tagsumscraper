import codecs
import logging
import re
import csv
import json
import html
import plac
from questionscraper.spiders.helper import load_jl
from os import path
from bs4 import BeautifulSoup


FORMAT_LIST = 'list'
FORMAT_CHECKBOXES = 'checkboxes'
FORMAT_PARAGRAPHS = 'paragraphs'

#logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
logging.getLogger().setLevel(logging.INFO)


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


def intents_split_to_dynamicContent(intents_split, answers_all, nbr_posts, max_queries=-1, dynamicContent_loaded=None,
                                    only_query_nbrs=None, format_as=FORMAT_LIST):
    if dynamicContent_loaded is None:
        dynamicContent_loaded = {}
    posts = [{'identifier': 'Post%i' % (i+1), 'type': 'TEXT', 'values': []} for i in range(nbr_posts)]
    if 'query' in dynamicContent_loaded:
        logging.warning('"query" is already in dynamicContent, do NOT overwrite.')
    if 'summaryGood' in dynamicContent_loaded:
        logging.warning('"summaryGood" is already in dynamicContent, do NOT overwrite.')
    if 'summaryBad' in dynamicContent_loaded:
        logging.warning('"summaryBad" is already in dynamicContent, do NOT overwrite.')
    if 'Post1' in dynamicContent_loaded:
        logging.warning('"Post1" is already in dynamicContent, OVERWRITE all "Post<n>".')
    query = {'identifier': 'query', 'type': 'TEXT', 'values': dynamicContent_loaded['query']['values'] if 'query' in dynamicContent_loaded else []}
    summary_good = {'identifier': 'summaryGood', 'type': 'TEXT', 'values': dynamicContent_loaded['summaryGood']['values'] if 'summaryGood' in dynamicContent_loaded else []}
    summary_bad = {'identifier': 'summaryBad', 'type': 'TEXT', 'values': dynamicContent_loaded['summaryBad']['values'] if 'summaryBad' in dynamicContent_loaded else []}
    all_l = []
    for i, intent_id in enumerate(intents_split):
        if i == max_queries:
            break
        if only_query_nbrs is not None and str(i) not in only_query_nbrs:
            continue
        if 'query' not in dynamicContent_loaded:
            query['values'].append('<div class=\"query\">%s</div>' % prepare_for_html(intents_split[intent_id]['Intent-Text']))

        if 'summaryGood' not in dynamicContent_loaded:
            current_summary_good = 'good DUMMY SUMMARY for intent %s' % intent_id
            summary_good['values'].append('<div class=\"summary\">%s</div>' % current_summary_good)
        if 'summaryBad' not in dynamicContent_loaded:
            current_summary_bad = 'bad DUMMY SUMMARY for intent %s' % intent_id
            summary_bad['values'].append('<div class=\"summary\">%s</div>' % current_summary_bad)

        #current_answers_split_sorted = list(reversed(sorted([(url, intents_split[intent_id]['answers_split'][url]) for url in
        #                                       intents_split[intent_id]['answers_split']], key=lambda x: len(''.join(x[1])))))
        current_answers_split = [(url, intents_split[intent_id]['answers_split'][url]) for url in intents_split[intent_id]['answers_split']]
        answers_html = []
        for current_url, current_answer in current_answers_split:
            answer_full = answers_all[current_url]
            answer_splits = prepare_for_html(re.sub(r'\s*\(\d+\)\s*$', '', current_answer),
                                             format_as=format_as)

            new_answer = '<div class="answer-content">%s</div>' % answer_splits
            question_title = '<div class="question-title">%s</div>' % answer_full['question']['title']

            accepted_by = answer_full.get('solution_accepted_by', None)
            accepted_by_text = answer_full.get('solution_accepted_by_text', None)
            if accepted_by:
                new_answer = '<div class="answer solution"><div class="solution-header">Lösung akzeptiert von %s %s</div>%s</div>' \
                             % (accepted_by, accepted_by_text, new_answer)
            else:
                new_answer = '<div class="answer">%s</div>' % new_answer
            answers_html.append(question_title + new_answer)

        answers_html_with_parsed_text = [(html_doc, BeautifulSoup(html_doc, 'html.parser').get_text()) for html_doc in answers_html]
        ## use character count for sorting
        #answers_html_sorted = sorted(answers_html_with_parsed_text, key=lambda h_with_l: len(h_with_l[1]), reverse=True)
        # sort by umber of block elements, but give <div>s more weight
        answers_html_sorted = sorted(answers_html_with_parsed_text, key=lambda h_with_l: 1.5 * h_with_l[0].count('<div') + h_with_l[0].count('<p') + h_with_l[0].count('<li'), reverse=True)
        # use words count as length
        l = sum(map(lambda x: len(x[1].strip().split()), answers_html_with_parsed_text))
        for post_pos in range(nbr_posts):
            #new_answer = ''
            #keys = list(intents_split[intent_id]['answers_split'].keys())
            if post_pos < len(answers_html_sorted):
                posts[post_pos]['values'].append(answers_html_sorted[post_pos][0])
            else:
                posts[post_pos]['values'].append('')
        all_l.append(l)
    logging.info('lengths of all posts for all %i intents: %s' % (len(all_l), str(all_l)))
    return posts + [query, summary_good, summary_bad]


def main(base_path: ("Path to the base directory", 'option', 'p')='scrape_10',
         tsv_sentences_fn: ("tsv file containing the split sentences", 'option', 's')='ARNE_LEO-Training-Example-Summaries-Intents.tsv',
         intents_all_fn: ("Jsonline file containing all intent data", 'option', 'i')='intents_questions_10_merged.jl',
         summary_template_fn: ("Json file that will be used as template", 'option', 't')='Summary.template.json',
         column_split_content: ("Column in the tsv sentences file that contains the split sentences", 'option', 'c')='answers_plain_marked_relevant_NEW',
         format_as: ("How to format the sentence entries", 'option', 'f', str, [FORMAT_LIST, FORMAT_PARAGRAPHS, FORMAT_CHECKBOXES])=FORMAT_LIST,
         max_queries: ("maximal number of queries. defaults to take all (-1)", 'option', 'm', int)=-1,
         only_queries: ("use only query with this number/index (zero based)", 'option', 'q', str)=None
         ):

    template_marker = '.template'
    assert template_marker in summary_template_fn, \
        'summary_template_fn ("%s") has to contain the template marker ("%s")' % (summary_template_fn, template_marker)
    summary_out_fn = summary_template_fn.replace(template_marker, '')

    intents = load_jl(path.join(base_path, intents_all_fn))
    answers_all = {a['url']: a for a in answers_from_intents(intents)}
    #print('stats for answers_all:')
    #print('distinct posts: %i' % len(answers_all))
    #print('distinct posts with image: %i' % len([url for url in answers_all if answers_all[url]['has_image']]))
    #print('distinct posts with quote: %i' % len([url for url in answers_all if answers_all[url]['has_quote']]))
    #print('distinct posts with link: %i' % len([url for url in answers_all if answers_all[url]['has_link']]))

    intents_split = {intent['Intent-ID']: {'Intent-Text': intent['Intent-Text'], 'answers_split': answer_from_concat(intent[column_split_content])} for intent in read_tsv(path.join(base_path, tsv_sentences_fn))}
    with open(path.join(base_path, summary_template_fn)) as f:
        summary = json.load(f)

    #with codecs.open(path.join(base_path, 'debug.json'), 'w', encoding='utf-8') as f:
    #    json.dump(summary, f, ensure_ascii=False, indent=4)
    #    #f.write(json_string)
    #    f.flush()

    summary['dynamicContent'] = intents_split_to_dynamicContent(intents_split, answers_all, nbr_posts=10,
                                                                max_queries=max_queries, format_as=format_as,
                                                                only_query_nbrs=only_queries.strip().split(',') if only_queries is not None else None,
                                                                dynamicContent_loaded={dc['identifier']: dc for dc in summary.get('dynamicContent', {})})
    #with open('scrape_10/Summary_content.json', 'w') as f:
    with codecs.open(path.join(base_path, summary_out_fn), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)
        #f.write(json_string)
        f.flush()


if __name__ == "__main__":
    plac.call(main)
