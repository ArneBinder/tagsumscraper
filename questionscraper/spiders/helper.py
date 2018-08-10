import csv
import json
import logging
import os
from pathlib import Path
import spacy
import re

QUESTION_PREFIX = 'Question_'
ANSWER_PREFIX = 'Answer_'
INTENT_ID = 'Intent-ID'
INTENT_TEXT = 'Intent-Text'


def flatten(l):
    return [item for sublist in l for item in sublist]


def get_intents_from_tsv(path, filter_columns=None, scrape_flag_column=None, scrape_flag_true='1'):
    intents = []

    with open(path, 'r') as tsvin:
        reader = csv.DictReader(tsvin, delimiter='\t')
        cols = filter_columns or reader.fieldnames
        answer_cols = [col for col in cols if col.startswith(ANSWER_PREFIX)]
        question_cols = [col for col in cols if col.startswith(QUESTION_PREFIX)]
        assert len(answer_cols) == 0 or len(question_cols) == 0, 'found question (#%d) AND answer link columns (#%d) in %s, but expected just questions OR answers' % (len(question_cols), len(answer_cols), path)
        link_cols = answer_cols + question_cols
        for row in reader:
            skip = scrape_flag_column is not None and row[scrape_flag_column].strip() != scrape_flag_true
            if skip:
                #print(row)
                continue
            new_row = {c: row[c] for c in cols if c not in link_cols}
            # remove and collect link urls
            links_ = (row[col].strip() for col in link_cols if row[col] is not None)
            # filter out empty entries
            links = [x for x in links_ if x != '' and x.startswith('http')]

            new_row['links'] = links
            intents.append(new_row)
    return intents


def load_jl(path, key=None):
    with open(path, 'r') as f:
        res = [json.loads(q) for q in f.readlines()]
    if key is not None:
        return {q[key]: q for q in res}
    else:
        return res


