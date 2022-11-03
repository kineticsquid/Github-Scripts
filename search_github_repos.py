"""
Created on May 7, 2019

Routine to scan all of the repos and all of the files in an org looking for regex matches. This includes
a repo's wiki if one exists. Because the Github API does not provide access to the wiki repo, to scan it,
we first clone it locally and then scan it.

Output is a series of files, one per repo, with matches highlighted. Only files and wiki pages with
matches are include in the output html files.

Requires a personal access token generated from GHE settings be defined
to environment variable GHE_ACCESS_TOKEN in .bashrc and/or .profile.
Looks like .profile is required for interactive terminal window.

Execution notes...
- Ignore errors like, `fatal: remote error: access denied or repository not exported: /c/nw/c2/ba/1b/2255/2968.wiki.git`. This happens when attempting to clone a wiki repo and
one doesn't exist. There doesn't seem to be a reliable way to determine if a repo has a wiki,
- Ignore errors like, `403: This API returns blobs up to 1 MB in size. The requested blob is too large to fetch via the API, but you can use the Git Data API to request blobs up to 100 MB in size.`. These files are binary files and not likely to present a security exposure of revealing secrets in clear text.

To use:

    python3 search_GHE_repos.py
      --server {domain name of server - default is github.ibm}
      --org {org to scan - default is watson-engagement-advisor}
      --repo {repo - scan this only and not all repos in the org}
      --regex {regex to search for}
      --start {start with this repo, skipping the ones before it. For restarts}
      --dir {director for output. Also will contain the clones of the wiki repos}
"""

import argparse
import traceback
import os
import handle_GH_paging
import base64
import re
import shutil

PAGE_SIZE = 100
MAX_RETRIES = 10
TIMEOUT = 60
HTML_TOP = '<!DOCTYPE html>\n<html lang="en">\n<head>\n\t<meta charset="UTF-8">\n\t<title>%s</title>\n</head>\n<body>\n<h1><a href="%s">%s</a></h1>\n'
HTML_BOTTOM = '</body>\n</html>'
BEGIN_FILE = '<h2>%s</h2>\n<pre>\n'
END_FILE = '</pre>\n'
BEGIN_MARK = '<b><font color="red">'
END_MARK = '</font></b>'
WIKI_DIR = 'wikis'

"""
Get and validate command line args
"""


def get_args():
    parser = argparse.ArgumentParser(
        description='Scans all files in all repos in an org for a regex.')
    # Add arguments
    parser.add_argument(
        '-s', '--server', type=str, help='API entry point for Github server, default is api.github.com.', default='api.github.com')
    parser.add_argument(
        '-o', '--org', type=str, help='GitHub organization name.', required=True)
    parser.add_argument(
        '-r', '--repo', type=str, help='Repo in the org to scan. Only this repo will be scanned.')
    parser.add_argument(
        '-x', '--regex', type=str, help='Regex to search for.', required=True)
    parser.add_argument(
        '--start', type=str, help='Name of repo to start with.')
    parser.add_argument(
        '-d', '--directory', type=str, help='Output directory for HTML output files, default is \'output\'.', default='output')
    args = parser.parse_args()
    return args.server, args.org, args.repo, args.regex, args.start, args.directory


"""
Process the contents of a repo recursively to deal with folders
"""


