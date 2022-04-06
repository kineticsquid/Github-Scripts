"""
Created on Feb 8, 2019

Script to create a series of issues in a Zenhub epic. See argparse description for detail.

Github API: https://developer.github.com/v3/
Zenhub API: https://github.com/ZenHubIO/API
"""

import requests
import traceback
import handle_GHE_calls as ghe
import handle_zenhub_calls as zh
import os
import json
import re
import argparse
import urllib3


# Timeout value on the http REST calls. Observations show response times on the calls can be pretty variable.
# This copy needs to be done in one shot and complete. Hence the conservative value.
TIMEOUT = 30

# Description text used with argparse
DESCRIPTION = 'This script will take an epic and prototypical issue and create a series of child issues under the epic. The resulting epic will have child issues one for each label starting with "squad:". Each child issue will have the same labels as the prototypical issue plus a squad label. The prototypical issue will be deleted.\n\nInput is two command line parameters. One is for the URL of the target epic in Github. The other is the Zenhub numerical id for the Github repo. You can get this from the URL of the Zenhub board of a Github Repo.\n\nRunning this script requires an access token for Github and an access Token for Zenhub. These get passed respectively in environment variables "GHE_ACCESS_TOKEN" and "ZENHUB_ACCESS_TOKEN". You can find information on getting the tokens at https://developer.github.com/v3/ and https://zenhub.ibm.com/app/dashboard/tokens. Note, due to implementation shortcuts, this only works for github.ibm.com.'

# This is the prefix that identifies the labels that identify the squads. It is used to create a list of labels.
# An issue is created for each label and tagged with that label and added to the original epic issue.
SQUAD_PREFIX = 'Squad:'

# Handle script parameters
parser = argparse.ArgumentParser(
    description=DESCRIPTION)
parser.add_argument(
    '-e', '--epic', type=str, help='URL of epic', required=True)
parser.add_argument(
    '-z', '--zenhub_repo', type=str, help='Zenhub numeric repo id for the Github repo', required=True)
parser.add_argument(
    '-s', '--squads', type=str, help='List of squad labels. When this parameter is specified, an issue is created and labeled with each of the labels in this list. Of the form \"[\\\"squad: foo\\\", \\\"mod squad\\\", \\\"bar\\\"]')
args = parser.parse_args()
epic_url = args.epic
zenhub_id = args.zenhub_repo
squads = args.squads

# Tokens for API access. See the Github and Zenhub API doc for how to create access tokens.
ghe_token = os.getenv('GHE_ACCESS_TOKEN')
if ghe_token is None:
    raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
ghe_headers = {"Authorization": "token %s" % ghe_token, "Accept": "application/vnd.github.v3+json"}

zenhub_token = os.getenv('ZENHUB_ACCESS_TOKEN')
if zenhub_token is None:
    raise Exception('ZENHUB_ACCESS_TOKEN environment variable not defined.')
zenhub_headers = {"X-Authentication-Token": "%s" % zenhub_token, "Content-Type": "application/json"}

"""
Method to retrieve all the labels for this repo that start with "Squad:".
"""

def get_squad_labels(labels_url):

    all_labels = ghe.makeCall(
        labels_url, ghe_headers, {})
    squad_labels = []
    for label in all_labels:
        if SQUAD_PREFIX.lower() in label['name'].lower():
            squad_labels.append(label['name'])
    return squad_labels

"""
Main method
"""


