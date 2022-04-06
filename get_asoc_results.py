"""
Script to collect ASoC findings reports.

ASoC API Swagger: https://cloud.appscan.com/swagger/ui/index#/

Requires an API keyid and secret. Get these as follows:
1.	Navigate to https://cloud.appscan.com/AsoCUI/serviceui/main/myapps/portfolio
2.	From the hamburger menu in the upper left, select "Settings". Then click "Generate"
3.	Save the generated Key ID and Key Secret where you can easily copy/paste to pass them into this script

To change the filters on the apps and the issues returned, edit the query parameters in the code.

Note, the routine that handles calling the ASoC API has logic to deal with multiple pages, but the ASoC API regardless
of number of results never seems to return a next page link. Hence the warning if the number of results
equals the max.

"""
import traceback
import argparse
import json
import requests
import time

# Default ASoC API end point
ASOC_URL = "https://cloud.appscan.com/api/V2"
# File name of output file for issues. Directory is an input parameter to this script
OUTPUT_FILE_NAME = 'asoc_issues.csv'
# Period to wait for reports to finish generating. This is because the request to generate a report is
# asynchronous
REPORT_WAIT_INTERVAL = 10

"""
Routine for getting script parameters. 
"""


def get_args():
    parser = argparse.ArgumentParser(
        description='Get results from ASoC scans.')
    parser.add_argument(
        '-u', '--api_url', type=str, help='API URL end point, no ending \'/\'.', default=ASOC_URL)
    parser.add_argument(
        '-k', '--key_id', type=str, help='ASoC KeyID', required=True)
    parser.add_argument(
        '-s', '--key_secret', type=str, help='ASoC KeySecret', required=True)
    parser.add_argument(
        '-o', '--output_directory', type=str, help='Output directory, no ending \'/\'.')
    parser.add_argument(
        '-f', '--output_file_name', type=str, help='Name of output file.', default=OUTPUT_FILE_NAME)
    parser.add_argument(
        '-a', '--apps_filter', type=str, help='String to filter apps processed. Use single quotes.')
    parser.add_argument(
        '-i', '--issues_filter', type=str, help='String to filter issues processed and included in the reports. Use single quotes.')
    args = parser.parse_args()
    # Remove the trailing blanks if we find them, despite the warning
    if args.api_url[len(args.api_url) - 1] == '/':
        args.api_url = args.api_url[0:len(args.api_url) - 1]
    if args.output_directory[len(args.output_directory) - 1] == '/':
        args.output_directory = args.output_directory[0:len(args.output_directory) - 1]
    return args.key_id, args.key_secret, args.output_directory, args.api_url, args.apps_filter, \
           args.issues_filter, args.output_file_name


"""
Class to handle calls to ASoC API. MAX_RESULTS is set to the min of the max results that can be returned for 
number of apps, scans, issues. As mentioned above, while there is logic for multiple pages, the API never
seems to return a next page link
"""


