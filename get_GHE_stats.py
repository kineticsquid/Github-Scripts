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
import my_logger

# page size for GitHub API
PAGE_SIZE = 100
# GITHUB_URL for organiztion in GitHub
GITHUB_API_URL = 'https://githubcom/api/v3'
ORG_GITHUB_URL = '%s/orgs/blueyoda' % GITHUB_API_URL
ghe_token = os.getenv('GHE_ACCESS_TOKEN')
if ghe_token is None:
    raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
HEADERS = dict(Authorization='token %s' % ghe_token)
PARAMETERS = dict(per_page='%s' % PAGE_SIZE)
OUTPUT_FILE_NAME = './Input_and_Output/github-stats.txt'
COMPLETED_FILE_NAME = './Input_and_Output/completed.txt'

"""
Main method
"""


def main():
    try:
        try:
            completed_file = open(COMPLETED_FILE_NAME, 'r')
            completed = []
            for line in completed_file:
                completed.append(line.strip())
            completed_file.close()
            # we're starting with some completed, so open outfile for append
            output_file = open(OUTPUT_FILE_NAME, 'a')
        except FileNotFoundError:
            completed = []
            # otherwise, starting from the beginning, so open output file for write
            output_file = open(OUTPUT_FILE_NAME, 'w')
            columns = 'Repo,Action,Issue #,Date,Date/Time,Author\n'
            output_file.write(columns)

        logger = my_logger.get_logger()

        # get all the repos for this organization
        repos = handle_GHE_calls.makeCall('%s/repos' % ORG_GITHUB_URL, HEADERS, PARAMETERS, logger=logger,
                                          print_status=True)
        # create new request parameters to get all of the issues (not just the open ones)
        issues_parameters = PARAMETERS.copy()
        issues_parameters['state'] = 'all'
        count = 1

        for repo in repos:
            if repo['name'] not in completed:
                logger.info('Processing repo: %s - %s of %s.' % (repo['name'], count, len(repos)))
                repo_url = repo['url']

                # we're keeping output for the current repo in list and will write it only when all processing is
                # completed.

                output_for_curreent_repo = []

                # get all of the issues for this repo and loop through each issue. If there are comments, write info
                # about the comment to the output file
                # issues = handle_GHE_paging.getAllPages('%s/issues' % repo_url, HEADERS, issues_parameters, logger=logger,
                #                                        print_status=True)
                # for issue in issues:
                #     comments_url = issue.get('comments_url', None)
                #     if comments_url is not None:
                #         comments = handle_GHE_paging.getAllPages(comments_url, HEADERS, PARAMETERS)
                #         for comment in comments:
                #             end_of_date = comment['created_at'].find('T')
                #             date = comment['created_at'][0:end_of_date]
                #             user = comment.get('user', None)
                #             if user is not None:
                #                 user = user['login']
                #             row = '%s,comment,%s,%s,%s,%s\n' % (
                #                 repo['name'], issue['number'], date, comment['created_at'], user)
                #             output_for_curreent_repo.append(row)

                # get all of the pull requests for this repo and loop through each PR. If there are commits, write info
                # about the commit to the output file
                pulls = handle_GHE_calls.makeCall('%s/pulls' % repo_url, HEADERS, issues_parameters, logger=logger,
                                                  print_status=True)
                for pull in pulls:
                    commits_url = pull.get('commits_url', None)
                    if commits_url is not None:
                        commits = handle_GHE_calls.makeCall(commits_url, HEADERS, PARAMETERS)
                        for commit in commits:
                            end_of_date = pull['created_at'].find('T')
                            date = pull['created_at'][0:end_of_date]
                            author = commit.get('author', None)
                            if author is not None:
                                author = author['login']
                            row = '%s,commit,%s,%s,%s,%s\n' % (
                                repo['name'], pull['number'], date, pull['created_at'], author)
                            output_for_curreent_repo.append(row)
                # we're finished with this repo, so write the output and add the repo name to the completed list
                for line in output_for_curreent_repo:
                    output_file.write(line)
                completed.append(repo['name'])
            logger.info('Finished with repo %s.' % repo['name'])
            count += 1
        # success, so if we have a file of completed entries from a previous partial run, remove it
        if os.path.isfile(COMPLETED_FILE_NAME):
            os.remove(COMPLETED_FILE_NAME)
    except Exception as e:
        # we've encountered an error, so record all the entries we've successfully processed
        completed_file = open(COMPLETED_FILE_NAME, 'w')
        for line in completed:
            completed_file.write('%s\n' % line)
        completed_file.close()
        print('Error: ' + str(e))
        traceback.print_exc()
    finally:
        output_file.close()



if __name__ == '__main__':
    main()
