
import json
import logging
import os
from pathlib import Path

import scrapy
from inline_requests import inline_requests

from questionscraper.spiders.helper import flatten, get_intents_from_tsv, QUESTION_PREFIX, ANSWER_PREFIX, load_jl

URL_MAIN = 'https://telekomhilft.telekom.de'
CAPTION_IMAGE = 'IMAGE'
CAPTION_BLOCKQUOTE = 'BLOCKQUOTE'
CAPTION_UNKNOWN = 'UNKNOWN'
CAPTION_LINK = 'LINK'
CAPTION_LINK_PROFILE = 'LINK_PROFILE'


def get_message_url(message, response):
    return response.urljoin(message.css('.lia-message-position-in-thread a::attr(href)').extract_first())


def serialize_elem(elem, response, in_quote=False, embed_plain=False):
    NODE_STR = 'text() | br | a | span//img | p | span | font | strong | blockquote  ' \
               '| ul/li | ol/li | div[contains(concat(" ", @class, " "), " accordion-content ")] ' \
               '| div[contains(concat(" ", @class, " "), " page ")]/div[contains(concat(" ", @class, " "), " layoutArea ")]/div[contains(concat(" ", @class, " "), " column ")]' # | div.page > div.layout > div.column'
    elems = elem.xpath(NODE_STR)
    # content, content_cleaned, content_split
    results = ['', '']
    #result_cleaned = ''
    block_prefix = ['\n\n', '\n\n']
    inline_prefix = [' ', ' ']
    for e in elems:
        tag_name = e.xpath('name()').extract_first()
        if tag_name is None:
            text = e.extract()
            if text is not None:
                results[0] += inline_prefix[0] + text
                results[1] += inline_prefix[1] + text
        else:
            #print('TAG %s %s' % (tag_name, str(e.extract())))
            if tag_name == 'br':
                results[0] += block_prefix[0]
                results[1] += block_prefix[1]
            elif tag_name == 'a':
                a_text = e.xpath('text()').extract_first()
                href = response.urljoin(e.xpath('@href').extract_first())

                if a_text is None:
                    if not (embed_plain and in_quote):
                        results[0] += '[%s]{{%s}}' % (CAPTION_LINK, response.urljoin(href))
                        results[1] += '[%s]{{%s}}' % (CAPTION_LINK, response.urljoin(href))
                    else:
                        results[0] += response.urljoin(href)
                        results[1] += response.urljoin(href)
                elif 'user/viewprofilepage/user-id' in href:
                    if not (embed_plain and in_quote):
                        results[0] += '[%s]{{%s}}{{%s}}' % (CAPTION_LINK_PROFILE, response.urljoin(href), a_text.strip())
                        #results[1] += a_text
                        results[1] += '[%s]{{%s}}{{%s}}' % (CAPTION_LINK_PROFILE, response.urljoin(href), a_text.strip())
                    else:
                        results[0] += a_text
                        results[1] += a_text
                #elif (len(a_text) > 4 and href.endswith(a_text[:-4])):
                elif a_text in href or (len(a_text) > 3 and href.startswith(a_text[:-3])):
                    if not (embed_plain and in_quote):
                        results[0] += '[%s]{{%s}}{{%s}}' % (CAPTION_LINK, response.urljoin(href), a_text.strip())
                        results[1] += '[%s]{{%s}}' % (CAPTION_LINK, href)
                    else:
                        results[0] += response.urljoin(href)
                        results[1] += response.urljoin(href)
                else:
                    if not embed_plain:
                        results[0] += '[%s]{{%s}}{{%s}}' % (CAPTION_LINK, response.urljoin(href), a_text.strip())
                        results[1] += '[%s]{{%s}}{{%s}}' % (CAPTION_LINK, response.urljoin(href), a_text.strip())
                    else:
                        results[0] += response.urljoin(href)
                        results[1] += response.urljoin(href)

            elif tag_name == 'blockquote':
                if in_quote:
                    print('QUOTE-IN-QUOTE: %s' % response.url)
                blockquote_contents = serialize_elem(e, response, in_quote=True, embed_plain=embed_plain)
                if in_quote:
                    results[0] += blockquote_contents[0]
                    results[1] += blockquote_contents[1]
                else:
                    results[0] += '%s[%s]{{%s}}' % (block_prefix[0], CAPTION_BLOCKQUOTE, blockquote_contents[0])
                    results[1] += '%s[%s]{{%s}}' % (block_prefix[0], CAPTION_BLOCKQUOTE, blockquote_contents[1])
            elif tag_name == 'img':
                img_src = response.urljoin(e.xpath('@src').extract_first())
                if not (embed_plain and in_quote):
                    results[0] += '[%s]{{%s}}' % (CAPTION_IMAGE, img_src)
                    results[1] += '[%s]{{%s}}' % (CAPTION_IMAGE, img_src)
                else:
                    results[0] += img_src
                    results[1] += img_src
            elif tag_name == 'li':
                p_contents = serialize_elem(e, response, in_quote=in_quote, embed_plain=embed_plain)
                if p_contents[0] != '':
                    results[0] += block_prefix[0] + ' * ' + p_contents[0]
                if p_contents[1] != '':
                    results[1] += block_prefix[1] + ' * ' + p_contents[1]
            elif tag_name in ['p', 'div']:
                p_contents = serialize_elem(e, response, in_quote=in_quote, embed_plain=embed_plain)
                if p_contents[0] != '':
                    results[0] += block_prefix[0] + p_contents[0]
                if p_contents[1] != '':
                    results[1] += block_prefix[1] + p_contents[1]
            elif tag_name in ['span', 'font', 'strong']:
                s_contents = serialize_elem(e, response, in_quote=in_quote, embed_plain=embed_plain)
                if s_contents[0] != '':
                    results[0] += inline_prefix[0] + s_contents[0]
                if s_contents[1] != '':
                    results[1] += inline_prefix[1] + s_contents[1]
            else:
                if not (embed_plain and in_quote):
                    results[0] += '[%s]{{%s}} ' % (CAPTION_UNKNOWN, e.extract())
                else:
                    results[0] += e.extract()
    return [res.replace('\u00a0', ' ').strip() for res in results]


