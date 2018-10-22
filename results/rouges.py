import json
import csv

file_name = 'rouges'


def worker_to_row(worker_id, workers, reference, rating=None):
    worker_data = workers[worker_id]
    if worker_data['answer'].strip() == '':
        return {'id': worker_id }
    res = {'id': worker_id, 'summary/WORKER': worker_data['answer']}
    stats = {}
    for ref_id in reference:
        ref = worker_data['reference_%s' % ref_id][0]
        for metric in ref:
            for k in ref[metric]:
                res['%s/%s/%s' % (metric, k, ref_id)] = ref[metric][k]
                stats['%s/%s' % (metric, k)] = stats.get('%s/%s' % (metric, k), [])
                stats['%s/%s' % (metric, k)].append(ref[metric][k])
        res['summary/%s' % ref_id] = reference[ref_id]
    for s in stats:
        res['%s/AVG' % s] = sum(stats[s]) / len(stats[s])
        res['%s/MAX' % s] = max(stats[s])
        res['%s/MIN' % s] = min(stats[s])
    if rating is not None:
        res.update({'x-%s' % r: rating[r] for r in rating})
    return res


if __name__ == '__main__':

    ratings = list(csv.DictReader(open('ratings.tsv'), delimiter='\t'))
    ratings_dict = {r['Worker']: r for r in ratings if r['Worker'] and r['Worker'].strip()}
    #rating_ids = set([r['Worker'] for r in ratings])
    rouges = json.load(open('%s.json' % file_name))
    rows = [worker_to_row(w_id, rouges['workers'], rouges['reference'], ratings_dict.get(w_id, None)) for w_id in rouges['workers']]
    #rows = list(filter(None, rows))
    #fieldnames = sorted(rows[0].keys())
    fieldnames = sorted(list(set([item for sublist in map(lambda x: x.keys(), rows) for item in sublist])))
    with open('%s.tsv' % file_name, 'w') as tsv:
        writer = csv.DictWriter(tsv, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
