#!/opt/bb/bin/python

"""Build an index of GitHub gists"""


import json
import math
import sys
import os
import re

from collections import Counter

import glob
import itertools
import string
import tempfile

import requests
from requests.auth import HTTPBasicAuth



tempdir = tempfile.mkdtemp()

os.mkdir(tempdir + '/tags')

hashes = {}
tag_hash = {}

git_user = 'some_engineer'


token_file = '/home/some_engineer/.ssh/gist_token'
try:
    with open(token_file) as token_file:
        token_value = token_file.readline().strip()
except Exception:
    print "No token data"
    sys.exit(3)


plain_user = HTTPBasicAuth('', token_value)

gists_per_page = 20


def get_cosine(vec1, vec2):
    """Calculate cosine value"""
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum([vec1[x] * vec2[x] for x in intersection])

    sum1 = sum([vec1[x]**2 for x in vec1.keys()])
    sum2 = sum([vec2[x]**2 for x in vec2.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    else:
        return float(numerator) / denominator


def screen_count(gists_per_page):
    """count how many cycles needed to scrape GitHub @ 30 items per-page"""

    gist_url = 'https://api.github.com/users/' + git_user + '/gists?per_page=' + str(gists_per_page)

    all_gists = requests.get(gist_url, auth=plain_user, verify=False)

    # Drop punctuation
    clean = all_gists.headers['Link'].translate(string.maketrans(string.punctuation, ' '*len(string.punctuation)))

    # Re-break on whitespace
    clean_list = clean.split()

    pages_to_load = clean_list[-3]

    return pages_to_load


def topical(filename, gist_id, gist_description):
    """Group gists based-on hashtags in comment"""

    #
    # Ask me later
    #

    gist_comments_url = 'https://api.github.com/gists/' + gist_id + '/comments'

    gist_comments = requests.get(gist_comments_url, auth=plain_user, verify=False).json()

    # No comments at-all
    #

    if gist_description != "Generated Index":
        if len(gist_comments) == 0:
            with open(tempdir + '/tags/untagged', 'a') as tag_buffer:
                markdown_link = '* [' + filename + '](' + 'https://gist.github.com/' + git_user + '/' + gist_id + ') ' + gist_description
                tag_buffer.write(markdown_link + "\n")


    for gist_comment in gist_comments:
        for tag in gist_comment['body'].split():
            if tag.startswith('#'):
                #tagged = 1

                tag = re.sub('#', '', tag)

                with open(tempdir + '/tags/' + tag, 'a') as tag_buffer:
                    markdown_link = '* [' + filename + '](' + 'https://gist.github.com/' + git_user + '/' + gist_id + ') ' + gist_description
                    tag_buffer.write(markdown_link + "\n")



this_screen = 1
screen_count_value = screen_count(gists_per_page)


while int(this_screen) <= int(screen_count_value):
    gist_url = 'https://api.github.com/users/' + git_user + '/gists?per_page=' + str(gists_per_page) + '&page=' + str(this_screen)

    all_gists = requests.get(gist_url, auth=plain_user, verify=False).json()

    for gist in all_gists:
        for gistfile in gist['files']:
            language = gist['files'][gistfile]['language']
            filename = gist['files'][gistfile]['filename']
            raw_url = gist['files'][gistfile]['raw_url']
            gist_id = gist['id']
            gist_description = gist['description']

            hashes[filename] = gist_id
            hashes[gist_id] = gist_description

            topical(filename, gist_id, gist_description)

            try:
                if language != "Markdown":
                    buffer_file = tempdir + '/' + filename

                    source = requests.get(raw_url, auth=plain_user, verify=False).text

                    with open(buffer_file, 'w') as buffer_handle:
                        buffer_handle.write(source)

            except Exception as e:
                print str(e)
                continue

    this_screen = this_screen + 1


for a, b in itertools.combinations(sorted(glob.glob(tempdir + '/*')), 2):
    if os.path.isfile(a) and os.path.isfile(b):
        a_text = []
        b_text = []

        for line in open(a).readlines():
            for word in line.strip().split():
                a_text.append(word)

        for line in open(b).readlines():
            for word in line.strip().split():
                b_text.append(word)

        cozy = get_cosine(Counter(a_text), Counter(b_text))

        if cozy > 0.8:
            a_hash = hashes[os.path.basename(a)]
            b_hash = hashes[os.path.basename(b)]

            for tagfile in glob.glob(tempdir + '/tags/*'):
                tagfile_handle = open(tagfile + '.sieve', 'w')

                for line in open(tagfile).readlines():
                    if re.search(a_hash, line):

                        line = line.strip()

                        line = line + " " + str(int(cozy * 100)) + "% dupe confidence: " + os.path.basename(b) + ",\n"

                    tagfile_handle.write(line)

                tagfile_handle.close()

                os.rename(tagfile + '.sieve', tagfile)

#
#

new_index = open(tempdir + '/index.md.new', 'w')

tag_list = glob.glob(tempdir + '/tags/*')

for index in sorted(glob.glob(tempdir + '/tags/*')):
    if os.path.basename(index) != "untagged":
        new_index.write("\n#" + os.path.basename(index) + "\n")

        for classified in open(index).readlines():
            new_index.write(classified)

new_index.write("\n\n---\n\n")


for unclassified in open(tempdir + '/tags/untagged').readlines():
    new_index.write(unclassified)

new_index.close()


gist_index_url = 'https://api.github.com/gists/' + str(hashes['index.md'])

index_text = open(tempdir + '/index.md.new').readlines()

index = "\n".join(index_text)

payload = {"description":"Generated Index", "files": {"index.md": {"content":index}}}

all_gists = requests.patch(gist_index_url, data=json.dumps(payload), auth=plain_user, verify=False)
