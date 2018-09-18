
import json
import argparse


def main(fn_in, fn_out):
    with open(fn_in) as f_in:
        summary = json.load(f_in)
    dc_dict = {c['identifier']: c  for c in summary['dynamicContent']}
    #nbr_posts = 10
    nbr_posts = len(dc_dict['Post1']['values'])
    res = []
    for i, intent_text in enumerate(dc_dict['query']['values']):
        posts = sorted([dc_dict['Post%i' % j]['values'][i] for j in range(1, nbr_posts+1, 1)], key=len, reverse=True)
        posts_body = ''.join(['<tr><td>%s</td><td>%s</td></tr>'
                              % (posts[j], posts[j + 1]) for j in range(0, len(posts), 2)])

        res.append({'query': intent_text,
                    'posts': '<table><tbody>%s</tbody></table>' % posts_body})

    with open(fn_out, mode='w') as f_out:
        json.dump(res, f_out, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Put posts from json into table.')
    parser.add_argument('inputfile', metavar='input-file', type=str,
                        help='input json file name')
    parser.add_argument('outputfile', metavar='output-file', type=str,
                        help='output json file name')
    args = parser.parse_args()
    main(fn_in=args.inputfile, fn_out=args.outputfile)


