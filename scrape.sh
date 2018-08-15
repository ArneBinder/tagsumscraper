#!/bin/bash

# usage: ./scrape.sh [DIRECTORY] [INTENT_FILE] [MAX_ANSWERS]

## use first argument as directory
if [ -n "$1" ]; then
    DIR="$1"
else
    DIR=scraped
fi

if [ ! -d "$DIR" ]; then
    mkdir "$DIR"
fi


## use second argument as INTENT_FILE
if [ -n "$2" ]; then
    INTENT_FILE="$2"
else
    INTENT_FILE="$DIR/Crowdsourcing-Intents-Intent-Answers_List.tsv"
fi

if [ ! -f "$INTENT_FILE" ]; then
    echo "File not found: $INTENT_FILE"
    exit 1
fi

## use third argument as max answers
if [ -n "$3" ]; then
    MAX_ANSWERS="$3"
else
    MAX_ANSWERS=10
fi

# scrape answers
if [ ! -f "$DIR/scraped_answers_$MAX_ANSWERS".jl ]; then
    scrapy crawl answers -L INFO -a intent_file="$INTENT_FILE" -o "$DIR/scraped_answers_$MAX_ANSWERS".jl
else
    echo "skip scraping answers. file exists: $DIR/scraped_answers_$MAX_ANSWERS".jl
fi
# merge
if [ ! -f "$DIR/intents_answers_$MAX_ANSWERS"_merged.jl ]; then
    python questionscraper/spiders/helper.py --intents-jsonl "$DIR/intents_answers_$MAX_ANSWERS".jl --out-dir "$DIR" --scraped-answers-jsonl "$DIR/scraped_answers_$MAX_ANSWERS".jl
else
    echo "skip merging answers. file exists: $DIR/intents_answers_$MAX_ANSWERS"_merged.jl
fi

# scrape questions
if [ ! -f "$DIR/scraped_questions_$MAX_ANSWERS".jl ]; then
    scrapy crawl questions -L INFO -a intent_file="$DIR/intents_answers_$MAX_ANSWERS"_merged.jl -o "$DIR/scraped_questions_$MAX_ANSWERS".jl
else
    echo "skip scraping questions. file exists: $DIR/scraped_questions_$MAX_ANSWERS".jl
fi
# merge questions
if [ ! -f "$DIR/intents_questions_$MAX_ANSWERS"_merged.jl ]; then
    python questionscraper/spiders/helper.py --intents-jsonl "$DIR/intents_questions_$MAX_ANSWERS".jl --out-dir "$DIR" --scraped-questions-jsonl "$DIR/scraped_questions_$MAX_ANSWERS".jl
else
    echo "skip merging answers. file exists: $DIR/intents_questions_$MAX_ANSWERS"_merged.jl
fi
