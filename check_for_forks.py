import traceback
import os
import argparse
import handle_GHE_calls
import requests

def get_args():
    parser = argparse.ArgumentParser(
        description='Lists all forks for an organization')
    # Add arguments
    parser.add_argument(
        '-s', '--server', type=str, help='GitHub Enterprise server name. ', required=True)
    parser.add_argument(
        '-o', '--org', type=str, help='GitHub org to list the repos for.', required=True)

    args = parser.parse_args()
    server = args.server
    org = args.org

    return server, org


def main():
    try:
        ghe_token = os.getenv('GHE_ACCESS_TOKEN')
        if ghe_token is None:
            raise Exception('GHE_ACCESS_TOKEN environment variable not defined.')
        ghe_headers = {"Authorization": "token %s" % ghe_token, "Accept": "application/vnd.github.v3+json"}

        server, org = get_args()

        gh_api_endpoint = 'https://%s/api/v3' % server

        repos = handle_GHE_calls.makeCall('%s/orgs/%s/repos' % (gh_api_endpoint, org), headers=ghe_headers,
                                          parameters=None)
        print('Forks in %s and forks of repos in %s:' % (org, org))
        for repo in repos:
            if repo['fork'] is True:
                print('%s/%s is a fork.' % (org, repo['name']))
            response = requests.get(repo['forks_url'], headers=ghe_headers, verify=False, timeout=60)
            if response.status_code == 200:
                forks = response.json()
                for fork in forks:
                    print('%s is a fork of %s.' %(fork['full_name'], repo['full_name']))


    except Exception as e:

        print('Error: ' + str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
