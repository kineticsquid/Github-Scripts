import os
import json

os.environ['APIKEY'] = 'uPmRXh***************************E1EAZJ6Hu'
os.environ['API_URL'] = 'https://api.us-east.assistant.watson.cloud.ibm.com/instances/96a44bf2-df75-4683-852d-1187573b8948'

import get_logs

LOGS_DIR_PATH = '/Users/jk/Downloads/Oficinas-Logs/Oficinas-1'

files = os.listdir(LOGS_DIR_PATH)
all_logs = []
for file_name in files:
    abs_path = os.path.join(LOGS_DIR_PATH, file_name)
    if os.path.isfile(abs_path) and file_name[0] != '.':
        file = open(abs_path, 'r')
        logs = json.load(file)
        all_logs += logs
        file.close()
        print('Added %s log entries from file \'%s\'.' % (len(logs), file_name))

user_detail, authorized_user_counts_by_month, unique_authorized_users_by_month = \
        get_logs.calculate_authorized_users(all_logs)

print(authorized_user_counts_by_month)

