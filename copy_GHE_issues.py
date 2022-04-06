"""
Created on Dec 5, 2017

Copies issues from one GitHub repo to another, including ZenHub info. You'll need a personal access token from GitHub,
see https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/. You'll also need an access
token from Zenhub. For Zenhub access, API is beta, see https://zenhub.innovate.ibm.com/setup/howto/api. Add these as
environment variables GHE_ACCESS_TOKEN and ZENHUB_ACCESS_TOKEN.

This uses a verify=False on the requests library call, which generates warning messages. To suppress the warning
messages set environment variable PYTHONWARNINGS to 'ignore'.

Be sure to set the correct values for the GitHub and Zenhub server domain names and the source and target orgs
and repos below.

Github API: https://developer.github.com/v3/
Zenhub API: https://github.com/ZenHubIO/API

"""

import requests
import traceback
import handle_GHE_calls as ghe
import handle_zenhub_calls as zh
import os
import json
import datetime
import re

# Setting this variable to true prevents changes from being made to the source repo. To wit, patching references
# issues that were copied to the target repo and closing the original issues in the source repo.
DEBUG = True

# Regex to find an issue reference in a description or a comment. Captures '#123' and 'https://.../issues/123'.
ISSUE_REGEX = r'(\s#|\S+/issues/)(\d+)'

# Timeout value on the http REST calls. Obversations show response times on the calls can be pretty variable. This
# copy needs to be done in one shot and complete. Hence the conservative value.
timeout = 120

# Domain names of the github and zenhub servers
gh_server = 'github.myorg.com'
zh_server = 'zenhub.innovate.myorg.com'

# This is the org and repo from where issues will be copied. The repo_id is a Zenhub value. There is currently no API
# that will provide this. Get it by opening up the Zenhub board on a repo and examining the GITHUB_URL.

source_org = 'source_org'
source_repo = 'source_repo'
source_repo_id = 311656

# Info on where the issues will be copied to. Same comment on the repo_id.
#
target_org = 'target_org'
target_repo = 'target_repo'
target_repo_id = 311656


# Tokens for API access. See the Github and Zenhub API doc for how to create access tokens.
ghe_token = os.getenv('GHE_ACCESS_TOKEN')
if ghe_token is None:
    raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
ghe_headers = {"Authorization": "token %s" % ghe_token, "Accept": "application/vnd.github.v3+json"}

zenhub_token = os.getenv('ZENHUB_ACCESS_TOKEN')
if zenhub_token is None:
    raise Exception('ZENHUB_ACCESS_TOKEN environment variable not defined.')
zenhub_headers = {"X-Authentication-Token": "%s" % zenhub_token, "Content-Type": "application/json"}

gh_api_endpoint = 'https://%s/api/v3' % gh_server
zh_api_endpoint = 'https://%s' % zh_server

source_org_url = '%s/orgs/%s' % (gh_api_endpoint, source_org)
source_repo_url = '%s/repos/%s/%s' % (gh_api_endpoint, source_org, source_repo)
target_org_url = '%s/orgs/%s' % (gh_api_endpoint, target_org)
target_repo_url = '%s/repos/%s/%s' % (gh_api_endpoint, target_org, target_repo)

source_zh_epics_url = '%s/p1/repositories/%d/epics' % (zh_api_endpoint, source_repo_id)
target_zh_epics_url = '%s/p1/repositories/%d/epics' % (zh_api_endpoint, target_repo_id)
source_zh_issues_url = '%s/p1/repositories/%d/issues' % (zh_api_endpoint, source_repo_id)
target_zh_issues_url = '%s/p1/repositories/%d/issues' % (zh_api_endpoint, target_repo_id)
source_zh_board_url = '%s/p1/repositories/%d/board' % (zh_api_endpoint, source_repo_id)
target_zh_board_url = '%s/p1/repositories/%d/board' % (zh_api_endpoint, target_repo_id)

# This dictionary maps pipelines in the source repo to pipelines in the target repo, when the name the pipeline in the
# source repo differs from the name of the pipeline in the target repo. If the pipelines match by name, e.g.
# 'New Issues' in source and 'New Issues' in target, no entry is necessary. If an issue in the 'Dev' pipeline in the
# source repo should land in the 'Developoment' pipeline in the target repo, include an entry like this:
#
#   {'Dev': 'Development'}

