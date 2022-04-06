import time
import requests
import datetime

RETRY_INTERVAL = 3
"""
Method for calling Zenhub API. Also handles rate limiting. 'verify=false' is to get around SSL errors. You can also get
pass your SSL certificate. See the Python requests package API.
"""


def make_request(url, zenhub_headers, params=None, method='GET', timeout=None, maxretries=3):
    if method == 'GET':
        response = requests.get(url, headers=zenhub_headers, verify=False, timeout=timeout)
    elif method == 'POST':
        response = requests.post(url, headers=zenhub_headers, data=params, verify=False, timeout=timeout)
    elif method == 'PUT':
        response = requests.put(url, headers=zenhub_headers, data=params, verify=False, timeout=timeout)
    if response.status_code == 403:
        # Zenhub rate limit exceeded
        rate_limit_reset = datetime.datetime.fromtimestamp(int(response.headers.get('X-RateLimit-Reset')))
        sleep_time = (rate_limit_reset - datetime.datetime.now()).total_seconds() + 1
        print('ZenHub rate limit exceeded, sleeping for %d seconds.' % sleep_time)
        time.sleep(sleep_time)
        return make_request(url, zenhub_headers, params=params, method=method, timeout=timeout)
    elif response.status_code == 400:
        # likely a timing error between Github and Zenhub
        if maxretries > 0:
            # wait a bit and try again
            print('400 error. Zenhub probably lagging behind Github. Retrying in %s seconds.' % RETRY_INTERVAL)
            time.sleep(RETRY_INTERVAL)
            return make_request(url, zenhub_headers, params=params, method=method,
                                timeout=timeout, maxretries=maxretries - 1)
        else:
            results = response.json()
            raise Exception('400 error attempting to update Zenhub: %s' % results['content'])
    elif response.status_code > 201:
        # else some other error
        print('Error with %s to %s: %d - %s' % (method, url, response.status_code, response.content))
        return None
    else:
        if len(response.content) == 0:
            return {}
        else:
            return response.json()