"""
Created on May 7, 2019

Routine to scan all of the repos and all of the files in an org looking for regex matches. This is a quicker, but
not as thorough scan as search_GHE_repos.py as this one clones the repos and then greps on the local file system using
the regex pattern. It does not suffer as much from the GHE rate limiting.

Output is a series of files, one per repo, with matches highlighted. Only files and wiki pages with
matches are include in the output html files.

Requires a personal access token generated from GHE settings be defined
to environment variable GHE_ACCESS_TOKEN in .bashrc and/or .profile.
Looks like .profile is required for interactive terminal window.

Execution notes...
- Ignore errors like, `fatal: remote error: access denied or repository not exported: /c/nw/c2/ba/1b/2255/2968.wiki.git`.
This happens when attempting to clone a wiki repo and one doesn't exist. There doesn't seem to be a reliable way to
determine if a repo has a wiki,
- Ignore errors like, `403: This API returns blobs up to 1 MB in size. The requested blob is too large to fetch via the
API, but you can use the Git Data API to request blobs up to 100 MB in size.`. These files are binary files and not
likely to present a security exposure of revealing secrets in clear text.

To use:

    python3 search_GHE_repos.py
      --server {domain name of server - default is github.ibm.com}
      --org {org to scan - default is watson-engagement-advisor}
      --repo {repo - scan this only and not all repos in the org}
      --regex {regex to search for}
      --start {start with this repo, skipping the ones before it. For restarts}
      --dir {director for output. Also will contain the clones of the wiki repos}
"""

import argparse
import traceback
import os
from Github_Scripts import handle_GHE_calls
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

"""
Get and validate command line args
"""


def get_args():
    parser = argparse.ArgumentParser(
        description='Scans all files in all repos in an org for a regex.')
    # Add arguments
    parser.add_argument(
        '-s', '--server', type=str, help='GitHub Enterprise server name. ', required=True)
    parser.add_argument(
        '-o', '--org', type=str, help='GitHub Enterprise organization name. ', required=True)
    parser.add_argument(
        '-r', '--repo', type=str, help='Repo in the org to scan. Only this repo will be scanned.')
    parser.add_argument(
        '-x', '--regex', type=str, help='Regex to search for.', required=True)
    parser.add_argument(
        '--start', type=str, help='Name of repo to start with.')
    parser.add_argument(
        '-d', '--directory', type=str, help='Output directory for HTML output files.')
    parser.add_argument(
        '-w', '--wiki', type=bool, help='Whether or not to also search wiki if present.', default=False)
    args = parser.parse_args()
    return args.server, args.org, args.repo, args.regex, args.start, args.directory, args.wiki


"""
Process File content. Returns an html string of results
"""


def process_file(full_file_path, regex):
    # string containing HTML results
    html_results = ''
    try:
        # Read in the file contents.
        f = open(full_file_path, "r")
        page_contents = ''
        for line in f:
            page_contents = page_contents + line
        f.close()

        # Process the file text line by line
        current_position = 0
        done = False
        while not done:
            next_new_line = page_contents.find('\n', current_position)
            if next_new_line > 0:
                # this is the next line of text
                next_line = page_contents[current_position:next_new_line + 1]
                current_position = next_new_line + 1
            elif current_position < len(page_contents):
                # this is the last line of text and it doesn't end with \n
                next_line = page_contents[current_position:len(page_contents)]
                current_position = len(page_contents)
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
    except Exception as e:
        print('Error with %s: %s' % (full_file_path, str(e)))

    return html_results


"""
This routine processes the cloned repos.
"""


def process_repo(repo_clone, repo_url, repo_name, regex, output_directory):
    html_results = ''
    for entry in os.listdir(repo_clone):
        full_file_path = "%s/%s" % (repo_clone, entry)
        # Skip the GitHub meta data and any directories, e.g. to contain img
        if entry[0] != '.' and os.path.exists(full_file_path) is True:
            if os.path.isfile(full_file_path) is True:
                # Now process like a source code file
                file_results = process_file(full_file_path, regex)
                if len(file_results) > 0:
                    source_file_url = full_file_path.replace(output_directory + '/clones', repo_url)
                    source_file_url = repo_url + '/blob/master' + \
                                      full_file_path.replace(output_directory + '/clones/%s/' % repo_name, '/')
                    file_link = '<a href="%s">%s</a>' % (source_file_url, entry)
                    html_results = html_results + BEGIN_FILE % file_link + \
                                   file_results + END_FILE
            else:
                dir_results = process_repo(full_file_path, repo_url, repo_name, regex, output_directory)
                if len(dir_results) > 0:
                    html_results = html_results + dir_results
    return html_results


def filter_repos(repos):
    filtered_repos = []
    for repo in repos:
        if 'voice' in repo['name']:
            filtered_repos.append(repo)
    return(filtered_repos)

"""
Main method
"""


def main():
    try:
        server, org, repo, r, start_repo, output_directory, wiki = get_args()
        regex = re.compile(r, re.IGNORECASE)
        ghe_token = os.getenv('GHE_ACCESS_TOKEN')
        if ghe_token is None:
            raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
        # Get all the repos for the org
        headers = dict(Authorization='token %s' % ghe_token)
        parameters = dict(per_page='%s' % PAGE_SIZE)
        if repo is None:
            repos_url = 'https://%s/api/v3/orgs/%s/repos' % (server, org)
            repos = handle_GHE_calls.makeCall(repos_url, headers, parameters, print_status=True,
                                              maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
        else:
            repo_url = 'https://%s/api/v3/repos/%s/%s' % (server, org, repo)
            repo = handle_GHE_calls.makeCall(repo_url, headers, parameters, print_status=True,
                                             maxretries=MAX_RETRIES, TIMEOUT=TIMEOUT)
            repos = [repo]
        # Filter the repos to process the ones we want to
        repos = filter_repos(repos)
        # If the directory exists, remove all previous clones to get the latest
        clone_dir = "%s/clones" % output_directory
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
                    html_results = ''

                    # First process clone looking for matches to regex
                    clone_target = "%s/%s" % (clone_dir, repo['name'])
                    os.system("git clone git@github.com:%s.git %s" % (repo['full_name'], clone_target))
                    # This clone may have failed, so we need to check to see if it exists
                    if os.path.isdir(clone_target) is True:
                        html_results += process_repo(clone_target, repo['html_url'], repo['name'], regex, output_directory)

                    # Now handle wiki if it exists. clone it to a temp location and scan it separately.
                    # This is a bit hacky because has_wiki is true sometimes when there is not a wiki.
                    has_wiki = repo.get('has_wiki')
                    if has_wiki is True and wiki is True:
                        clone_target = "%s/%s/wiki" % (clone_dir, repo['name'])
                        os.system("git clone git@github.com:%s.wiki.git %s" % (repo['full_name'], clone_target))
                        # This clone may have failed, so we need to check to see if it exists
                        if os.path.isdir(clone_target) is True:
                            wiki_url = 'https://%s/%s/%s/wiki' % (server, org, repo['name'])
                            html_results += process_repo(clone_target, wiki_url, repo['name'], regex, output_directory)

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
