"""
Created on Apr 8, 2022

This is an adaptation of copy_GHE_ZH_issues.py to deal only with moving the GH issue without having to deal with the
ZenHub data. Copies issues from one GitHub repo to another. This assumes you're copying from github.com. If not, set the 
value of the variable 'gh_server'.

I highly recommend warning all users who may be subscribed to issues in either repo. This will generate a ton of email
notifications. Simplest approach is to warn users, have them turn off notifications to these repos (or select web 
only notifications), run the script, then inform users to reset their notifications. 

By default, this script will copy all issues. If you want to filter the issues that get copied, define a filter in 
'should_we_include_this_issue(issue)'.

Requires the following environment variables:
GH_ACCESS_TOKEN - You'll need a personal access token from GitHub, see https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/. 
SOURCE_ORG - GitHub org that is the source of the issues to be copied
SOURCE_REPO - Github repo that is the source of the issues to be copied
TARGET_ORG - GitHub org to where the issues will be copied
TARGET_REPO - Github repo to where the issues will be copied

This uses a verify=False on the requests library call, which generates warning messages. To suppress the warning
messages set environment variable PYTHONWARNINGS to 'ignore'.

Github API: https://developer.github.com/v3/

"""

import requests
import traceback
import handle_GH_paging as gh
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

# Domain names of the github server
gh_server = 'github.com'

# This is the org and repo from where issues will be copied.

source_org = os.getenv('SOURCE_ORG')
source_repo = os.getenv('SOURCE_REPO')

# Info on where the issues will be copied to. 
#
target_org = os.getenv('TARGET_ORG')
target_repo = os.getenv('TARGET_REPO')


# Tokens for API access. See the Github API doc for how to create access tokens.
gh_token = os.getenv('GH_ACCESS_TOKEN')
gh_headers = {"Authorization": "token %s" % gh_token, "Accept": "application/vnd.github.v3+json"}

gh_api_endpoint = 'https://%s/api/v3' % gh_server

source_org_url = '%s/orgs/%s' % (gh_api_endpoint, source_org)
source_repo_url = '%s/repos/%s/%s' % (gh_api_endpoint, source_org, source_repo)
target_org_url = '%s/orgs/%s' % (gh_api_endpoint, target_org)
target_repo_url = '%s/repos/%s/%s' % (gh_api_endpoint, target_org, target_repo)

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
    issues = gh.makeCall('%s/issues' % source_repo_url, gh_headers, parameters,
                          print_status=True)
    issues_to_include = []

    for issue in issues:
        if should_we_include_this_issue(issue):
            issues_to_include.append(issue)
        else:
            print('Excluding issue %s.' % issue['html_url'])
    return issues_to_include


"""
Determines is an issue should be written to the new target repo. The implementation in the comment is to write all issues, 
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
Set up the target repo with labels and milestones from the source repo. In both cases, we're just matching names, not
attempting to match colors for labels and dates for milestones.
"""


