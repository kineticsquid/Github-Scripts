"""
Created on Jan 20, 2017

Handles paging of GitHub API requests

Takes as input a url, headers dictionary, and parameters dictionary. The headers
dictionary must have the GitHub access token defined in "token". The parameters
dictionary must have page size defined in "per_page".

Returns an array of aggregated results.

"""

import requests
import time

DEFAULT_TIMEOUT = 30
WAIT_TIME = 1
def makeCall(url, headers, parameters, **kwargs):
    if 'print_status' in kwargs:
        print_status = kwargs['print_status']
    else:
        print_status = False
    if 'logger' in kwargs:
        logger = kwargs['logger']
    else:
        logger = None
    if 'number' in kwargs:
        number = kwargs['number']
    else:
        number = None
    if 'TIMEOUT' in kwargs:
        timeout = kwargs['TIMEOUT']
    else:
        timeout = DEFAULT_TIMEOUT
    if 'maxretries' in kwargs:
        maxretries = kwargs['maxretries']
    else:
        maxretries = 1

    results = []
    while url is not None:
        if number is not None and len(results) >= number:
            break
        retries = 0
        while True:
            try:
                if parameters is None:
                    response = requests.get(url, headers=headers, timeout=timeout)
                else:
                    response = requests.get(url, params=parameters, headers=headers, timeout=timeout)
                break
            except:
                retries += 1
                time.sleep(WAIT_TIME)
                print('Retrying %s' % url)

            if retries > maxretries:
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
            if print_status:
                status = "Retrieved items %s to %s." % (str(len(results) + 1), str(len(results) + len(new_results)))
                if logger:
                    logger.info(status)
                else:
                    print(status)
            if len(results) == 0:
                results = new_results
            else:
                results = results + new_results
        elif response.status_code == 403:
                response_headers = response.headers
                rate_limit_remaining = response.headers['x-ratelimit-remaining']
                if int(rate_limit_remaining) == 0:
                    # We've reached our rate limit and need to wait
                    rate_limit_reset = response.headers['x-ratelimit-reset']
                    time_to_wait = int(rate_limit_reset) - int(time.time())
                    wait_until = time.strftime('%H:%M:%S', time.localtime(int(rate_limit_reset)))
                    status = 'API limit reached. Waiting for %s seconds, until %s.' %  (time_to_wait, wait_until)
                    if logger:
                        logger.info(status)
                    print(status)
                    time.sleep(time_to_wait)
                    status = 'It\'s now %s. Starting again.' %  wait_until
                    if logger:
                        logger.info(status)
                    print(status)
                else:
                    # Some other error resulting in 403 so raise an exception
                    raise Exception("%s: %s" % (response.status_code, url))
        elif response.status_code == 409:
            # This covers the case where empty repos return 409 when asking for commits
            print('\'%s\' returned 409, empty repo.' % url)
            url = None
        else:
            raise Exception("%s: %s" %(response.status_code, url))

    if number is None or number > len(results):
        return results
    else:
        return results[0:number]