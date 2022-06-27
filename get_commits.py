"""
Created on June 25, 2022

Retrieves all commits for a series of repos
"""

import os
import handle_GH_paging as gh
import traceback
import json
import argparse

# page size for GitHub API
PAGE_SIZE = 100
# GITHUB_URL for organiztion in GitHub
GITHUB_API_URL = 'https://api.github.com'
gh_token = os.getenv('GH_ACCESS_TOKEN')
if gh_token is None:
    raise Exception('GH_ACCESS_TOKEN environment variable not defined.')
gh_headers = {"Authorization": "token %s" % gh_token, "Accept": "application/vnd.github.v3+json"}
parms = dict(per_page='%s' % PAGE_SIZE)


def get_args():
    parser = argparse.ArgumentParser(
        description='Gets information for all commits in a series repos')
    # Add arguments
    parser.add_argument(
        '-r', '--repos', type=str, help='list of org/repos, comma separated', required=True)
    parser.add_argument(
        '-f', '--filename', type=str, help='Filename for output. If not specified, output is sent to stdout.', default=None)
    parser.add_argument(
        '-s', '--since', type=str, help='Return commits after the given time. This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.', default=None)
    parser.add_argument(
        '-u', '--until', type=str, help='Return commits up until the given time. This is a timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.', default=None)
    args = parser.parse_args()
    repos = args.repos
    filename = args.filename
    since = args.since
    until = args.until

    return repos, filename, since, until

def output_results(results_str, output_file):
    if output_file is not None:
        output_file.write(results_str + '\n')
    else:
        print(results_str)


def main():
    try:
        repos, output_filename, since, until = get_args()
        if since is not None:
            parms['since'] = since
        if until is not None:
            parms['until'] = until
        if output_filename is not None:
            output_file = open(output_filename, 'w')
        else:
            output_file = None

        for repo in repos.split(','):
            repo = repo.strip()
            print("Processing %s" % repo)
            # get all the commits for this repo
            commits = gh.makeCall('%s/repos/%s/commits' % (GITHUB_API_URL, repo), gh_headers, parms,
                                            print_status=True)
            output_results("%s, %s" % (repo, len(commits)), output_file)

        if output_file is not None:
            output_file.close()

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