def main():
    try:
        # This suppresses the following warning:
        # 'InsecureRequestWarning: Unverified HTTPS request is being made.
        # Adding certificate verification is strongly advised'
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        regex = '(https:\/\/github\.com)\/(\S+)\/(\S+)\/issues\/(\d+)'
        match = re.findall(regex, epic_url)
        if len(match) != 1 or len(match[0]) != 4:
            raise Exception('Error parsing epic url %s.' % epic_url)
        else:
            github_url = match[0][0]
            github_org = match[0][1]
            github_repo = match[0][2]
            github_epic = match[0][3]

        # Get epic issue from Github
        epic_api_url = '%s/api/v3/repos/%s/%s/issues/%s' % (github_url, github_org, github_repo, github_epic)
        response = requests.get(epic_api_url, headers=ghe_headers, verify=False, timeout=TIMEOUT)
        if response.status_code != 200:
            raise Exception('Error retrieving epic %s.' % epic_url)
        epic_issue = response.json()

        # Get Zenhub epic issue information
        zenhub_epic_url = 'https://zenhub.innovate.com/p1/repositories/%s/epics/%s' % \
                          (zenhub_id, github_epic)
        response = requests.get(zenhub_epic_url, headers=zenhub_headers, verify=False, timeout=TIMEOUT)
        if response.status_code != 200:
            raise Exception('Error retrieving Zenhub epic %s.' % github_epic)
        zenhub_epic = response.json()

        # Now get prototypical issue from the Zenhub epic information. This is the issue we'll be
        # replicating, one for each of the squad labels. Raise an exception if there are no issues.
        # Otherwise take the first one as the prototype.
        if len(zenhub_epic['issues']) == 0:
            raise Exception('Zenhub epic must have at least one issue.')
        zenhub_prototypical_issue = zenhub_epic['issues'][0]

        # Get squad labels from the Github repo
        labels_url = '%s/api/v3/repos/%s/%s/labels' % (github_url, github_org, github_repo)
        squad_labels = get_squad_labels(labels_url)
        if squads is not None:
            labels_input = json.loads(squads)
            new_labels = []
            for label in labels_input:
                if label in squad_labels:
                    new_labels.append(label)
                else:
                    print('Label %s is not a defined label, ignoring' % label)
            squad_labels = new_labels
        print('Starting to create %s issues.' % len(squad_labels))

        # Get prototypical issue information
        prototypical_issue_url = '%s/api/v3/repos/%s/%s/issues/%s' % \
                     (github_url, github_org, github_repo, zenhub_prototypical_issue['issue_number'])
        response = requests.get(prototypical_issue_url, headers=ghe_headers,
                                verify=False, timeout=TIMEOUT)
        if response.status_code != 200:
            raise Exception('Error getting prototypical issue %s.' % zenhub_prototypical_issue['issue_number'])
        prototypical_issue = response.json()

        # Get labels from prototypical issue
        prototypical_issue_labels = prototypical_issue['labels']

        # Now we're creating the new epic child issues, one for each squad as represented in squad_labels
        new_labels_list = []
        new_epic_issues = []
        for label in prototypical_issue_labels:
            new_labels_list.append(label['name'])
        for squad_label in squad_labels:
            new_issue_labels = new_labels_list + [squad_label]
            new_issue_payload = dict(title='[%s]: %s' % (squad_label, prototypical_issue['title']),
                                    body=prototypical_issue['body'],
                                    labels=new_issue_labels)
            response = requests.post('%s/api/v3/repos/%s/%s/issues' % (github_url, github_org, github_repo),
                                     headers=ghe_headers,
                                     data=json.dumps(new_issue_payload), verify=False, timeout=TIMEOUT)
            if response.status_code != 201:
                raise Exception('Error creating epic child issue for %s.' % squad_label['name'])
            new_issue = response.json()
            new_epic_issues.append(new_issue['number'])

        # Now add the new issues to the Zenhub epic. But first wait a bit for Zenhub to catch up
        issues_to_add_to_epic = []
        for issue_id in new_epic_issues:
            issues_to_add_to_epic.append(dict(repo_id=int(zenhub_id), issue_number=issue_id))
        issues_to_update_payload = dict(add_issues=issues_to_add_to_epic)
        zenhub_issue_update_url = 'https://zenhub.innovate.com/p1/repositories/%s/epics/%s/update_issues' % \
                          (zenhub_id, github_epic)
        results = zh.make_request(zenhub_issue_update_url, zenhub_headers,
                                  params=json.dumps(issues_to_update_payload), method='POST')
        print('Created %s issues under epic %s.' % (len(results['added_issues']), github_epic))

        # Close prototypical issue
        response = requests.patch(prototypical_issue_url, headers=ghe_headers,
                                 data=json.dumps(dict(state='closed')), verify=False, timeout=TIMEOUT)
        if response.status_code != 200:
            raise Exception('Error closing prototypical issue %s.' % zenhub_prototypical_issue['number'])

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