class APIInvoker:
    """
    Initialization method. Also gets the bearer token. Saving the expiration of the token even
    though I currently don't use it.
    """

    def __init__(self, url, key_id, key_secret):
        self.key_id = key_id
        self.key_secret = key_secret
        self.url = url
        self.http_headers = {'Content-Type': 'application/json',
                             'Accept': 'application/json'}

        data = {'KeyID': key_id, 'KeySecret': key_secret}
        url = "%s/Account/ApiKeyLogin" % url
        response = requests.post(url, headers=self.http_headers, data=json.dumps(data))
        if response.status_code == 200:
            results = response.json()
            self.bearer_token = results['Token']
            self.token_expiration = results['Expire']
            self.http_headers['Authorization'] = 'Bearer %s' % self.bearer_token
        else:
            raise Exception("%s:%s", (response.status_code, response.text))

    """
    Method to make the call to the ASoC API. 
    - function: reguests.get or requests.post
    - api: ASoC API that comes after '/api/V2'
    - parameters: any query parameters
    - data: data for post requests
    """

    def invoke(self, function, api, headers=None, parameters=None, data=None):
        # Construct the full URL for the API call
        url = '%s%s' % (self.url, api)
        # Define the query parameters for the call
        if parameters is None:
            parameters = {}
        # if there are additional HTTP headers for this call, merge them
        if headers is not None:
            http_headers = self.http_headers.copy()
            for header in headers:
                http_headers[header] = headers[header]
        else:
            http_headers = self.http_headers
        response = function(url, headers=http_headers, params=parameters, data=json.dumps(data))

        # Bit of a hack here. Some calls simply return a list, e.g. /apps and /scans. Calls to get
        # Issues return a dict with a list of items and a next page link. Calls to get report status return a dict
        # that requires no further processing. Calls to get report content return just a bytestring
        #
        # First try to decode JSON, if it fails, this is report content.
        if response.status_code > 204:
            raise Exception("%s:%s", (response.status_code, response.text))
        try:
            results = response.json()
        except Exception as e:
            return response.content.decode('utf-8')
        if type(results) is dict:
            # Check to see if this is the first page of a list
            items = results.get('Items')
            if items is not None:
                # If we find 'Items' in the results, it means this is the first page of a list
                # Get the next page.
                next_page = results.get('NextPageLink')
                while next_page is not None:
                    # While there are no more pages, get the next page and add the items to previous items found
                    self.invoke(requests.get, next_page)
                    if response.status_code != 200:
                        raise Exception("%s:%s", (response.status_code, response.text))
                    results = response.json()
                    next_page = results.get('NextPageLink')
                    items = items.append(results['Items'])
            else:
                # It's a dict but not the first page of a list, so simply return it
                items = results
        else:
            # Results are not a dict, so must be a list. Return the list.
            items = results
        return items


"""
Routine to generate a report for a scan
"""


def generate_scan_report(api_invoker, scan, issues_filter):

    config = {
        "Configuration": {
            "Summary": True,
            "Details": True,
            "Discussion": True,
            "Overview": True,
            "TableOfContent": True,
            "Advisories": True,
            "FixRecommendation": True,
            "History": True,
            "IsTrialReport": True,
            "MinimizeDetails": True,
            "ReportFileType": "Html",
            "Title": "Scan: %s" % scan['Name'],
            "Notes": "Notes",
            "Locale": "Locale"
        },
        "OdataFilter": "",
        "ApplyPolicies": "None",
        "SelectPolicyIds": [
            "00000000-0000-0000-0000-000000000000"
        ]
    }
    if issues_filter is not None:
        config['OdataFilter'] = "(%s)" % issues_filter
    data = config
    results = api_invoker.invoke(function=requests.post,
                                 api='/Reports/Security/Scan/%s' % scan['Id'],
                                 data=data)
    return results


"""
Routine to generate a report for an application
"""


def generate_app_report(api_invoker, app, issues_filter):

    config = {
        "Configuration": {
            "Summary": True,
            "Details": True,
            "Discussion": True,
            "Overview": True,
            "TableOfContent": True,
            "Advisories": True,
            "FixRecommendation": True,
            "History": True,
            "IsTrialReport": True,
            "MinimizeDetails": True,
            "ReportFileType": "Html",
            "Title": "App: %s" % app['Name'],
            "Notes": "Notes",
            "Locale": "Locale"
        },
        "OdataFilter": "",
        "ApplyPolicies": "None",
        "SelectPolicyIds": [
            "00000000-0000-0000-0000-000000000000"
        ]
    }
    if issues_filter is not None:
        config['OdataFilter'] = "(%s)" % issues_filter
    data = config
    results = api_invoker.invoke(function=requests.post,
                                 api='/Reports/Issues/Application/%s' % app['Id'],
                                 data=data)
    return results


"""
Routine to check on status of reports and download them when they are complete. They get 
downloaded to the output directory
"""


