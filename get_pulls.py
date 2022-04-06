"""
Created on Jul 14, 2017

Lists GitHub activity, at least commits and comments to issues, for all repos under an organization.

I'm writing to a txt file, instead of a csv, so that excel will convert the date string on the way in to a proper date.

For syntax:
    Python ./GitAllGitHubRepos.py -h
"""

import os
import handle_GHE_calls
import traceback
import json

# page size for GitHub API
PAGE_SIZE = 100
# GITHUB_URL for organiztion in GitHub
GITHUB_API_URL = 'https://github.com/api/v3'
ORG_GITHUB_URL = '%s/orgs/blueyoda' % GITHUB_API_URL
ghe_token = os.getenv('GHE_ACCESS_TOKEN')
if ghe_token is None:
    raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
HEADERS = dict(Authorization='token %s' % ghe_token)
PARAMETERS = dict(per_page='%s' % PAGE_SIZE)

"""
Main method
"""


def main():
    try:
        # get all the repos for this organization
        repos = handle_GHE_calls.makeCall('%s/repos' % ORG_GITHUB_URL, HEADERS, PARAMETERS,
                                          print_status=True)
        # create new request parameters to get all of the issues (not just the open ones)
        issues_parameters = PARAMETERS.copy()
        issues_parameters['state'] = 'all'
        count = 0
        pull_count = {}

        for repo in repos:
            repo_url = repo['url']
            pulls = handle_GHE_calls.makeCall('%s/pulls' % repo_url, HEADERS, issues_parameters,
                                              print_status=True)
            print('processing %s - %s pulls' % (repo_url, len(pulls)))
            for pull in pulls:
                commits_url = pull.get('commits_url', None)
                if commits_url is not None:
                    commits = handle_GHE_calls.makeCall(commits_url, HEADERS, PARAMETERS)
                    for commit in commits:
                        author = commit.get('author', None)
                        if author is not None:
                            author = author['login']
                            current_author_count = pull_count.get(author, None)
                            if current_author_count is not None:
                                pull_count[author] = pull_count[author] + 1
                            else:
                                pull_count[author] = 1
            count += 1
            print('finished processing %s of %s' % (count, len(repos)))

        print(json.dumps(pull_count, indent=4))

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