# this is for blueyoda/blueyoda to watson-engagement-advisor/wea-backlog
pipeline_map_exceptions = {'In Review': 'Code Review',
                           'Deployed (Stage)': 'In Staging',
                           'Delivered (DEV)': 'Implemented'}

"""
Method for converting date/time string returned by GH API into something more readable
"""


def get_date(string):
    t = string.find('T')
    date_string = string[0:t]
    time_string = string[t + 1:len(string) - 1]
    date = datetime.datetime.strptime(date_string, '%Y-%m-%d')
    time = datetime.datetime.strptime(time_string, '%H:%M:%S')

    return date.strftime('%b %d')


"""
Read all the GHE Issues from the source repo.
"""


def read_issues(state):
    parameters = {'state': state, 'direction': 'asc', 'per_page': 50}
    issues = ghe.makeCall('%s/issues' % source_repo_url, ghe_headers, parameters,
                          print_status=True)
    issues_to_include = []

    for issue in issues:
        if should_we_include_this_issue(issue):
            issues_to_include.append(issue)
        else:
            print('Excluding issue %s.' % issue['html_url'])
    return issues_to_include


"""
Determines is an issue should be written to the new target repo. The current implementation is to write all issues, 
open and closed, except for those that have an 'Aha:' label or have a 'squad: cap' label only and not other 'squad:' label.
"""


def should_we_include_this_issue(issue):
    return True
    # found_aha_label = [element for element in issue['labels'] if element['name'].find('Aha') >= 0]
    # if len(found_aha_label) > 0:
    #     return False
    # else:
    #     found_cap_label = [element for element in issue['labels'] if 'quad: CAP' in element['name']]
    #     if len(found_cap_label) == 0:
    #         return True
    #     else:
    #         found_squad_labels = [element for element in issue['labels'] if 'quad:' in element['name']]
    #         if len(found_squad_labels) > 1:
    #             return True
    #         else:
    #             return False


"""
This method completes pipeline_map, a dictionary that maps a pipeline in the source repo (by name) to a pipeline in 
the target repo (by id). Pipelines match by name, except those included in pipeline_map_exceptions.
"""


def complete_pipeline_map():
    pipeline_map = {}
    source_board = zh.make_request(source_zh_board_url, zenhub_headers)
    target_board = zh.make_request(target_zh_board_url, zenhub_headers)
    for source_pipeline in source_board['pipelines']:
        target_pipeline = [target_pipeline for target_pipeline in target_board['pipelines'] if
                           target_pipeline['name'] == source_pipeline['name']]
        if len(target_pipeline) == 1:
            # we've found the target pipeline that matches source pipeline by name. Add the target pipeline id to the map
            pipeline_map[source_pipeline['name']] = target_pipeline[0]['id']
        else:
            # else, look for a match in the pipeline_exceptions, defined above
            target_pipeline_name = pipeline_map_exceptions.get(source_pipeline['name'])
            if target_pipeline_name is not None:
                # we've found a match, by name, in the pipeline_exceptions for the source pipeline. Now get its id and
                # put this in the map
                target_pipeline = [target_pipeline for target_pipeline in target_board['pipelines'] if
                                   target_pipeline['name'] == target_pipeline_name]
                if len(target_pipeline) == 1:
                    # we've found a match for the source pipeline in pipeline_exceptions, so add the target ipieline's id
                    # to the mape
                    pipeline_map[source_pipeline['name']] = target_pipeline[0]['id']
                else:
                    # there appears to be an error in the pipeline_exceptions map. The target pipeline name is not found
                    # as a pipeline in the target board
                    print(
                        'Error with pipeline_exceptions list. No pipeline \'%s\' found in %s. '
                        'Issues will be left in the \'New Issues\' pipeline.' % (
                            target_pipeline_name, target_repo_url))
            else:
                # no match by name to either target pipelines or entries in the pipeline exception dictionary.
                print('No pipeline %s found in %s. Issues will be left in the \'New Issues\' pipeline.' % (
                    source_pipeline['name'], target_repo_url))
    return pipeline_map


"""
Set up the target repo with labels and milestones from the source repo. In both cases, we're just matching names, not
attempting to match colors for labels and dates for milestones.
"""