def setup_target_repo():
    source_labels_url = '%s/labels' % source_repo_url
    source_labels = gh.makeCall(
        source_labels_url, gh_headers, {})
    target_labels_url = '%s/labels' % target_repo_url
    target_labels = gh.makeCall(
        target_labels_url, gh_headers, {})
    for source_label in source_labels:
        found_label = [element for element in target_labels if element['name'] == source_label['name']]
        if len(found_label) == 0:
            label_parameters = json.dumps(dict(name=source_label["name"], color=source_label["color"]))
            response = requests.post(target_labels_url, data=label_parameters, headers=gh_headers, verify=False,
                                     timeout=timeout)
            if response.status_code <= 201:
                print('Added label %s.' % source_label['name'])
            else:
                print('Error adding label %s.' % source_label['name'])

    source_milestones_url = '%s/milestones' % source_repo_url
    source_milestones = gh.makeCall(
        source_milestones_url, gh_headers, {'state': 'all'})
    target_milestones_url = '%s/milestones' % target_repo_url
    target_milestones = gh.makeCall(
        target_milestones_url, gh_headers, {'state': 'all'})
    for source_milestone in source_milestones:
        found_milestone = [element for element in target_milestones if element['title'] == source_milestone['title']]
        if len(found_milestone) == 0:
            milestone_parameters = json.dumps(dict(title=source_milestone['title'],
                                                   description=source_milestone['description'],
                                                   due_on=source_milestone['due_on']))
            response = requests.post(target_milestones_url, data=milestone_parameters, headers=gh_headers,
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
    target_milestones = gh.makeCall('%s/milestones' % target_repo_url, gh_headers, {})
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
        response = requests.post('%s/issues' % target_repo_url, headers=gh_headers,
                                 data=json.dumps(issue_parameters), verify=False, timeout=timeout)

        # 201 means a new issue was created.
        if response.status_code == 201:
            new_issue_results = response.json()
            issue_map[issue['number']] = new_issue_results['number']
            print('Copied %s as #%s.' % (issue['html_url'], new_issue_results['number']))

            # Last step is to copy the comments from the source issue to the target issue.
            source_comments_url = issue['comments_url']
            target_comments_url = new_issue_results['comments_url']
            response = requests.get(source_comments_url, headers=gh_headers, verify=False, timeout=timeout)
            if response.status_code != 200:
                print("Error getting comments for %s." % source_comments_url)
            else:
                results = response.json()
                for result in results:
                    comment = "_On %s, %s commented:_\n%s" % (
                        get_date(result['created_at']), result['user']['login'], result['body'])
                    response = requests.post(target_comments_url, headers=gh_headers,
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
        response = requests.get('%s/issues/%s' % (target_repo_url, issue_map[key]), headers=gh_headers, verify=False,
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
                response = requests.patch(issue['url'], headers=gh_headers,
                                          data=json.dumps(params), verify=False, timeout=timeout)
                if response.status_code != 200:
                    print("Error patching url reference in %s." % issue['html_url'])
                else:
                    patched = True

        # Now look through all the comments
        target_comments_url = issue['comments_url']
        response = requests.get(target_comments_url, headers=gh_headers, verify=False, timeout=timeout)
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
                    response = requests.patch(result['url'], headers=gh_headers,
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
    issues = gh.makeCall('%s/issues' % source_repo_url, gh_headers, parameters,
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
                        response = requests.patch(issue['url'], headers=gh_headers,
                                                  data=json.dumps(params), verify=False, timeout=timeout)
                        if response.status_code != 200:
                            print("Error patching url reference in %s." % issue['html_url'])
                        else:
                            patched = True

        # Now look through all the comments
        source_comments_url = issue['comments_url']
        response = requests.get(source_comments_url, headers=gh_headers, verify=False, timeout=timeout)
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
                                response = requests.patch(result['url'], headers=gh_headers,
                                                          data=json.dumps(params), verify=False, timeout=timeout)
                                if response.status_code != 200:
                                    print("Error patching url reference in %s." % issue['html_url'])
                                else:
                                    patched = True
        if patched:
            print('Patched issue reference(s) in %s.' % issue['html_url'])
        print('Processed source issue %s.' % issue['html_url'])


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
    source_milestones = gh.makeCall(source_milestones_url, gh_headers, {'state': 'all'})
    target_milestones = gh.makeCall(target_milestones_url, gh_headers, {'state': 'all'})

    # if source milestone is closed, close corresponding new milestone. The milestone has to be open to add issues to it
    print('\nClosing miletsones.')
    for source_milestone in source_milestones:
        found_milestone = [element for element in target_milestones if element['title'] == source_milestone['title']]
        if len(found_milestone) != 1:
            print('Error: %s instances found for milestone %s.' % (len(found_milestone), source_milestone['title']))
        else:
            if source_milestone['state'] == 'closed':
                response = requests.patch(found_milestone[0]['url'], headers=gh_headers,
                                          data=json.dumps({'state': 'closed'}), verify=False, timeout=timeout)
                if response.status_code != 200:
                    print('Error closing milestone %s.' % found_milestone[0]['title'])

    # Now close issues
    for issue in issues:
        # if the source issue is closed, close the new target issue
        if issue['state'] == 'closed':
            response = requests.patch('%s/issues/%s' % (target_repo_url, issue_map[issue['number']]),
                                      headers=gh_headers,
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
                                     headers=gh_headers,
                                     data=json.dumps({'body': comment}), verify=False, timeout=timeout)
            if response.status_code != 201:
                print('Error commenting on %s.' % source_issue_url)
            response = requests.patch('%s/issues/%s' % (source_repo_url, issue['number']),
                                      headers=gh_headers,
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

        # now write the issues to the target repo. Return a dictionaru mapping the issue numbers
        # in the source repo to the corresponding issues numbers in the target repo
        issue_map = write_issues(issues)

        # patch up the issue references #[issue] in the target repo, both in description and comment fields
        patch_target_issues(issue_map)

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
