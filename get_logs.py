import requests
import datetime
import os

"""
This routine returns all the logs in JSON (/v1 and /v2 message calls) for all work spaces for a given
service instance of Watson Assistant. 
"""

def get_all_logs():
    API_VERSION = '2020-04-01'
    LOGS_API = '/v1/workspaces/%s/logs?version=%s'
    WORKSPACES_API = '/v1/workspaces?version=%s'

    if 'APIKEY' in os.environ:
        APIKEY = os.environ['APIKEY']
    else:
        raise Exception('Error no environment variable \'APIKEY\' defined.')
    if 'API_URL' in os.environ:
        API_URL = os.environ['API_URL']
    else:
        raise Exception('Error no environment variable \'API_URL\' defined.')
    http_headers = {'Content-Type': 'application/json',
                    'Accept': 'application/json'}
    auth = ('APIKEY', APIKEY)
    
    # Get all the workspaces
    workspaces_url = API_URL + WORKSPACES_API % API_VERSION
    response = requests.get(workspaces_url, auth=auth, headers=http_headers)
    if response.status_code == 200:
        results = response.json()
    else:
        raise Exception(response.content)

    # Now retrieve the logs for each of the workspaces
    all_logs = []
    count = 1
    workspaces = results['workspaces']
    for workspace in workspaces:
        done = False
        logs_url = API_URL + LOGS_API % (workspace['workspace_id'], API_VERSION)
        # Continue retrieving logs until there are no more pages of logs
        while not done:
            response = requests.get(logs_url, auth=auth, headers=http_headers)
            if response.status_code == 200:
                results = response.json()
                all_logs += results['logs']
                print('Retrieved %s log entries from workspace \'%s\'.' % (len(results['logs']),
                                                                           workspace['workspace_id']))
                next_page = results.get('pagination')
                if len(next_page) > 0:
                    logs_url = API_URL + next_page['next_url']
                else:
                    done = True
            else:
                raise Exception(response.content)
        print('Finished %s of %s workspaces.' % (count, len(workspaces)))
        count += 1
    return all_logs

"""
This routine processes the /logs JSON to generate a flatter data structure without PI for further processing:
 
    'user_detail':
        - request_month - 3 char month when the /message call was made (e.g. 'Jan', 'Feb')
        - request_date - date when the /message call was made
        - request_time - time when the /message call was made
        - authorized_user - string used to determine who the user is
        - type - how the 'authorized_user' value was determined; by field 'user_id', 'session_id' or 'conversation_id'
        - dialog_turn_counter' - what turn of the conversation this /message call represents
        - text_length - length of the input utterance; 0 if none
        - billable - True or False indicating if this request/response and associated user_id is billable. 
        - workspace_id - workspace of this /message request

Based on this detail, this routine also calculates unique users by month and lists of the ids of those users by
month.

    'unique_authorized_users_by_month': 
        {'month1': {'Fred', 'Barney', 'Wilma'', Betty', 'Bam Bam'},
        'month2': {'George', 'Jane', 'Elroy'},
        'month3': {'Gilligan', 'Skipper', 'Professor', 'Ginger, 'Maryann'}
        }
        
    'authorized_user_counts_by_month': 
        {'user_id': 
            {'month1': total, 'month2': total, 'month3': total}, 
        'session_id': 
            {'month1': total, 'month2': total, 'month3': total}, 
        'conversation_id': 
            {'month1': total, 'month2': total, 'month3': total}}
"""

def calculate_authorized_users(logs):

    def log_sort_function(i):
        return str(i['request_timestamp'])

    # First, sort the logs so the graph plotting is easier
    logs.sort(key=log_sort_function)

    user_detail = []
    unique_authorized_users_by_month = {}
    authorized_user_counts_by_month = {'user_id': {}, 'session_id': {}, 'conversation_id': {}}

    for entry in logs:
        # Get the authorized user id based on what fields in the /message payload were set. In priority
        # order, user_id, session_id, conversation_id.
        user_id = None
        user_id = entry['request'].get('user_id')
        if user_id is not None:
            # user_id is set so record this value as the authorized user. This is the same for
            # both /v1/message and /v2/message
            user_id_type = 'user_id'
        else:
            # Otherwise, look for user_id in context metadata, for /v1/message
            metadata = entry['response']['context'].get('metadata')
            if metadata is not None:
                user_id = metadata.get('user_id')
                if user_id is not None:
                    user_id_type = 'user_id'
        if user_id is None:
            user_id = entry['response']['context']['system'].get('session_id')
            if user_id is not None:
                # if we can't find user_id, the look for the substitute. If we find session_id
                # it means this is a /v2/message call, use it.
                user_id_type = 'session_id'
            else:
                # otherwise, user conversation_id. Both /v1/message and /v2/message
                user_id = entry['response']['context']['conversation_id']
                user_id_type = 'conversation_id'

        # Get the utterance text if there is input. We're getting this solely to get its length. For
        # privacy reasons, we are saving on the length to indicate if there was input.
        utterance_text = ''
        input = entry['request'].get('input')
        if input is not None:
            input_text = input.get('text')
            if input_text is not None:
                utterance_text = input_text

        # Write the flatter log record. This is what will be written as output to a CSV file for
        # futher analysis
        request_timestamp = datetime.datetime.strptime(entry['request_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ')
        new_entry = {'request_month': request_timestamp.strftime('%b'),
                    'request_date': request_timestamp.strftime('%Y-%m-%d'),
                     'request_time': request_timestamp.strftime('%H:%M:%S'),
                     'authorized_user': user_id,
                     'type': user_id_type,
                     'dialog_turn': int(entry['response']['context']['system']['dialog_turn_counter']),
                     'text_length': len(utterance_text),
                     'workspace_id': entry['workspace_id']}
        # Mark this entry as billable, and adding this user_id as an authorized user if there is text input
        # or if we are past the first turn of the dialog. Conversely, do not mark this as billable if there
        # is no text input and we are on the first turn of the dialog. We're using 'True' and 'False' strings here
        # instead of True and False in order to make the export to CSV work.
        if new_entry['dialog_turn'] <= 1 and new_entry['text_length'] == 0:
            new_entry['billable'] = 'False'
        else:
            new_entry['billable'] = 'True'
        user_detail.append(new_entry)

        # Add this as an authorized user if we've determined the request/response is billable
        if new_entry['billable'] == 'True':
            month = new_entry['request_month']
            if month not in unique_authorized_users_by_month.keys():
                unique_authorized_users_by_month[month] = set()
                authorized_user_counts_by_month['user_id'][month] = 0
                authorized_user_counts_by_month['conversation_id'][month] = 0
                authorized_user_counts_by_month['session_id'][month] = 0
            if new_entry['authorized_user'] not in unique_authorized_users_by_month[month]:
                unique_authorized_users_by_month[month].add(new_entry['authorized_user'])
                authorized_user_counts_by_month[new_entry['type']][month] += 1

    return user_detail, authorized_user_counts_by_month, unique_authorized_users_by_month


def get_authorized_user_counts():
    all_logs = get_all_logs()
    user_detail, authorized_user_counts_by_month, unique_authorized_users_by_month = \
        calculate_authorized_users(all_logs)

    return user_detail, authorized_user_counts_by_month, unique_authorized_users_by_month