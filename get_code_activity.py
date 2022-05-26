"""
Created on May 25, 2022

Retrieves all pulls and commits for a repo and lists authors
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
        description='Gets information for all pulls in a repo')
    # Add arguments
    parser.add_argument(
        '-r', '--repo', type=str, help='Org/repo to list the pulls for', required=True)
    parser.add_argument(
        '-o', '--output', type=str, help='Filename for output. Default is \'output.csv\'.', default='output.csv')

    args = parser.parse_args()
    repo = args.repo
    output = args.output

    return repo, output


def main():
    try:
        repo, output_filename = get_args()
        output_file = open(output_filename, 'w')

        output_file.write('repo, type, login, name, company, blog, location, email\n')

        # get all the pulls for this repo
        pulls = gh.makeCall('%s/repos/%s/pulls?state=all' % (GITHUB_API_URL, repo), gh_headers, parms,
                                          print_status=True)
        count = 0
        for pull in pulls:
            if pull.get('user') is not None:
                # User may be none if this user id not longer on Github
                try:
                    user_detail = gh.makeCall(pull['user']['url'], gh_headers, parms)
                    output_file.write('%s, pull, %s, %s, %s, %s, %s, %s\n' % (repo, user_detail['login'], user_detail['name'], user_detail['company'], user_detail['blog'],
                        user_detail['location'], user_detail['email']))
                except Exception as e:
                    print(print('Error: ' + str(e)))
            count += 1
            if count % 10 == 0:
                print(count)
        print("\n")

        # get all the commits for this repo
        commits = gh.makeCall('%s/repos/%s/commits' % (GITHUB_API_URL, repo), gh_headers, parms,
                                          print_status=True)
        count = 0
        for commit in commits:
            if commit.get('author') is not None:
                # Author may be none if this user id not longer on Github
                try:
                    author_detail = gh.makeCall(commit['author']['url'], gh_headers, parms)
                    output_file.write('%s, commit, %s, %s, %s, %s, %s, %s\n' % (repo, author_detail['login'], author_detail['name'], author_detail['company'], author_detail['blog'],
                        author_detail['location'], author_detail['email']))
                except Exception as e:
                    print(print('Error: ' + str(e)))
            count += 1
            if count % 10 == 0:
                print(count)
        print("\n")

        output_file.close()

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
