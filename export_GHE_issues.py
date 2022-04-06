"""
Created on Mar 31, 2016

Exports Issues from a specified repository to stdout separated by tabs

Requires a personal access token generated from GHE settings be defined
to environment variable GHE_ACCESS_TOKEN in .bashrc and/or .profile.
Looks like .profile is required for interactive terminal window.

For syntax:
    Python ./Export_GHE_Issues.py -h

Otherwise, parameters are as documented for issues through the GitHub API:
    https://developer.github.com/v3/issues/
"""

import argparse
import csv
import traceback
import handle_GHE_calls
import os

page_size = 50

"""
Get and validate command line args
"""


def get_args():

    parser = argparse.ArgumentParser(
        description='Exports issues from a specified repository' +
                    ' to stdout separated by tabs. In addition to server, repo,' +
                    ' and csvfile, parameters are the same as the GitHub issues API for querying a repo (vs a user): ' +
                    'https://developer.github.com/v3/issues/.')
    # Add arguments
    parser.add_argument(
        '-s', '--server', type=str, help='GitHub Enterprise server name. ', required=True)
    parser.add_argument(
        '-r', '--repo', type=str, help='GitHub Enterprise repository ' +
                                       'in the form of Github organization/repository name.', required=True)
    parser.add_argument(
        '-f', '--file', type=str, help='Output file name.' +
                                       'Default is ~/Github Organization_repository name.csv.')
    parser.add_argument(
        '-m', '--milestone', type=str)
    parser.add_argument(
        '-t', '--state', type=str)
    parser.add_argument(
        '-a', '--assignee', type=str)
    parser.add_argument(
        '-c', '--creator', type=str)
    parser.add_argument(
        '-n', '--mentioned', type=str)
    parser.add_argument(
        '-l', '--labels', type=str)
    parser.add_argument(
        '-o', '--sort', type=str)
    parser.add_argument(
        '-d', '--direction', type=str)
    parser.add_argument(
        '-i', '--since', type=str)

    args = parser.parse_args()
    server = args.server
    repo = args.repo
    if args.file is None:
        file = repo.replace('/', '_') + ".csv"
    else:
        file = args.file
    milestone = args.milestone
    state = args.state
    assignee = args.assignee
    creator = args.creator
    mentioned = args.mentioned
    labels = args.labels
    sort = args.sort
    direction = args.direction
    since = args.since
    repo_url = 'https://%s/api/v3/repos/%s/issues' % (server, repo)

    return repo_url, file, milestone, state, assignee, creator, mentioned, labels, sort, direction, since

"""
Export the GHE Issues
"""
def export_issues(repo_url, milestone, state, assignee, creator, mentioned, labels, sort, direction, since, pagesize):
    ghe_token = os.getenv('GHE_ACCESS_TOKEN')
    if ghe_token is None:
        raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
    headers = dict(Authorization='token %s' % ghe_token)
    parameters = dict(milestone=milestone, state=state, assignee=assignee, creator=creator, mentioned=mentioned,
                      labels=labels, sort=sort, direction=direction, since=since, per_page='%s' % pagesize)

    issues = handle_GHE_calls.makeCall(repo_url, headers, parameters)

    return issues

"""
Processes the issues and writes to the csv file
"""

def process_issues(issues, csv_file):
    print('Writing issues to \'' + csv_file + '\'.')
    f = open(csv_file, 'w')
    csv_out = csv.writer(f, dialect='excel', quoting=csv.QUOTE_NONNUMERIC)
    columns = ('Number', 'State', 'Creator', 'Assignee', 'Title', 'Body', 'Labels',
               'Milestone', 'Created', 'Updated', 'GITHUB_URL')
    csv_out.writerow(columns)

    for issue in issues:
        labels = issue['labels']
        if len(labels) == 0:
            labels_string = ''
        else:
            labels_string = labels[0]['name']
        if len(labels) > 1:
            for i in range(1, len(labels)):
                labels_string += (', ' + labels[i]['name'])

        if issue['milestone'] is None:
            milestone_string = ''
        else:
            milestone_string = issue['milestone']['title']

        if issue['assignee'] is None:
            assignee_string = ''
        else:
            assignee_string = issue['assignee']['login']

        row = (issue['number'],
               issue['state'],
               issue['user']['login'],
               assignee_string,
               issue['title'],
               issue['body'],
               labels_string,
               milestone_string,
               issue['created_at'].replace('Z', '').replace('T', ' '),
               issue['updated_at'].replace('Z', '').replace('T', ' '),
               issue['html_url'])
        csv_out.writerow(row)

    f.close()
    print('Finished writing %s issue(s).' % len(issues))

"""
Main method
"""

def main():
    try:
        repo_url, file, milestone, state, assignee, creator, mentioned, labels, sort, direction, since = get_args()
        issues = export_issues(repo_url, milestone, state, assignee, creator, mentioned, labels, sort, direction, since, page_size)
        process_issues(issues, file)
    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()

if __name__ == '__main__':
    main()
