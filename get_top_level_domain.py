"""
Created on Feb 1, 2017

@author: kellrman

Returns the top level domain from a url

"""

def get_domain(url):
    top_level_domain = None
    # first get rid of http:// if it's in the GITHUB_URL
    double_slash = url.find('//')
    if double_slash >= 0:
        url_string = url[double_slash+2:len(url)]
    else:
        url_string = url
    # next get rid of any trailing / qualifiers, keeping only the top level domain name
    slash_index = url_string.find('/')
    if slash_index >= 0:
        url_string = url_string[0:slash_index]
    # now, get rid of the .com, .edu, .org etc
    period_index = url_string.rfind('.')
    if period_index >= 0:
        url_string = url_string[0:period_index]
    # now get the top level domain qualifier
    period_index = url_string.rfind('.')
    if period_index >= 0:
        top_level_domain = url_string[period_index+1:len(url_string)]
    else:
        top_level_domain = url_string
    return top_level_domain