def setup_target_repo():
    source_labels_url = '%s/labels' % source_repo_url
    source_labels = ghe.makeCall(
        source_labels_url, ghe_headers, {})
    target_labels_url = '%s/labels' % target_repo_url
    target_labels = ghe.makeCall(
        target_labels_url, ghe_headers, {})
    for source_label in source_labels:
        found_label = [element for element in target_labels if element['name'] == source_label['name']]
        if len(found_label) == 0:
            label_parameters = json.dumps(dict(name=source_label["name"], color=source_label["color"]))
            response = requests.post(target_labels_url, data=label_parameters, headers=ghe_headers, verify=False,
                                     timeout=timeout)
            if response.status_code <= 201:
                print('Added label %s.' % source_label['name'])
            else:
                print('Error adding label %s.' % source_label['name'])

    source_milestones_url = '%s/milestones' % source_repo_url
    source_milestones = ghe.makeCall(
        source_milestones_url, ghe_headers, {'state': 'all'})
    target_milestones_url = '%s/milestones' % target_repo_url
    target_milestones = ghe.makeCall(
        target_milestones_url, ghe_headers, {'state': 'all'})
    for source_milestone in source_milestones:
        found_milestone = [element for element in target_milestones if element['title'] == source_milestone['title']]
        if len(found_milestone) == 0:
            milestone_parameters = json.dumps(dict(title=source_milestone['title'],
                                                   description=source_milestone['description'],
                                                   due_on=source_milestone['due_on']))
            response = requests.post(target_milestones_url, data=milestone_parameters, headers=ghe_headers,
                                     verify=False,
                                     timeout=timeout)
            if response.status_code <= 201:
                print('Added milestone %s.' % source_milestone['title'])
            else:
                print('Error adding milestone %s.' % source_milestone['title'])


"""
Write the issues to the target repo. Keep track of the numbers of the new issues in issue_map so we can later associate
an issue in the source repo to the corresponding one in the target repo. This is done in two passes. The first writes 
issues and creates the map. The second pass is to patch up the #[issue] references. We need the map to know the issue
number in the target repo.
"""


def write_issues(issues):
    print('Starting to write %s issues to %s/%s.' % (len(issues), target_org, target_repo))
    target_milestones = ghe.makeCall('%s/milestones' % target_repo_url, ghe_headers, {})
    issue_map = {}
    for issue in issues:
        target_assignees = []
        for assignee in issue['assignees']:
            target_assignees.append(assignee['login'])
        target_labels = []
        for label in issue['labels']:
            target_labels.append(label['name'])
        if issue['milestone'] is None:
            issue_parameters = dict(title=issue['title'],
                                    body="_%s created the following on %s:_  \n\n %s \n\n_Original issue: %s_" % (
                                        issue['user']['login'], get_date(issue['created_at']), issue['body'],
                                        issue['html_url']),
                                    assignees=target_assignees,
                                    labels=target_labels)
        else:
            target_milestone = [milestone for milestone in target_milestones if
                                milestone['title'] == issue['milestone']['title']]
            if len(target_milestone) > 0:
                target_milestone_integer = target_milestone[0]['number']
                issue_parameters = dict(title=issue['title'],
                                        body="_%s created the following on %s:_  \n\n %s \n\n_Original issue: %s_" % (
                                            issue['user']['login'], get_date(issue['created_at']), issue['body'],
                                            issue['html_url']),
                                        assignees=target_assignees,
                                        labels=target_labels,
                                        milestone=target_milestone_integer)
            else:
                issue_parameters = dict(title=issue['title'],
                                        body="_%s created the following on %s:_  \n\n %s \n\n_Original issue: %s_" % (
                                            issue['user']['login'], get_date(issue['created_at']), issue['body'],
                                            issue['html_url']),
                                        assignees=target_assignees,
                                        labels=target_labels)
        response = requests.post('%s/issues' % target_repo_url, headers=ghe_headers,
                                 data=json.dumps(issue_parameters), verify=False, timeout=timeout)

        # 201 means a new issue was created.
        if response.status_code == 201:
            new_issue_results = response.json()
            issue_map[issue['number']] = new_issue_results['number']
            print('Copied %s as #%s.' % (issue['html_url'], new_issue_results['number']))

            # Look for dependencies. There's no API to add dependencies, so we're just going to print a message.
            # The dependencies have to be added by hand.
            results = zh.make_request(
                '%s/%s/events' % (source_zh_issues_url, issue['number']), zenhub_headers)
            if results is not None:
                dependency_events = [event for event in results if
                                     event['type'] == 'addBlocking' or event['type'] == 'addBlockedBy']
                if len(dependency_events) > 0:
                    print('Check for dependencies: %s.' % new_issue_results['html_url'])

            # Last step is to copy the comments from the source issue to the target issue.
            source_comments_url = issue['comments_url']
            target_comments_url = new_issue_results['comments_url']
            response = requests.get(source_comments_url, headers=ghe_headers, verify=False, timeout=timeout)
            if response.status_code != 200:
                print("Error getting comments for %s." % source_comments_url)
            else:
                results = response.json()
                for result in results:
                    comment = "_On %s, %s commented:_\n%s" % (
                        get_date(result['created_at']), result['user']['login'], result['body'])
                    response = requests.post(target_comments_url, headers=ghe_headers,
                                             data=json.dumps({'body': comment}), verify=False, timeout=timeout)
                    if response.status_code > 201:
                        print("Error writing comment to %s." % issue['html_url'])

        else:
            results = response.json()
            print('Error copying %s.' % issue['html_url'])
            print(json.dumps(results, indent=4))

    print('Finished copying %s issue(s).' % len(issues))

    return issue_map