def process_message_view(message, response, embed_plain=False):

    result = {}
    # get author data
    author = message.css('.telekom-custom-message-author > .telekom-custom-user-overlay')
    author_name = author.css('.lia-message-author-username > .UserName > span::text')
    result['author_name'] = author_name.extract_first()
    result['author_profile_link'] = author.css('a.telekom-custom-view-profile::attr(href)').extract_first()
    # TODO: get author kudos from profile

    # get message metadata
    result['kudos'] = int(message.css('span.MessageKudosCount::text').extract_first().strip())

    # try to get rich text
    message_content = message.css('.lia-message-body-content .outerRichtextDiv')
    if message_content.extract_first() is None:
        message_content = message.css('.lia-message-body-content')
    text, text_cleaned = serialize_elem(message_content, response, embed_plain=embed_plain)
    # replace double spaces (were inserted between inline elements)
    text_cleaned = text_cleaned.replace('  ', ' ')
    # replace double quotes (these would destroy table entries when downloaded later from google sheets)
    result['content'] = text.strip().replace('"', '\'\'')
    result['content_cleaned'] = text_cleaned.strip().replace('"', '\'\'')

    result['has_quote'] = '[%s]' % CAPTION_BLOCKQUOTE in result['content']
    result['has_image'] = '[%s]' % CAPTION_IMAGE in result['content']
    result['has_link'] = '[%s]' % CAPTION_LINK in result['content']

    result['url'] = get_message_url(message, response)
    result['solution_accepted_by'] = message.css('.lia-component-solution-info .solution-accepter > a::text').extract_first()
    solution_accepter_text_list = message.css('.lia-component-solution-info .solution-accepter::text').extract()
    if len(solution_accepter_text_list) > 0:
        result['solution_accepted_by_text'] = solution_accepter_text_list[-1].strip()
    else:
        result['solution_accepted_by_text'] = None
    if result['solution_accepted_by'] is not None:
        assert result['solution_accepted_by_text'] is not None, \
            'answer marked as solution by %s, but no additional solution_accepted_by_text given' \
            % result['solution_accepted_by']

    #content_wo_divs = message_content.xpath('*[name() != "div"] | text()')
    content_wo_signature = message_content.xpath('*[not(contains(concat(" ", @class, " "), " lia-message-signature "))] | text()')

    # concatenate, resolve relative links and add target attribute to open links in new tab
    result['content_html'] = ''.join(content_wo_signature.extract()).strip()\
        .replace('src=\"/', 'src=\"%s/' % URL_MAIN)\
        .replace('href=\"/', 'href=\"%s/' % URL_MAIN)\
        .replace('<a href=', '<a target="_blank" href=')

    return result