def dump_jl(rows, path, tsv_fieldnames=None):
    if isinstance(rows, dict):
        rows = rows.values()
    print('dump to %s' % path)
    with open(path, 'w') as f:
        if tsv_fieldnames is not None:
            w = csv.DictWriter(f, fieldnames=tsv_fieldnames, delimiter='\t', extrasaction='ignore', quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(rows)
        else:
            f.writelines((json.dumps(row) + '\n' for row in rows))
        f.flush()


def get_link_to_intent_mapping(intends, links_key):
    res = {}
    for intent in intends:
        for link in intent[links_key]:
            res[link] = intent[INTENT_TEXT].strip()
    return res


def create_sql_inserts_answers(directory='answers'):
    create_sql_inserts(intents_jsonl=os.path.join(directory, 'intents.jl'),
                       scraped_answers_jsonl=os.path.join(directory, 'scraped.jl'), insert=False)


def create_sql_inserts_questions(directory='questions'):
    create_sql_inserts(intents_jsonl=os.path.join(directory, 'intents.jl'),
                       scraped_questions_jsonl=os.path.join(directory, 'scraped.jl'), insert=False)


def merge_answers_to_intents(intents_jsonl, scraped_questions_jsonl=None, scraped_answers_jsonl=None, split_sentences=True):
    if split_sentences:
        nlp = spacy.load('de')
        print('german spacy model loaded successfully')
    intents = load_jl(intents_jsonl)
    assert scraped_questions_jsonl is None or scraped_answers_jsonl is None, 'please provide just one question OR answer file'
    if scraped_answers_jsonl is not None:
        answers = load_jl(scraped_answers_jsonl, key='url')
        for i in range(len(intents)):
            intents[i]['answers'] = [answers[url] for url in intents[i]['links'] if url in answers]

            dif = len(intents[i]['links']) - len(set(intents[i]['links']))
            intents[i]['links'] = list(set(intents[i]['links']))
            if dif > 0:
                print('DUPLICATED LINKS FOR INTENT (id: %s; different: %i; duplicates: %i): %s' % (intents[i][INTENT_ID], len(intents[i]['links']), dif, intents[i][INTENT_TEXT]))
            intents[i]['answers_plain'] = '\n\n'.join((a['content_cleaned'] for a in intents[i]['answers'] if not a['has_quote']))
    elif scraped_questions_jsonl is not None:
        questions = load_jl(scraped_questions_jsonl, key='url')
        for i, intent in enumerate(intents):
            dif = len(intents[i]['links']) - len(set(intents[i]['links']))
            if dif > 0:
                print('DUPLICATED LINKS FOR INTENT (id: %s; different: %i; duplicates: %i): %s' % (intents[i][INTENT_ID], len(intents[i]['links']), dif, intents[i][INTENT_TEXT]))
            intents[i]['questions'] = [questions[url] for url in set(intents[i]['links']) if url in questions]
            for j, q in enumerate(intents[i]['questions']):
                intents[i]['questions'][j]['nbr_answers'] = len(intents[i]['questions'][j]['answers'])
                intents[i]['questions'][j]['nbr_answers_relevant'] = 0
                for k, a in enumerate(q['answers']):
                    if a['url'] in intent.get('relevant_answer_links', []):
                        intents[i]['questions'][j]['answers'][k]['is_relevant'] = True
                        intents[i]['questions'][j]['nbr_answers_relevant'] += 1
                    else:
                        intents[i]['questions'][j]['answers'][k]['is_relevant'] = False
            answers = flatten([[a for a in q['answers'] if not a['has_quote']] for q in intents[i]['questions']])
            answers_relevant = flatten(
                [[a for a in q['answers'] if not a['has_quote'] and a['is_relevant']] for q in intents[i]['questions']])
            intents[i]['answers_plain'] = '\n\n'.join([a['content_cleaned'] for a in answers])
            intents[i]['answers_plain_relevant'] = '\n\n'.join([a['content_cleaned'] for a in answers_relevant])

            def join_answers_marked(answers, split_sentences=False):
                res = []
                if split_sentences:
                    for a in answers:
                        paragraphs = ['|\n'.join(map(lambda x:  re.sub(r' +', ' ', str(x).strip().replace('\n', ' ')), nlp(p).sents)) for p in a['content_cleaned'].split('\n\n') if p.strip() != '']
                        res.append('----- %s -----\n%s' % (a['url'], '|\n\n'.join(paragraphs)))
                    return '|\n\n'.join(res)
                else:
                    res = ['----- %s -----\n%s' % (a['url'], a['content_cleaned']) for a in answers]
                    return '\n\n'.join(res)

            intents[i]['answers_plain_marked'] = join_answers_marked(answers)
            intents[i]['answers_plain_marked_relevant'] = join_answers_marked(answers_relevant)

            if split_sentences:
                intents[i]['answers_plain_marked_sentences'] = join_answers_marked(answers, split_sentences=True)
                intents[i]['answers_plain_marked_sentences_relevant'] = join_answers_marked(answers_relevant, split_sentences=True)

            intents[i]['nbr_answers'] = sum([q['nbr_answers'] for q in intents[i]['questions']])
            intents[i]['nbr_answers_relevant'] = sum([q['nbr_answers_relevant'] for q in intents[i]['questions']])

            intents[i]['nbr_words'] = len(intents[i]['answers_plain'].split())
            intents[i]['nbr_words_relevant'] = len(intents[i]['answers_plain_relevant'].split())

            intents[i]['nbr_original_relevant_answer_links'] = len(intents[i]['original_relevant_answer_links'])
            intents[i]['nbr_questions'] = len(intents[i]['questions'])

    else:
        raise AssertionError('please provide a question or answer file')
    dump_jl(intents, (Path(intents_jsonl).parent / 'intents_merged.jl').resolve())
    tsv_fieldnames = [k for k in intents[0].keys() if k not in ['answers', 'questions'] and not k.startswith('answers_plain')]
    tsv_fieldnames += [k for k in intents[0].keys() if k.startswith('answers_plain')]
    dump_jl(intents, (Path(intents_jsonl).parent / 'intents_merged.tsv').resolve(), tsv_fieldnames=tsv_fieldnames)


def get_answers_and_intent_and_mapping(intents_jsonl, scraped_questions_jsonl=None, scraped_answers_jsonl=None):
    intents = load_jl(intents_jsonl)
    assert scraped_questions_jsonl is None or scraped_answers_jsonl is None, 'please provide just one question OR answer file'
    if scraped_questions_jsonl is not None:
        _links_to_intents = get_link_to_intent_mapping(intents, links_key='links')
        questions = load_jl(scraped_questions_jsonl, key='url')
        answers = {}
        links_to_intents = {}
        for question_url in questions:
            # collect answers
            answers.update({a['url']: a for a in questions[question_url]['answers']})
            # map links again
            links_to_intents.update(
                {a['url']: _links_to_intents[question_url] for a in questions[question_url]['answers'] if
                 question_url in _links_to_intents})
    elif scraped_answers_jsonl is not None:
        links_to_intents = get_link_to_intent_mapping(intents, links_key='links')
        answers = load_jl(scraped_answers_jsonl, key='url')
    else:
        raise AssertionError('please provide a question or answer file')

    return answers, intents, links_to_intents


def create_sql_inserts(intents_jsonl, scraped_questions_jsonl=None, scraped_answers_jsonl=None, insert=False):
    #with open(intent_file_json, 'r') as f:
    #    intents = json.load(f)

    answers, intents, links_to_intents = get_answers_and_intent_and_mapping(intents_jsonl, scraped_questions_jsonl, scraped_answers_jsonl)

    dir = Path(intents_jsonl).parent

    # create inserts for st_docset (intents) like this:
    #
    # INSERT INTO st_docset(topic)
    # VALUES
    # ("Mein WLAN ist langsam."),
    # ("TESTTEST")

    with open((dir / 'insert_intents.sql').resolve(), 'w') as insert_intents:
        insert_intents.write('INSERT INTO st_docset(topic)\n')
        insert_intents.write('VALUES\n')
        lines = ',\n'.join(('("%s")' % intend[INTENT_TEXT].replace('"', '\'') for intend in intents if intend[INTENT_TEXT] != ''))
        insert_intents.write(lines + ';')


    # create inserts for st_doc like this:
    # INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, "DOC_TITLE", "DOC_CONTENT" FROM st_docset WHERE topic = "Test topicX";

    entries = [(answer_url, answers[answer_url]['content'].replace('"', '\''), links_to_intents[answer_url])
               for answer_url in answers if answer_url in links_to_intents]
    with open((dir / 'insert_answers.sql').resolve(), 'w') as insert_answers:
        lines = ('INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, "%s", "%s" FROM st_docset WHERE topic = "%s";'
                 % e for e in entries)
        insert_answers.writelines(lines)

    # create adjust_table.sql that sets required character sets (for smileys, etc)
    with open((dir / 'adjust_tables.sql').resolve(), 'w') as adjust_tables:
        adjust_tables.write('ALTER TABLE st_doc CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n')
        adjust_tables.write('ALTER TABLE st_docset CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;\n')

    if insert:
        import MySQLdb

        PASSWORD = 'SET_A_PASSWORD'
        db = MySQLdb.connect(host='0.0.0.0', port=3307, user="root", passwd=PASSWORD, db='mdswriter', use_unicode=True)
        c = db.cursor()
        c.execute('ALTER TABLE st_doc CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        c.execute('ALTER TABLE st_docset CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        c.executemany('INSERT INTO st_docset (topic) VALUES (%s)', (intend[INTENT_TEXT].replace('"', '\'') for intend in intents if intend[INTENT_TEXT] != ''))
        db.commit()
        c.executemany(
            'INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, %s, %s FROM st_docset WHERE topic = %s',
            entries)


def calc_stats_questions(intent_file_json='questions/intents.jl', question_file_jsonl='questions/scraped.jl'):

    #with open(intent_file_json, 'r') as f:
    #    intents = json.load(f)

    intents = load_jl(intent_file_json)
    questions_dict = load_jl(question_file_jsonl, key='url')

    for url in questions_dict:
        questions_dict[url]['nbr_answers'] = len(questions_dict[url]['answers'])
        questions_dict[url]['nbr_solutions'] = len([True for a in questions_dict[url]['answers'] if a['solution_accepted_by'] is not None])
        q_author_name = questions_dict[url]['question']['author_name']
        questions_dict[url]['nbr_answers_from_question_author'] = len([True for a in questions_dict[url]['answers'] if a['author_name'] == q_author_name])

    for i in range(len(intents)):
        intents[i]['nbr_questions'] = len(intents[i]['links'])
        intent_answers = [questions_dict[a_url] for a_url in intents[i]['links'] if a_url in questions_dict]
        intents[i]['nbr_answers'] = sum([a['nbr_answers'] for a in intent_answers])
        intents[i]['nbr_solutions'] = sum([a['nbr_solutions'] for a in intent_answers])

    # intents_stats_fn = out_file or 'intents_questions_stats.tsv'
    dir = Path(intent_file_json).parent
    intents_stats_fn = (dir / 'intents_stats.tsv').resolve()
    logging.info('write intents with stats to: %s' % intents_stats_fn)
    with open(intents_stats_fn, 'w') as intents_stats_file:
        assert len(intents) > 0, 'no intents'
        writer = csv.DictWriter(intents_stats_file, fieldnames=intents[0].keys(), delimiter='\t')
        writer.writeheader()
        writer.writerows(intents)

    #return intents, questions_dict


def calc_stats_answers(intent_file_jsonl='answers/intents.jl', answer_file_jsonl='answers/scraped.jl'):
    #with open(intent_file_json, 'r') as f:
    #    intents = json.load(f)

    intents = load_jl(intent_file_jsonl)
    answers_dict = load_jl(answer_file_jsonl, key='url')

    for i in range(len(intents)):
        intent_answers = [answers_dict[a_url] for a_url in intents[i]['links'] if a_url in answers_dict]
        intents[i]['nbr_answers'] = len(intent_answers)
        intents[i]['nbr_solutions'] = len([True for a in intent_answers if a['solution_accepted_by'] is not None])

    #intents_stats_fn = out_file or 'intents_answers_stats.tsv'
    dir = Path(intent_file_jsonl).parent
    intents_stats_fn = (dir / 'intents_stats.tsv').resolve()
    logging.info('write intents with stats to: %s' % intents_stats_fn)
    with open(intents_stats_fn, 'w') as intents_stats_file:
        assert len(intents) > 0, 'no intents'
        writer = csv.DictWriter(intents_stats_file, fieldnames=intents[0].keys(), delimiter='\t')
        writer.writeheader()
        writer.writerows(intents)

    #return intents, answers_dict


def merge_questions_answers(merged_intents_questions='questions/intents_merged.jl', merged_intents_answers='answers/intents_merged.jl'):
    intents_questions =load_jl(merged_intents_questions, key=INTENT_ID)
    intents_answers = load_jl(merged_intents_answers, key=INTENT_ID)

    not_in_intents_answers = set(intents_questions.keys()) - set(intents_answers.keys())
    if len(not_in_intents_answers) > 0:
        print('not in intents_answers, but in intents_questions: %s' % str(list(not_in_intents_answers)))
    not_in_intents_questions = set(intents_answers.keys()) - set(intents_questions.keys())
    if len(not_in_intents_questions):
        print('not in intents_questions, but in intents_answers: %s' % str(list(not_in_intents_questions)))

    for k in intents_questions.keys():
        intents_answers[k]['question_answers_plain'] = intents_questions[k]['answers_plain']

    intents_merged_all = sorted(intents_answers.values(), key=lambda x: x[INTENT_ID])
    dump_jl(intents_merged_all, 'intents_merged_all.tsv',
            tsv_fieldnames=[k for k in intents_merged_all[0].keys() if k not in ['answers', 'questions']])