"""
Patch issues referenced in the target repo of the form #[issue].  If the issue was copied, we insert 
a url in the new repo. If it was not, we use the url to the issue in the source repo. GitHub does a nic e job of 
properly representing the reference in the issue text.
"""


def patch_target_issues(issue_map):
    print('\nNow patching up issue in target repo.')
    target_gh_issues_url = 'https://github.ibm.com/%s/%s/issues' % (target_org, target_repo)
    source_gh_issues_url = 'https://github.ibm.com/%s/%s/issues' % (source_org, source_repo)
    for key in issue_map.keys():
        response = requests.get('%s/issues/%s' % (target_repo_url, issue_map[key]), headers=ghe_headers, verify=False,
                                timeout=timeout)
        if response.status_code != 200:
            print('Error retrieving target issue %s.' % issue_map[key])
        else:
            issue = response.json()
            patched = False
            # look for references first in the issue description
            matches = re.findall(ISSUE_REGEX, issue['body'])
            if len(matches) > 0:
                new_body = issue['body']
                for match in matches:
                    # If this was a reference to an issue in the source repo, we need to update the reference, otherwise
                    # leave it as it.
                    if match[0].strip() == '#' or match[0].find(source_repo) >= 0:
                        # If the match is a reference to this issue, leave it. Bit of a hack but it means it's likely
                        # from the line we're adding to the description to point back to the original issue.
                        if int(match[1]) != key:
                            target_issue_number = issue_map.get(int(match[1]))
                            if target_issue_number is not None:
                                # The issue in this reference is one we copied, so use the new mappes issue number.
                                # Otherwise, is a reference to an issue that we excluded. We need to write out the
                                # entire reference in case in the source repo it was just refefences as e.g. #123
                                new_url_ref = ' %s/%s' % (target_gh_issues_url, target_issue_number)
                            else:
                                new_url_ref = ' %s/%s' % (source_gh_issues_url, match[1])
                            new_body = new_body.replace('%s%s' % (match[0], match[1]), new_url_ref)
                params = {"body": new_body}
                response = requests.patch(issue['url'], headers=ghe_headers,
                                          data=json.dumps(params), verify=False, timeout=timeout)
                if response.status_code != 200:
                    print("Error patching url reference in %s." % issue['html_url'])
                else:
                    patched = True

        # Now look through all the comments
        target_comments_url = issue['comments_url']
        response = requests.get(target_comments_url, headers=ghe_headers, verify=False, timeout=timeout)
        if response.status_code != 200:
            print("Error getting comments for %s." % target_comments_url)
        else:
            results = response.json()
            for result in results:
                matches = re.findall(ISSUE_REGEX, result['body'])
                if len(matches) > 0:
                    new_comment = result['body']
                    for match in matches:
                        # If this was a reference to an issue in the source repo, we need to update the reference, otherwise
                        # leave it as it.
                        if match[0].strip() == '#' or match[0].find(source_repo) >= 0:
                            target_issue_number = issue_map.get(int(match[1]))
                            if target_issue_number is not None:
                                # The issue in this reference is one we copied, so use the new mappes issue number.
                                # Otherwise, is a reference to an issue that we excluded. We need to write out the
                                # entire reference in case in the source repo it was just refefences as e.g. #123
                                new_url_ref = ' %s/%s' % (target_gh_issues_url, target_issue_number)
                            else:
                                new_url_ref = ' %s/%s' % (source_gh_issues_url, match[1])
                            new_comment = new_comment.replace('%s%s' % (match[0], match[1]), new_url_ref)
                    params = {"body": new_comment}
                    response = requests.patch(result['url'], headers=ghe_headers,
                                              data=json.dumps(params), verify=False, timeout=timeout)
                    if response.status_code != 200:
                        print("Error patching url reference in %s." % issue['html_url'])
                    else:
                        patched = True
        if patched:
            print('Patched issue reference(s) in %s.' % issue['html_url'])


