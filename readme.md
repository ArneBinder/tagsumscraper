## example workflow
```bash
# scrape links to ANSWERS mentioned in columns beginning with "Answer_"
scrapy crawl answers -L INFO -a intent_file=answers/Crowdsourcing-Intents-Answers-List.tsv -o answers/scraped.jl
```

```python3
import questionscraper.spiders.helper as h

# merge answers back into intents:
h.merge_answers_to_intents(intents_jsonl='answers/intents.jl', scraped_answers_jsonl='answers/scraped.jl')
```

```bash
cp answers/intents_merged.jl questions/intents_merged_answers.jl
# scrape links to QUESTIONS mentioned in `intents_merged.jl` from previous answer scrape
scrapy crawl questions -L INFO -a intent_file=questions/intents_merged_answers.jl -o questions/scraped.jl
```

```python3
import questionscraper.spiders.helper as h
# merge
h.merge_answers_to_intents(intents_jsonl='questions/intents.jl', scraped_questions_jsonl='questions/scraped.jl')

# generate sql files for mdswriter
# for questions:
h.create_sql_inserts_questions()
# or for answers:
h.create_sql_inserts_answers()
```

*NOTE*: `adjust_tables.sql` has to be executed before the other sql files. Otherwise smileys etc will cause errors.
