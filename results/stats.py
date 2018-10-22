import csv
import os
from collections import Counter

import plac


def load_results(path, ext='.csv'):
    res = []
    for fn in os.listdir(path):
        if fn.endswith(ext):
            res.append(list(csv.DictReader(open(os.path.join(path, fn)))))
    return res


def main(path):
    data = load_results(path)
    queries = [[job['DynamicContent.query'].replace('<div class="query">', '').replace('</div>', '') for job in jobset]
               for jobset in data]
    queries_flat = [item for sublist in queries for item in sublist]
    queries_c = Counter(queries_flat)
    with open(os.path.join(path, 'counts.tsv'), 'w') as tsv:
        writer = csv.DictWriter(tsv, fieldnames=['query', 'count'], delimiter='\t')
        writer.writeheader()
        for q, c in queries_c.most_common():
            writer.writerow({'query': q, 'count': c})

    worker = [[job['Worker'] for job in jobset] for jobset in data]
    worker_flat = [item for sublist in worker for item in sublist]
    worker_nbr = len(set(worker_flat))
    print('nbr of workers: %i' % worker_nbr)
    print('done')


if __name__ == '__main__':
    plac.call(main)