"""
Patch issues referenced in the target repo of the form #[issue].  If the issue was copied, we insert 
a url in the new repo. If it was not, we use the url to the issue in the source repo. GitHub does a nice job of 
properly representing the reference in the issue text.
"""


def patch_source_issues(issue_map):
    print('\nNow patching up issue references in source repo.')
    target_gh_issues_url = 'https://github.ibm.com/%s/%s/issues' % (target_org, target_repo)
    parameters = {'state': 'all', 'direction': 'asc', 'per_page': 50}
    issues = ghe.makeCall('%s/issues' % source_repo_url, ghe_headers, parameters,
                          print_status=True)
    for issue in issues:
        patched = False
        # look for references first in the issue description
        matches = re.findall(ISSUE_REGEX, issue['body'])
        if len(matches) > 0:
            new_body = issue['body']
            for match in matches:
                # If this was a reference to an issue in the source repo, we need to update the reference, otherwise
                # leave it as it.
                if match[0].strip() == '#' or match[0].find(source_repo) >= 0:
                    target_issue_number = issue_map.get(int(match[1]))
                    if target_issue_number is not None:
                        # OK the issue in this reference is one we copied.
                        new_url_ref = ' %s/%s' % (target_gh_issues_url, target_issue_number)
                        new_body = new_body.replace('%s%s' % (match[0], match[1]), new_url_ref)
                        params = {"body": new_body}
                        response = requests.patch(issue['url'], headers=ghe_headers,
                                                  data=json.dumps(params), verify=False, timeout=timeout)
                        if response.status_code != 200:
                            print("Error patching url reference in %s." % issue['html_url'])
                        else:
                            patched = True

        # Now look through all the comments
        source_comments_url = issue['comments_url']
        response = requests.get(source_comments_url, headers=ghe_headers, verify=False, timeout=timeout)
        if response.status_code != 200:
            print("Error getting comments for %s." % source_comments_url)
        else:
            results = response.json()
            for result in results:
                matches = re.findall(ISSUE_REGEX, result['body'])
                if len(matches) > 0:
                    new_comment = result['body']
                    for match in matches:
                        # If this was a reference to an issue in the source repo, we need to update the reference, otherwise
                        # leave it as it.
                        if match[0].strip() == '#' or match[0].find(source_repo) >= 0:
                            target_issue_number = issue_map.get(int(match[1]))
                            if target_issue_number is not None:
                                # OK the issue in this reference is one we copied.
                                new_url_ref = ' %s/%s' % (target_gh_issues_url, target_issue_number)
                                new_comment = new_comment.replace('%s%s' % (match[0], match[1]), new_url_ref)
                                params = {"body": new_comment}
                                response = requests.patch(result['url'], headers=ghe_headers,
                                                          data=json.dumps(params), verify=False, timeout=timeout)
                                if response.status_code != 200:
                                    print("Error patching url reference in %s." % issue['html_url'])
                                else:
                                    patched = True
        if patched:
            print('Patched issue reference(s) in %s.' % issue['html_url'])
        print('Processed source issue %s.' % issue['html_url'])


"""
Add the issue estimates to the newly created issues
"""


def add_estimates(source_issues, issue_map):
    print('\nNow defining the estimates.')
    # first go through all source_issues and add zenhub estimates
    for source_issue in source_issues:
        source_issue_info = zh.make_request('%s/%d' % (source_zh_issues_url, source_issue['number']), zenhub_headers)
        if source_issue_info is not None:
            source_estimate = source_issue_info.get('estimate', None)
            if source_estimate is not None:
                results = zh.make_request(
                    '%s/%s/estimate' % (target_zh_issues_url, issue_map[source_issue['number']]),
                    zenhub_headers, params=json.dumps({'estimate': source_estimate['value']}), method='PUT')
                if results is None:
                    print('Error setting estimate for %s in target repo.' % source_issue['html_url'])
                else:
                    print('Setting estimate for %s.' % issue_map.get(source_issue['number']))


