## example workflow
```bash
# scrape links to QUESTIONS mentioned in columns beginning with "Similar_Question_Link" ...
scrapy crawl questions -L INFO -a intent_file=questions/Crowdsourcing-Intents-Intent-List.tsv -o questions/scraped.jl
# ... OR scrape links to ANSWERS mentioned in columns beginning with "Answer"
scrapy crawl answers -L INFO -a intent_file=answers/Crowdsourcing-Intents-Answers-List.tsv -o answers/scraped.jl
```

```python3
import questionscraper.spiders.helper as h

# generate stats for questions ...
h.calc_stats_questions()
# ... or for answers
h.calc_stats_answers()

# merge final answers into intents:
# for answers ...
h.merge_answers_to_intents(intents_jsonl='answers/intents.jl', scraped_answers_jsonl='answers/scraped.jl')
# ... for questions
h.merge_answers_to_intents(intents_jsonl='questions/intents.jl', scraped_questions_jsonl='questions/scraped.jl')

# generate sql files for mdswriter
# for questions:
h.create_sql_inserts_questions()
# or for answers:
h.create_sql_inserts_answers()
```

*NOTE*: `adjust_tables.sql` has to be executed before the other sql files. Otherwise smileys etc will cause errors.