def process_repo_element(repo, element, headers, regex):
    html_results = ''
    try:
        repo_element_contents = handle_GH_paging.makeCall(element['url'], headers, None,
                                                          maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
        # if the type of the returned results is not a dict (it's an array)
        # it means this is a folder, so recursively process entries
        if element.get('type') != 'file':
            if element['name'] == 'site':
                debug = True  # here for debugging only
            for item in repo_element_contents:
                html_results = html_results + process_repo_element(repo, item, headers, regex)
        # else it is a dict meaning this is an entry for a single file
        else:
            try:
                # need to decode the content first to get text
                file_contents = base64.b64decode(repo_element_contents['content']).decode('utf-8')
                file_link = '<a href="%s">%s</a>' % (repo_element_contents['html_url'], repo_element_contents['path'])
                html_results = process_file(file_contents, regex)
                if len(html_results) > 0:
                    html_results = '\n' + BEGIN_FILE % file_link + html_results + END_FILE

            except UnicodeDecodeError:
                # Decode error means it's most likely a binary blob of some sort, so ignore
                pass

    except Exception as e:
        print(str(e))

    return html_results

"""
Process File content. Returns an html string of results
"""


def process_file(file_contents, regex):
    # string containing HTML results
    html_results = ''
    # Process the file text line by line
    current_position = 0
    done = False
    while not done:
        next_new_line = file_contents.find('\n', current_position)
        if next_new_line > 0:
            # this is the next line of text
            next_line = file_contents[current_position:next_new_line + 1]
            current_position = next_new_line + 1
        elif current_position < len(file_contents):
            # this is the last line of text and it doesn't end with \n
            next_line = file_contents[current_position:len(file_contents)]
            current_position = len(file_contents)
        else:
            break

        # This keeps track of the next character I need to write from the source file.
        next_char_to_copy = 0
        matches = regex.finditer(next_line)
        for match in matches:
            start = match.start()
            end = match.end()
            # Write from the source file up to the matching text
            html_results += next_line[next_char_to_copy:start]
            # Insert the HTML that marks the matching text
            html_results += BEGIN_MARK
            # The matching text
            html_results += next_line[start:end]
            # Close off the HTML that marks the matching text
            html_results += END_MARK
            # Update the next character to copy
            next_char_to_copy = end

        # copy the rest of the line only if we found a match, otherwise we'll skip it
        if next_char_to_copy > 0:
            html_results += next_line[next_char_to_copy:len(next_line)]

    return html_results


"""
This routine processes the branches in a repo other than master
"""


def process_branches(repo, headers, regex):
    html_results = ''
    branches = handle_GH_paging.makeCall(repo['url'] + '/branches', headers, None,
                                         maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
    for branch in branches:
        if branch['name'] != 'master':
            branch_contents = handle_GH_paging.makeCall(branch['commit']['url'],
                                                        headers, None, maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
            for file in branch_contents['files']:
                if file['status'] != 'removed':
                    file_contents = handle_GH_paging.makeCall(file['contents_url'],
                                                              headers, None, maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
                    try:
                        # need to decode the content first to get text
                        file_contents = base64.b64decode(file['content']).decode('utf-8')
                        file_link = '<a href="%s">%s</a>' % (file['html_url'], file['path'])
                        html_results = process_file(file_contents, regex)
                        if len(html_results) > 0:
                            html_results = '\n' + BEGIN_FILE % file_link + html_results + END_FILE

                    except UnicodeDecodeError:
                        # Decode error means it's most likely a binary blob of some sort, so ignore
                        pass

                    # Now process like a source code file
                    file_html_results = process_file(file_contents, regex)
                    if len(file_html_results) > 0:
                        file_link = '<a href="%s/%s">wiki/%s</a>' % (file['url'], file['path'], file['path'])
                        html_results = html_results + '\n' + BEGIN_FILE % file_link + file_html_results + END_FILE
    return html_results


"""
This routine processes the wikis cloned from the repos containing them. We've having to clone them because 
the GitHub does not provide a way to directly access content like other source code.
"""


def process_wiki(wiki_clone, wiki_url, regex):
    html_results = ''
    for wiki_page in os.listdir(wiki_clone):
        wiki_page_path = "%s/%s" % (wiki_clone, wiki_page)
        # Skip the GitHub meta data and any directories, e.g. to contain img
        if wiki_page != '.git' and os.path.isfile(wiki_page_path):
            # Read in the file contents.
            f = open(wiki_page_path, "r")
            page_contents = ''
            for line in f:
                page_contents = page_contents + line
            f.close()

            # Now process like a source code file
            page_html_results = process_file(page_contents, regex)
            if len(page_html_results) > 0:
                page_name = wiki_page.replace('.md', '')
                wiki_page_link = '<a href="%s/%s">wiki/%s</a>' % (wiki_url, page_name, page_name)
                html_results = html_results + '\n' + BEGIN_FILE % wiki_page_link + page_html_results + END_FILE
    return html_results


"""
Main method
"""


def main():
    try:
        server, org, repo, r, start_repo, output_directory = get_args()
        regex = re.compile(r, re.IGNORECASE)
        gh_token = os.getenv('GH_ACCESS_TOKEN')
        if gh_token is None:
            raise Exception('GH_ACCESS_TOKEN environment variable not defined.')
        # Get all the repos for the org
        headers = dict(Authorization='token %s' % gh_token)
        parameters = dict(per_page='%s' % PAGE_SIZE)
        if repo is None:
            repos_url = 'https://%s/orgs/%s/repos' % (server, org)
            repos = handle_GH_paging.makeCall(repos_url, headers, parameters, print_status=True,
                                              maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
        else:
            repo_url = 'https://%s/repos/%s/%s' % (server, org, repo)
            repo = handle_GH_paging.makeCall(repo_url, headers, parameters, print_status=True,
                                             maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
            repos = [repo]

        # If the directory exists, remove all previous clones to get the latest
        clone_dir = "%s/%s" % (output_directory, WIKI_DIR)
        if os.path.isdir(clone_dir) is True:
            shutil.rmtree(clone_dir)
        count = 1
        # Indicates when to start scanning repos.
        if start_repo is not None:
            start_scanning = False
        else:
            start_scanning = True
        for repo in repos:
            if start_scanning is False:
                if repo['name'] != start_repo:
                    print('Skipping %s of %s: %s' % (count, len(repos), repo['full_name']))
                else:
                    start_scanning = True
            if start_scanning is True:
                print('Processing %s of %s: %s' % (count, len(repos), repo['full_name']))
                try:
                    repo_contents = handle_GH_paging.makeCall(repo['url'] + '/contents', headers, None,
                                                              maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
                    html_results = ''
                    for element in repo_contents:
                        html_results += html_results + process_repo_element(repo, element, headers, regex)

                    # Now process branches other than master
                    # html_results += process_branches(repo, headers, regex)

                    # Now handle wiki if it exists. clone it to a temp location and scan it separately.
                    # This is a bit hacky because has_wiki is true sometimes when there is not a wiki.
                    # if repo['has_wiki'] is not None:
                    #     clone_target = "%s/%s" % (clone_dir, repo['name'])
                    #     os.system("git clone git@github.ibm.com:%s.wiki.git %s" % (repo['full_name'], clone_target))
                    #     # This clone may have failed, so we need to check to see if it exists
                    #     if os.path.isdir(clone_target) is True:
                    #         wiki_url = 'https://%s/%s/%s/wiki' % (server, org, repo['name'])
                    #         html_results += process_wiki(clone_target, wiki_url, regex)

                    output_file_name = "%s/%s.html" % (output_directory, repo['name'])
                    if len(html_results) > 0:
                        # Write new results, overwriting old results
                        output_file = open(output_file_name, "w")
                        output_file.write(HTML_TOP % (repo['full_name'], repo['html_url'], repo['full_name']))
                        output_file.write(html_results)
                        output_file.write(HTML_BOTTOM)
                        output_file.close()
                    else:
                        # Otherwise, if the file exists, it's from a previous run, so remove it
                        if os.path.isfile(output_file_name) is True:
                            os.remove(output_file_name)
                except Exception as e:
                    print('Error: ' + str(e))
            count += 1
    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