"""
Assign new issues in the target repo to pipelines
"""


def assign_issues_to_pipelines(issue_map, pipeline_map):
    print('\nNow, assigning issues to the correct pipeline.')
    source_board = zh.make_request(source_zh_board_url, zenhub_headers)
    if source_board is not None:
        source_pipelines = source_board.get('pipelines', None)
        if source_pipelines is not None:
            for source_pipeline in source_pipelines:
                # skip the 'new issues' pipeline because the issues we created in the target repo are already there
                if source_pipeline['name'] != 'New Issues':
                    for source_issue in source_pipeline['issues']:
                        # check to see if this is an issue we want to include
                        if issue_map.get(source_issue['issue_number']) is not None:
                            target_pipeline = pipeline_map.get(source_pipeline['name'])
                            if target_pipeline is not None:
                                # If target_pipeline is None, it means we don't have a pipeline in the target repo that
                                # matches the source repo, so do nothing which leaves the issue in New issues
                                params = {"pipeline_id": target_pipeline, "position": "bottom"}
                                results = zh.make_request(
                                    '%s/%d/moves' % (target_zh_issues_url, issue_map[source_issue['issue_number']]),
                                    zenhub_headers, params=json.dumps(params), method='POST')
                                print('Assinging pipeline for %s.' % issue_map.get(source_issue['issue_number']))


"""
Define epics in the target repo. First, add estimates to issues that have them. Next, create the epics in the target
repo and add the target issues to them. Finally, Go through all the issues in the source ZenHub board and assign them
to the corresponding pipeline in the target repo.
"""


def define_epics(issue_map):
    print('\nNow, defining epics.')
    source_epics = zh.make_request(source_zh_epics_url, zenhub_headers)['epic_issues']
    for source_epic in source_epics:
        # Need to determine if the epic correcponds to an issue we are choosing not to include. We do this by
        # checking to see if the epic issue number is inclucded in issue_map, meaning we chose to include it.
        if issue_map.get(source_epic['issue_number']) is not None:
            source_epic_info = zh.make_request('%s/%d' % (source_zh_epics_url, source_epic['issue_number']),
                                               zenhub_headers)
            target_epic_issues = []
            request_data = []
            target_epic_issues_not_included = []
            for source_issue in source_epic_info['issues']:
                target_issue_number = issue_map.get(source_issue['issue_number'])
                if target_issue_number is not None:
                    target_epic_issues.append(target_issue_number)
                    request_data.append({"repo_id": target_repo_id, "issue_number": target_issue_number})
                else:
                    target_epic_issues_not_included.append(source_issue['issue_number'])

            results = zh.make_request(
                '%s/%d/convert_to_epic' % (target_zh_issues_url, issue_map[source_epic['issue_number']]),
                zenhub_headers, params=json.dumps({'issues': request_data}), method='POST')
            if results is None:
                print('Error creating epic %s in target repo.' % issue_map[source_epic['issue_number']])
                print('%s issues that should be included: %s' % (target_repo, target_epic_issues))
                print('%s issues that were not copied to %s: %s' % (
                    source_repo, target_repo, target_epic_issues_not_included))
            else:
                print('Created epic %s with issues %s.' % (issue_map[source_epic['issue_number']], target_epic_issues))
                if len(target_epic_issues_not_included) > 0:
                    print('The following issues were not copied from %s and cannot be added to epic %s: %s' % (
                        source_repo, issue_map[source_epic['issue_number']], str(target_epic_issues_not_included)))


"""
Clean up after writing issues: If an issue or milestone in the source repo was closed, close it now in the target
repo. We have to do this last because the issues have to be open to modify them through the API. Same thing for
milestones.
"""