def parse_question(response, url_only=False):
    q = response.css('.lia-thread-topic')
    assert len(q) == 1, 'unexpected number of questions: %i for url: %s' % (len(q), response.request.url)
    if url_only:
        question_message_url = get_message_url(q[0], response)
        return {'url': question_message_url}
    return process_message_view(q[0], response)


def parse_answers(response):
    m_list = response.css('.message-list')[0]
    replies_header = m_list.css('.lia-replies-header')
    # get lia-thread-reply_s (MessageView_s)
    if len(replies_header) == 0:
        answers = m_list.css('.lia-message-view-wrapper')
    elif len(replies_header) == 1:
        answers = replies_header.xpath('following-sibling::div').css('.lia-message-view-wrapper')
    else:
        raise ValueError(
            'Unexpected number of replies header in message-list: %i. Expected 0 or 1.' % len(replies_header))
    answers = [process_message_view(answ, response) for answ in answers]
    return answers


class QuestionsSpider(scrapy.Spider):
    name = "questions"

    def start_requests(self):
        max_answers = int(getattr(self, 'max_answers', 10))
        logging.info('use max_answers: %i' % max_answers)
        intent_file = getattr(self, 'intent_file', None)
        assert intent_file is not None, 'no intent_file set. Please specify a intent_file via scrapy parameters: "-a intent_file=PATH_TO_INTENT_FILE"'

        logging.info('load %s from file: %s' % (QUESTION_PREFIX, intent_file))

        f_ext = os.path.splitext(intent_file)[1]
        if f_ext.lower() == 'tsv':
            # TODO: filter columns? see AnswersSpider.start_requests
            raise NotImplementedError('only intent files in json line file format are implemented for scraping question')
        elif f_ext.lower() in ['.jl', '.jsonl']:
            intents = load_jl(intent_file)
            #question_links = []
            #relevant_answer_links = []
            for i, intent in enumerate(intents):
                intents[i]['original_relevant_answer_links'] = intents[i]['links']
                answers = intent['answers'][:max_answers]
                intents[i]['relevant_answer_links'] = [a['url'] for a in answers]
                #relevant_answer_links.extend(intents[i]['relevant_answer_links'])
                intents[i]['links'] = sorted(list(set([a['question_url'] for a in answers])))
                #question_links.extend(intents[i]['question_links'])
                del intents[i]['answers']

        else:
            raise ValueError('unknown intent file extension: %s' % f_ext)
        urls = flatten([intent['links'] for intent in intents])
        dir = Path(intent_file).parent
        intents_backup_fn = (dir / ('intents_questions_%i.jl' % max_answers)).resolve()
        logging.info('backup intents to %s' % intents_backup_fn)
        with open(intents_backup_fn, 'w') as intents_out:
            #json.dump(intents, intents_out)
            intents_out.writelines(json.dumps(intent)+'\n' for intent in intents)

        results = []
        logging.info('crawl %d urls ...' % len(urls))
        for url in urls:
            res = scrapy.Request(url=url, callback=self.parse)
            results.append(res)
            yield res

    @inline_requests
    def parse(self, response):
        question = parse_question(response)
        answers = parse_answers(response)
        title = response.css('.PageTitle > span::text').extract_first()
        solved = response.css('.icon-confirm').extract_first() is not None
        tags = [t.strip() for t in response.css('.TagList .lia-tag-list-item > .lia-tag::text').extract()]

        next_resp = response
        while True:
            next_url = next_resp.css('.lia-component-message-list > .lia-paging-pager .lia-paging-page-next a::attr(href)').extract_first()
            if next_url is not None:
                next_resp = yield scrapy.Request(next_url)
                next_answers = parse_answers(next_resp)
                answers.extend(next_answers)
            else:
                break
        yield {'url': response.request.url, 'title': title, 'solved': solved, 'tags': tags, 'question': question, 'answers': answers}


