import csv
import json
import logging
import os
from pathlib import Path

QUESTION_PREFIX = 'Similar_Question_Link'
ANSWER_PREFIX = 'Answer'
TOPIC_CAPTION = 'Intent-Text'


def flatten(l):
    return [item for sublist in l for item in sublist]


# deprecated
def get_intents_from_file(path):
    intents = []
    # sim_urls = []
    with open(path, 'r') as tsvin:
        reader = csv.reader(tsvin, delimiter='\t')
        headers = reader.__next__()
        simlink_indices = [i for i, h in enumerate(headers) if h == 'Similar_Question_Link']
        text_idx = headers.index(TOPIC_CAPTION)
        id_idx = headers.index('Intent-ID')
        for r in reader:
            intents.append({'Intent-ID': r[id_idx],
                            'Similar_Question_Links': [r[i] for i in simlink_indices if
                                                       r[i].startswith('https://telekomhilft.telekom.de')],
                            TOPIC_CAPTION: r[text_idx]})
    return intents


def get_intents_from_tsv(path):
    intents = []

    with open(path, 'r') as tsvin:
        reader = csv.DictReader(tsvin, delimiter='\t')
        answer_cols = [col for col in reader.fieldnames if col.startswith(ANSWER_PREFIX)]
        question_cols = [col for col in reader.fieldnames if col.startswith(QUESTION_PREFIX)]
        for row in reader:
            new_row = {c: row[c] for c in row if c not in answer_cols + question_cols}
            # remove and collect question urls
            questions_ = (row[col].strip() for col in question_cols)
            # filter out empty entries
            questions = [x for x in questions_ if x != '' and x.startswith('http')]
            # remove and collect answer urls
            answers_ = (row[col] for col in answer_cols)
            # filter out empty entries
            answers = [x for x in answers_ if x != '' and x.startswith('http')]

            new_row[QUESTION_PREFIX] = questions
            new_row[ANSWER_PREFIX] = answers
            intents.append(new_row)
    return intents


def load_jl(path):
    with open(path, 'r') as f:
        res = [json.loads(q) for q in f.readlines()]
    res_dict = {q['url']: q for q in res}
    return res_dict


def get_link_to_intent_mapping(intends, links_key):
    res = {}
    for intent in intends:
        for link in intent[links_key]:
            res[link] = intent[TOPIC_CAPTION].strip()
    return res


# deprecated
def get_entries_from_questions(question_file_jsonl, intents):
    questions = load_jl(question_file_jsonl)

    answer_to_intent = {}
    answers_filtered = []
    nbr_empty = 0
    for intent in intents:
        if intent[TOPIC_CAPTION].strip() != '':
            current_answers_ = [questions[question_url]['answers'] for question_url in intent['Similar_Question_Links']]
            current_answers = [item for sublist in current_answers_ for item in sublist]
            answers_filtered.extend(current_answers)
            answer_to_intent.update({ans['url']: intent[TOPIC_CAPTION].strip() for ans in current_answers})
        else:
            nbr_empty += 1
    print('empty topics: %d' % nbr_empty)

    return answers_filtered, answer_to_intent


def create_sql_inserts_answers(directory='answers'):
    create_sql_inserts(intent_file_json=os.path.join(directory, 'intents.json'),
                       answer_file_jsonl=os.path.join(directory, 'scraped.jl'), insert=False)


def create_sql_inserts_questions(directory='questions'):
    create_sql_inserts(intent_file_json=os.path.join(directory, 'intents.json'),
                       question_file_jsonl=os.path.join(directory, 'scraped.jl'), insert=False)