def close_target_issues(issues, issue_map):
    print('\nClosing issues and milestones in %s/%s that were closed in %s/%s and issues that were copied.' % (
        target_org, target_repo, source_org, source_repo))
    source_milestones_url = '%s/milestones' % source_repo_url
    target_milestones_url = '%s/milestones' % target_repo_url
    source_milestones = ghe.makeCall(source_milestones_url, ghe_headers, {'state': 'all'})
    target_milestones = ghe.makeCall(target_milestones_url, ghe_headers, {'state': 'all'})

    # if source milestone is closed, close corresponding new milestone. The milestone has to be open to add issues to it
    print('\nClosing miletsones.')
    for source_milestone in source_milestones:
        found_milestone = [element for element in target_milestones if element['title'] == source_milestone['title']]
        if len(found_milestone) != 1:
            print('Error: %s instances found for milestone %s.' % (len(found_milestone), source_milestone['title']))
        else:
            if source_milestone['state'] == 'closed':
                response = requests.patch(found_milestone[0]['url'], headers=ghe_headers,
                                          data=json.dumps({'state': 'closed'}), verify=False, timeout=timeout)
                if response.status_code != 200:
                    print('Error closing milestone %s.' % found_milestone[0]['title'])

    # Now close issues
    for issue in issues:
        # if the source issue is closed, close the new target issue
        if issue['state'] == 'closed':
            response = requests.patch('%s/issues/%s' % (target_repo_url, issue_map[issue['number']]),
                                      headers=ghe_headers,
                                      data=json.dumps({'state': 'closed'}), verify=False, timeout=timeout)
            if response.status_code != 200:
                print('Error closing new issue %s.' % issue_map[issue['number']])
            else:
                print('Closed issue %s.' % issue_map[issue['number']])

"""
If we copied an issue, close it in the source repo
"""


def close_source_issues(issues, issue_map):
    print('\nClosing issues and milestones in %s/%s that were closed in %s/%s and issues that were copied.' % (
        target_org, target_repo, source_org, source_repo))

    for issue in issues:
        # if the issue was copied, close it in the source repo
        target_issue_number = issue_map.get(issue['number'])
        if target_issue_number is not None:
            target_issue_url = 'https://%s/%s/%s/issues/%s' % (
                gh_server, target_org, target_repo, target_issue_number)
            source_issue_url = 'https://%s/%s/%s/issues/%s' % (
                gh_server, source_org, source_repo, issue['number'])
            comment = 'This issue was moved to %s.' % target_issue_url
            response = requests.post('%s/issues/%s/comments' % (source_repo_url, issue['number']),
                                     headers=ghe_headers,
                                     data=json.dumps({'body': comment}), verify=False, timeout=timeout)
            if response.status_code != 201:
                print('Error commenting on %s.' % source_issue_url)
            response = requests.patch('%s/issues/%s' % (source_repo_url, issue['number']),
                                      headers=ghe_headers,
                                      data=json.dumps({'state': 'closed'}), verify=False, timeout=timeout)
            if response.status_code != 200:
                print('Error closing source issue %s.' % issue['number'])
            else:
                print('Closed source issue %s.' % issue['number'])


"""
Main method
"""


def main():
    try:
        # Issue map is a dictionary that maps an issue number in the source repo to it's corresponding issue in
        # the target repo
        issue_map = []
        issues = []
        #
        # read the open issues from the source repo
        issues = read_issues('open')

        # add to the target repo the labels and milestones from the source repo
        setup_target_repo()

        # complete pipeline_map dictionary to map between pipelines ids in the source and target repos
        pipeline_map = complete_pipeline_map()

        # now write the issues to the target repo, minus the ZenHub info. Return a dictionaru mapping the issue numbers
        # in the source repo to the corresponding issues numbers in the target repo
        issue_map = write_issues(issues)

        # patch up the issue references #[issue] in the target repo, both in description and comment fields
        patch_target_issues(issue_map)

        # Add the issue estimates
        add_estimates(issues, issue_map)

        # Put the new issues in the correct pipelines in the target repo
        assign_issues_to_pipelines(issue_map, pipeline_map)

        # now add the epic info, including estimates and pipeline.
        define_epics(issue_map)

        # Close the new issues in the target repo if the issue in the source repo is closed. Same thing
        # for milestones.
        close_target_issues(issues, issue_map)

        # patch up the issue references #[issue] in the target repo, both in description and comment fields
        if DEBUG is False:
            patch_source_issues(issue_map)

        # Close the issues in the source repo that were copied to the target repo
        if DEBUG is False:
            close_source_issues(issues, issue_map)

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()
    finally:
        # We need to know this in case the script fails. This way we know which issues we copied and what their corresponding
        # issue numbers are in the target repo./
        print('Issue map of issues written:')
        print(issue_map)


if __name__ == '__main__':
    main()
