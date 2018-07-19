
import json
import logging
from pathlib import Path

import scrapy
from inline_requests import inline_requests

from questionscraper.spiders.helper import flatten, get_intents_from_tsv, QUESTION_PREFIX, ANSWER_PREFIX


def process_message_view(message, response):

    result = {}
    # get author data
    author = message.css('.telekom-custom-message-author > .telekom-custom-user-overlay')
    author_name = author.css('.lia-message-author-username > .UserName > span::text')
    result['author_name'] = author_name.extract_first()
    result['author_profile_link'] = author.css('a.telekom-custom-view-profile::attr(href)').extract_first()
    # TODO: get author kudos from profile

    # get message metadata
    result['kudos'] = int(message.css('span.MessageKudosCount::text').extract_first().strip())

    CAPTION_IMAGE = 'IMAGE'
    CAPTION_BLOCKQUOTE = 'BLOCKQUOTE'
    CAPTION_UNKNOWN = 'UNKNOWN'

    def concat_plain_elems(elem):
        NODE_STR = 'blockquote | text() | br | a | span//img'
        plain_elems = elem.xpath(NODE_STR)
        result = ''
        result_plain = ''
        for e in plain_elems:
            tag_name = e.xpath('name()').extract_first()
            if tag_name is None:
                text = e.extract()
                result += text or ''
                result_plain += text or ''
            else:
                if tag_name == 'br':
                    result += '\n'
                    result_plain += '\n'
                elif tag_name == 'a':
                    a_text = e.xpath('text()').extract_first()
                    href = response.urljoin(e.xpath('@href').extract_first())
                    result += '[%s]{%s}' % (a_text, response.urljoin(href))

                    if a_text is None:
                        result_plain += href
                    elif 'user/viewprofilepage/user-id' in href:
                        result_plain += a_text
                    elif len(a_text) > 3 and href.startswith(a_text[:-3]):
                        result_plain += href
                    else:
                        result_plain += '%s %s' % (a_text, href)

                elif tag_name == 'blockquote':
                    quote_paragraphs = [concat_plain_elems(e2)[0] for e2 in [e] + e.xpath('p')]
                    result += '\n['+CAPTION_BLOCKQUOTE+']{' + '\n'.join(quote_paragraphs) + '}'
                elif tag_name == 'img':
                    img_src = response.urljoin(e.xpath('@src').extract_first())
                    result += '[%s]{%s}' % (CAPTION_IMAGE, img_src)
                    result_plain += img_src
                else:
                    result += '[%s]{%s} ' % (CAPTION_UNKNOWN, e.extract())
        return result.replace('\u00a0', ' ').strip(), result_plain.replace('\u00a0', ' ').strip()

    text, text_plain = concat_plain_elems(message.css('.lia-message-body-content'))
    concat_result = [concat_plain_elems(e) for e in message.css('.lia-message-body-content > p')]
    if len(concat_result) > 0:
        paragraphs, paragraphs_plain = zip(*[concat_plain_elems(e) for e in message.css('.lia-message-body-content > p')])
    else:
        paragraphs, paragraphs_plain = [], ''

    if text != '':
        result['content'] = text
    else:
        result['content'] = '\n'.join(paragraphs)
    if text_plain != '':
        result['content_plain'] = text_plain.strip()
    else:
        result['content_plain'] = '\n'.join(paragraphs_plain).strip()

    result['has_quote'] = any('[%s]' % CAPTION_BLOCKQUOTE in c for c in result['content'])
    result['has_image'] = any('[%s]' % CAPTION_IMAGE in c for c in result['content'])

    result['url'] = response.urljoin(message.css('.lia-message-position-in-thread a::attr(href)').extract_first())
    #result['is_solution'] = message.css('.lia-component-solution-info').extract_first() is not None
    result['solution_accepted_by'] = message.css('.lia-component-solution-info .solution-accepter > a::text').extract_first()

    return result


def parse_question(response):
    q = response.css('.lia-thread-topic')
    assert len(q) == 1, 'unexpected number of questions: %i for url: %s' % (len(q), response.request.url)
    return process_message_view(q[0], response)


def parse_answers(response):
    m_list = response.css('.message-list')[0]
    replies_header = m_list.css('.lia-replies-header')
    # get lia-thread-reply_s (MessageView_s)
    if len(replies_header) == 0:
        #answers = m_list.css('.lia-thread-reply')
        answers = m_list.css('.lia-message-view-wrapper')
    elif len(replies_header) == 1:
        #answers = replies_header.xpath('following-sibling::div').css('.lia-thread-reply')
        answers = replies_header.xpath('following-sibling::div').css('.lia-message-view-wrapper')
    else:
        raise ValueError(
            'Unexpected number of replies header in message-list: %i. Expected 0 or 1.' % len(replies_header))
    answers = [process_message_view(answ, response) for answ in answers]
    return answers


class QuestionsSpider(scrapy.Spider):
    name = "questions"

    def start_requests(self):
        intent_file = getattr(self, 'intent_file', None)
        assert intent_file is not None, 'no intent_file set. Please specify a intent_file via scrapy parameters: "-a intent_file=PATH_TO_INTENT_FILE"'

        logging.info('load %s from file: %s' % (QUESTION_PREFIX, intent_file))
        intents = get_intents_from_tsv(intent_file)
        urls = flatten([intent['links'] for intent in intents])
        dir = Path(intent_file).parent
        intents_backup_fn = (dir / 'intents.jl').resolve()
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
        yield {'url': response.url, 'title': title, 'solved': solved, 'tags': tags, 'question': question, 'answers': answers}


class AnswersSpider(scrapy.Spider):
    name = "answers"

    def start_requests(self):
        intent_file = getattr(self, 'intent_file', None)
        assert intent_file is not None, 'no intent_file set. Please specify a intent_file via scrapy parameters: "-a intent_file=PATH_TO_INTENT_FILE"'

        logging.info('load %s from file: %s' % (ANSWER_PREFIX, intent_file))
        intents = get_intents_from_tsv(intent_file)
        urls = flatten([intent['links'] for intent in intents])
        dir = Path(intent_file).parent
        intents_backup_fn = (dir / 'intents.jl').resolve()
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
        yield answers_dict[response.request.url]