def create_sql_inserts(intent_file_json, question_file_jsonl=None, answer_file_jsonl=None, insert=False):
    with open(intent_file_json, 'r') as f:
        intents = json.load(f)

    dir = Path(intent_file_json).parent


    # create inserts for st_docset (intents) like this:
    #
    # INSERT INTO st_docset(topic)
    # VALUES
    # ("Mein WLAN ist langsam."),
    # ("TESTTEST")

    with open((dir / 'insert_intents.sql').resolve(), 'w') as insert_intents:
        insert_intents.write('INSERT INTO st_docset(topic)\n')
        insert_intents.write('VALUES\n')
        lines = ',\n'.join(('("%s")' % intend[TOPIC_CAPTION].replace('"', '\'') for intend in intents if intend[TOPIC_CAPTION] != ''))
        insert_intents.write(lines + ';')


    # create inserts for st_doc like this:
    #
    # INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, "DOC_TITLE", "DOC_CONTENT" FROM st_docset WHERE topic = "Test topicX";
    # https://telekomhilft.telekom.de/t5

    assert question_file_jsonl is None or answer_file_jsonl is None, 'please provide just one question OR answer file'
    if question_file_jsonl is not None:
        _links_to_intents = get_link_to_intent_mapping(intents, links_key=QUESTION_PREFIX)
        questions = load_jl(question_file_jsonl)
        answers = {}
        links_to_intents = {}
        for question_url in questions:
            # collect answers
            answers.update({a['url']: a for a in questions[question_url]['answers']})
            # map links again
            links_to_intents.update({a['url']: _links_to_intents[question_url] for a in questions[question_url]['answers'] if question_url in _links_to_intents})
    elif answer_file_jsonl is not None:
        links_to_intents = get_link_to_intent_mapping(intents, links_key=ANSWER_PREFIX)
        answers = load_jl(answer_file_jsonl)
    else:
        raise AssertionError('please provide a question or answer file')

    entries = [(answer_url, answers[answer_url]['content'].replace('"', '\''), links_to_intents[answer_url])
               for answer_url in answers if answer_url in links_to_intents]

    with open((dir / 'insert_answers.sql').resolve(), 'w') as insert_answers:
        lines = ('INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, "%s", "%s" FROM st_docset WHERE topic = "%s";'
                 % e for e in entries)
        insert_answers.writelines(lines)

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
        c.executemany('INSERT INTO st_docset (topic) VALUES (%s)', (intend[TOPIC_CAPTION].replace('"', '\'') for intend in intents if intend[TOPIC_CAPTION] != ''))
        db.commit()
        c.executemany(
            'INSERT INTO st_doc(docset_id, doc_title, doc_text) SELECT id, %s, %s FROM st_docset WHERE topic = %s',
            entries)


# deprecated
def get_intents_and_questions(intent_file_json='intents.json', question_file_jsonl='scraped.jl'):
    with open(intent_file_json, 'r') as intent_file:
        intents = json.load(intent_file)
    with open(question_file_jsonl, 'r') as question_file:
        questions = [json.loads(q) for q in question_file.readlines()]
    questions_dict = {q['url']: q for q in questions}
    return intents, questions_dict


def calc_stats_questions(intent_file_json='questions/intents.json', question_file_jsonl='questions/scraped.jl'):

    with open(intent_file_json, 'r') as f:
        intents = json.load(f)

    questions_dict = load_jl(question_file_jsonl)

    for url in questions_dict:
        questions_dict[url]['nbr_answers'] = len(questions_dict[url]['answers'])
        questions_dict[url]['nbr_solutions'] = len([True for a in questions_dict[url]['answers'] if a['solution_accepted_by'] is not None])
        q_author_name = questions_dict[url]['question']['author_name']
        questions_dict[url]['nbr_answers_from_question_author'] = len([True for a in questions_dict[url]['answers'] if a['author_name'] == q_author_name])

    for i in range(len(intents)):
        intents[i]['nbr_questions'] = len(intents[i][QUESTION_PREFIX])
        intent_answers = [questions_dict[a_url] for a_url in intents[i][QUESTION_PREFIX] if a_url in questions_dict]
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

    return intents, questions_dict


def calc_stats_answers(intent_file_json='answers/intents.json', answer_file_jsonl='answers/scraped.jl'):
    with open(intent_file_json, 'r') as f:
        intents = json.load(f)

    answers_dict = load_jl(answer_file_jsonl)

    for i in range(len(intents)):
        intent_answers = [answers_dict[a_url] for a_url in intents[i][ANSWER_PREFIX] if a_url in answers_dict]
        intents[i]['nbr_answers'] = len(intent_answers)
        intents[i]['nbr_solutions'] = len([True for a in intent_answers if a['solution_accepted_by'] is not None])

    #intents_stats_fn = out_file or 'intents_answers_stats.tsv'
    dir = Path(intent_file_json).parent
    intents_stats_fn = (dir / 'intents_stats.tsv').resolve()
    logging.info('write intents with stats to: %s' % intents_stats_fn)
    with open(intents_stats_fn, 'w') as intents_stats_file:
        assert len(intents) > 0, 'no intents'
        writer = csv.DictWriter(intents_stats_file, fieldnames=intents[0].keys(), delimiter='\t')
        writer.writeheader()
        writer.writerows(intents)

    return intents, answers_dict