class AnswersSpider(scrapy.Spider):
    name = "answers"

    def start_requests(self):
        #https://telekomhilft.telekom.de/t5/Telefonie-Internet/Internet-ist-viel-zu-langsam/m-p/2694977#M798659
        #https://telekomhilft.telekom.de/t5/Telefonie-Daten/Auslandsflat-Laendergruppe-2/m-p/2820568#M57752
        #https://telekomhilft.telekom.de/t5/Telefonie-Daten/Auslandsflat-Laendergruppe-2/m-p/2820660#M57754

        #https://telekomhilft.telekom.de/t5/Fernsehen/TV-Paket-kuendigen/m-p/2603477#M202884
        max_answers = int(getattr(self, 'max_answers', 10))
        logging.info('use max_answers: %i' % max_answers)
        test_link = getattr(self, 'test_link', None)
        if test_link is not None:
            urls = [test_link]
        else:
            intent_file = getattr(self, 'intent_file', None)
            assert intent_file is not None, 'no intent_file set. Please specify a intent_file via scrapy parameters: "-a intent_file=PATH_TO_INTENT_FILE"'

            logging.info('load %s from file: %s' % (ANSWER_PREFIX, intent_file))
            intents = get_intents_from_tsv(
                intent_file,
                filter_columns=['Intent-ID', 'DT-Example', 'Basis-Intent-Text', 'Intent-Text', 'Answers-Searcher',
                                'Intent-Type', 'Summary-Must-Haves',
                                'Scrapen?', 'SEGMENTED', 'answers_plain_marked_relevant_segmented',
                                'Trainingsbeispiel'
                                #'Answer_0', 'Answer_1', 'Answer_2', 'Answer_3', 'Answer_4', 'Answer_5', 'Answer_6',
                                #'Answer_7', 'Answer_8', 'Answer_9',
                                #'Answer_10', 'Answer_11', 'Answer_12', 'Answer_13', 'Answer_14', 'Answer_15', 'Answer_16',
                                #'Answer_17', 'Answer_18', 'Answer_19'
                                ] + [ANSWER_PREFIX + str(i) for i in range(max_answers)],
                scrape_flag_column='Scrapen?'
            )
            urls = flatten([intent['links'] for intent in intents])
            for url in urls:
                logging.debug(url)
            dir = Path(intent_file).parent
            intents_backup_fn = (dir / ('intents_answers_%i.jl' % max_answers)).resolve()
            logging.info('backup intents to %s' % intents_backup_fn)
            with open(intents_backup_fn, 'w') as intents_out:
                #json.dump(intents, intents_out)
                intents_out.writelines(json.dumps(intent) + '\n' for intent in intents)

        results = []
        logging.info('crawl %d urls ...' % len(urls))
        for url in urls:
            res = scrapy.Request(url=url, callback=self.parse)
            results.append(res)
            yield res

    @inline_requests
    def parse(self, response):
        answers = parse_answers(response)
        answers_dict = {a['url']: a for a in answers}
        assert response.request.url in answers_dict, 'answers with response.request.url=%s not found at that page' % response.request.url

        answer = answers_dict[response.request.url]
        page_1_url = response.css('.lia-paging-page-first > a::attr(href)').extract_first()
        if page_1_url is not None:
            page_1_resp = yield scrapy.Request(page_1_url, dont_filter=True)
        else:
            page_1_resp = response
        question = parse_question(page_1_resp, url_only=True)
        answer['question_url'] = question['url']
        yield answer