def wait_on_reports_and_print(api_invoker, reports, output_directory):
    # while we have reports that have not completed
    while len(reports) > 0:
        for report in reports:
            # Get the status of this report
            response = api_invoker.invoke(function=requests.get,
                                          api='/Reports/%s' % report['Id'])
            status = response['Status']
            if status == 'Ready':
                # If ready, download and save it to file.
                print('Downloading report %s' % report['Name'])
                report_content = api_invoker.invoke(function=requests.get,
                                              api='/Reports/Download/%s' % report['Id'])
                report_file_name = '%s/%s.html' % (output_directory, report['Name'])
                report_file = open(report_file_name, 'w')
                report_file.writelines(report_content)
                report_file.close()
                # We processed this report, so remove it from the list
                reports.remove(report)
        # If there are reports left in the list, meaning they weren't ready to be downloaded, go to sleep
        # for a bit and then try again
        if len(reports) > 0:
            print('Still some incomplete reports. Waiting for %s seconds before trying again.' % REPORT_WAIT_INTERVAL)
            time.sleep(REPORT_WAIT_INTERVAL)


def main():
    try:
        # Input parameters and open output file
        key_id, key_secret, output_directory, asoc_url, apps_filter, issues_filter, output_file_name = get_args()
        output_file_full_path = "%s/%s" % (output_directory, output_file_name)
        output_file = open(output_file_full_path, 'w')

        # Instantiate the API invoker
        api_invoker = APIInvoker(asoc_url, key_id, key_secret)

        # Get the ASoC apps I have access to subject to the filter, if specified
        parameters = {'$orderby': 'Name',
                      '$top': 5000}
        all_apps = api_invoker.invoke(function=requests.get, api='/Apps',
                                     parameters=parameters)
        apps = []
        for app in all_apps:
            if apps_filter in app['Name']:
                apps.append(app)

        # Begin the output by writing the column headers
        output_file.write('Report Name, Date, Type, Tool, Component, Category, Severity, API Vuln, API, Location\n')


        # This list holds the ids of the reports being generated. Need to use this to later check for status and
        # when complete, download the reports
        reports = []

        # Loop through all the ASoC apps
        for app in apps:

            print('Processing %s' % app['Name'])
            # Get the scans for this app
            parameters = {'$orderby': 'LastModified',
                          '$top': 5000}
            scans = api_invoker.invoke(function=requests.get,
                                       api='/Apps/%s/Scans' % app['Id'],
                                       parameters=parameters)
            if len(scans) > 0:
                # If we find scans, examine only the most recent scan
                most_recent_scan = scans[len(scans) - 1]
                # Get the issues for this scan
                parameters = {'$orderby': 'IssueType',
                              '$top': 5000}
                if issues_filter is not None:
                    parameters['$filter'] = issues_filter
                issues = api_invoker.invoke(function=requests.get,
                                            api='/Issues/Scan/%s' % most_recent_scan['Id'],
                                            parameters=parameters)
                if issues is not None and len(issues) > 0:
                    # If we have issues, generate an html report with issue detail for reference and save the ID
                    reports.append(generate_scan_report(api_invoker=api_invoker, scan=most_recent_scan, issues_filter=issues_filter))
                    # reports.append(generate_app_report(api_invoker=api_invoker, app=app, issues_filter=None))
                    # Finally output the issues
                    for issue in issues:
                        output_file.writelines('%s, %s, %s, %s, %s, %s, %s, %s, %s, %s\n' % (
                            issue['ScanName'],
                            issue['DateCreated'],
                            issue['DiscoveryMethod'],
                            'ASoC',
                            app['Name'],
                            issue['IssueType'],
                            issue['Severity'],
                            issue['ApiVulnName'],
                            issue['Api'],
                            issue['Location']
                        ))
                else:
                    print('No issues found for %s in %s' % (app['Name'], most_recent_scan['Name']))
            else:
                print('No scans found for %s' % app['Name'])
        output_file.close()

        # Now check the status of the reports submitted and when complete ('Ready'), downland them and save
        # to file
        wait_on_reports_and_print(api_invoker=api_invoker, reports=reports, output_directory=output_directory)

    except Exception as e:
        print('Error: ' + str(e))
        traceback.print_exc()


if __name__ == '__main__':
    main()
