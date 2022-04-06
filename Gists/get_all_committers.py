"""
Created on Jan 2022

Scans all commits to create a list of all who have committed to repos in an org

"""

import os
import traceback
import requests
import time

# page size for GitHub API
PAGE_SIZE = 100
# Seconds to wait for requests call to return before failing
DEFAULT_TIMEOUT = 30
# Seconds to wait between retries
WAIT_TIME = 1
# Max number of times to retry
MAX_RETRIES = 1

# Access token from GitHub acct settings. If needs read access to the org, repos, users, commits, and pull requests
ghe_token = os.getenv('GHE_ACCESS_TOKEN')
# GitHub org you're scanning
github_org = os.getenv('GHE_ORG')

# Filename for output in CSV format
output_filename = os.getenv('OUTPUT_FILENAME')

# Dictionary to keep track of information for users we've encountered, so save API calls to /user
USERS = {}

GITHUB_API_URL = 'https://api.github.com'
ORG_GITHUB_URL = '%s/orgs/%s' % (GITHUB_API_URL, github_org)

HEADERS = dict(Authorization='token %s' % ghe_token)
PARAMETERS = dict(per_page='%s' % PAGE_SIZE)

"""
Handles paging of GitHub API requests

Takes as input a url, headers dictionary, and parameters dictionary. The headers
dictionary must have the GitHub Enterprise access token defined in "token". The parameters
dictionary must have page size defined in "per_page".

Returns an array of aggregated results.
"""

def makeGitHubCall(url, headers, parameters):

    results = []
    while url is not None:
        retries = 0
        while True:
            try:
                if parameters is None:
                    response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
                else:
                    response = requests.get(url, params=parameters, headers=headers, timeout=DEFAULT_TIMEOUT)
                break
            except:
                retries += 1
                time.sleep(WAIT_TIME)
                print('Retrying %s' % url)

            if retries > MAX_RETRIES:
                raise Exception('Max retries error getting %s' % url)

        if response.status_code == 200:
            response_page_link = response.headers.get('link', default=None)
            if response_page_link is None:
                url = None
            else:
                next_page_link = response.links.get('next', None)
                if next_page_link is None:
                    url = None
                else:
                    url = next_page_link.get('url')
            new_results = response.json()
            print("Retrieved items %s to %s." % (str(len(results) + 1), str(len(results) + len(new_results))))

            if len(results) == 0:
                results = new_results
            else:
                results = results + new_results
        elif response.status_code == 403:
                rate_limit_remaining = response.headers['x-ratelimit-remaining']
                if int(rate_limit_remaining) == 0:
                    # We've reached our rate limit and need to wait
                    rate_limit_reset = response.headers['x-ratelimit-reset']
                    time_to_wait = int(rate_limit_reset) - int(time.time())
                    wait_until = time.strftime('%H:%M:%S', time.localtime(int(rate_limit_reset)))
                    print('API limit reached. Waiting for %s seconds, until %s.' %  (time_to_wait, wait_until))
                    time.sleep(time_to_wait)
                    print('It\'s now %s. Starting again.' %  wait_until)
                else:
                    # Some other error resulting in 403 so raise an exception
                    raise Exception("%s: %s" % (response.status_code, url))
        elif response.status_code == 409:
            # This covers the case where empty repos return 409 when asking for commits
            print('\'%s\' returned 409, empty repo.' % url)
            url = None
        else:
            raise Exception("%s: %s" %(response.status_code, url))

    return results

"""
Method to collect and return user information given an API URL
"""

def get_user_info(user_url):
    if user_url not in USERS:
        response = requests.get(user_url, HEADERS)
        if response.status_code != 200:
            print('%s error with \'%s\'.' % (response.status_code, user_url))
            USERS[user_url] = None
        else:
            user_info = response.json()
            USERS[user_url] = user_info
    return USERS[user_url]


"""
Main method
"""

def main():
    try:
        # get all the repos for this organization
        repos = makeGitHubCall('%s/repos' % ORG_GITHUB_URL, HEADERS, PARAMETERS)
        count = 1
        output_file = open(output_filename, 'w')
        output_file.write('Name, Login ID, email, Type, Repo, Fork?\n')
        for repo in repos:
            print('Processing repo \'%s\', %s of %s.' % (repo['name'], count, len(repos)))
            repo_url = repo['url']
            print('Getting commits')
            commits = makeGitHubCall('%s/commits' % repo_url, HEADERS, PARAMETERS)
            for commit in commits:
                if commit.get('author') is not None and commit['author']['login'] != 'web-flow':
                    user_info = get_user_info(commit['author']['url'])
                    if user_info is not None:
                        output_file.write('%s, %s, %s, Author, %s, %s\n' %
                                      (user_info['name'], user_info['login'], user_info['email'], repo['name'],
                                       repo['fork']))
                    else:
                        output_file.write('%s, %s, %s, Author, %s, %s\n' %
                                      ('None', commit['author']['login'], 'None', repo['name'],
                                       repo['fork']))
                else:
                    print('Commit in repo %s has no author' % repo['name'])
                if commit.get('committer') is not None and commit['committer']['login'] != 'web-flow':
                    user_info = get_user_info(commit['committer']['url'])
                    if user_info is not None:
                        output_file.write('%s, %s, %s, Committer, %s, %s\n' %
                                      (user_info['name'], user_info['login'], user_info['email'], repo['name'],
                                       repo['fork']))
                    else:
                        output_file.write('%s, %s, %s, Committer, %s, %s\n' %
                                      ('None', commit['committer']['login'], 'None', repo['name'],
                                       repo['fork']))
                else:
                    print('Commit in repo %s has no committer' % repo['name'])
            count += 1
        output_file.close()

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
