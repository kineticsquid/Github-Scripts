"""
Created on May 25, 2022

Retrieves all pulls and commits for a repo and lists authors
"""

import os
import handle_GH_paging as gh
import traceback
import argparse
from datetime import datetime

# page size for GitHub API
PAGE_SIZE = 100
# Github API entry point
GITHUB_API_URL = 'https://api.github.com'
# Github access token - get from your Github settings
gh_token = os.getenv('GH_ACCESS_TOKEN')
if gh_token is None:
    raise Exception('GH_ACCESS_TOKEN environment variable not defined.')
gh_headers = {"Authorization": "token %s" % gh_token, "Accept": "application/vnd.github.v3+json"}
parms = dict(per_page='%s' % PAGE_SIZE)

# Dictionary cache of user information to save calls and rate limiting
users = {}

def get_args():
    parser = argparse.ArgumentParser(
        description='Gets information for all pulls and commits in a Github repo or list of repos')
    parser.add_argument(
        '-r', '--repo', type=str, help='Org/repo to list the pulls for')
    parser.add_argument(
        '-f', '--file', type=str, help='File with list of org/repos, one per line, to list the pulls and commits for')
    parser.add_argument(
        '-o', '--output', type=str, help='Filename for output. Default is \'output.csv\'.', default='output.csv')

    args = parser.parse_args()
    repo = args.repo
    input_filename = args.file
    output_filename = args.output

    return repo, input_filename, output_filename

# Routine to get info on a pull/commit user and cache it
def get_user_info(user_url):
    user_detail = users.get(user_url)
    if user_detail is None:
        user_detail = gh.makeCall(user_url, gh_headers, parms)
        users[user_url] = user_detail
    return user_detail

# Convert an ISO format date into something Excel will recognize in a CSV import
def convert_date(iso_date_string):
    if iso_date_string is not None:
        d = datetime.strptime(iso_date_string, '%Y-%m-%dT%H:%M:%SZ')
        return str(d.date())
    else:
        return None

# Process a repo
def process_repo(repo, output_file):
    print("Processing \'%s\'" % repo)

    # get all the commits for this repo
    commits = gh.makeCall('%s/repos/%s/commits' % (GITHUB_API_URL, repo), gh_headers, parms,
                                        print_status=True)
    count = 0
    for commit in commits:
        if commit.get('author') is not None:
            # Author may be none if this user id not longer on Github
            try:
                author_detail = get_user_info(commit['author']['url'])
                iso_date = commit['commit']['committer']['date']
                date = convert_date(iso_date)
                if date is not None and '[bot]' not in author_detail['login']:
                    output_file.write('%s,commit,%s,%s,%s\n' % (repo, date, author_detail['login'], author_detail['name']))
            except Exception as e:
                print(print('Error: ' + str(e)))
        count += 1
        if count % 10 == 0:
            print(count)

    # get all the pulls for this repo
    pulls = gh.makeCall('%s/repos/%s/pulls?state=all' % (GITHUB_API_URL, repo), gh_headers, parms,
                                        print_status=True)
    count = 0
    for pull in pulls:
        if pull.get('user') is not None:
            # User may be none if this user id not longer on Github
            try:
                user_detail = get_user_info(pull['user']['url'])
                iso_date = pull['closed_at']
                date = convert_date(iso_date)
                if date is not None and '[bot]' not in user_detail['login']:
                    output_file.write('%s,pull,%s,%s,%s\n' % (repo, date, user_detail['login'], user_detail['name']))
            except Exception as e:
                print(print('Error: ' + str(e)))
        count += 1
        if count % 10 == 0:
            print(count)


def main():
    try:
        input_repo, input_filename, output_filename = get_args()
        output_file = open(output_filename, 'w')
        output_file.write('repo, type, date, login, name\n')

        if input_repo is not None:
            process_repo(input_repo.strip(), output_file)
        elif input_filename is not None: 
            input_file = open(input_filename, 'r')
            for repo in input_file:
                process_repo(repo.strip(), output_file)
        else:
            raise Exception('You must specify either a repo (-r) or an input file (-f).')
        output_file.close()

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
