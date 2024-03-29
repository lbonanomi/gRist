#!/bin/python3

#pylint: disable=C0103

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


netrc_name = os.environ['HOME'] + '/.netrc'

if os.path.exists(netrc_name):
    with open(netrc_name) as netrc_file:
        netrc_data = netrc_file.readlines()

    field_counter = 0

    for field in netrc_data:
        if 'github.com' in field:
            git_user = (netrc_data[field_counter - 3]).split()[1]
            token_value = netrc_data[field_counter + 2].split()[1]
        field_counter = field_counter+1
else:
    print("Couldn't find ~/.netrc")
    sys.exit(2)



plain_user = HTTPBasicAuth('', token_value)


def get_cosine(vec1, vec2):
    """Calculate cosine value"""

    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum([vec1[x] * vec2[x] for x in intersection])

    sum1 = sum([vec1[x]**2 for x in vec1.keys()])
    sum2 = sum([vec2[x]**2 for x in vec2.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        retval = 0.0
    else:
        retval = float(numerator) / denominator

    return retval


def screen_count(per_page):
    """count how many cycles needed to scrape GitHub @ 30 items per-page"""

    count_gist_url = 'https://api.github.com/users/' + git_user + '/gists?per_page=' + str(per_page)

    these_gists = requests.get(count_gist_url, auth=plain_user)

    # Drop punctuation
    link_header = these_gists.headers['Link']
    clean = link_header.translate(str.maketrans(string.punctuation, ' '*len(string.punctuation)))

    # Re-break on whitespace
    clean_list = clean.split()

    pages_to_load = clean_list[-3]

    return pages_to_load


def topical(filename, gist_id, gist_description):
    """Group gists based-on hashtags in comment"""

    gist_comments_url = 'https://api.github.com/gists/' + gist_id + '/comments'

    gist_comments = requests.get(gist_comments_url, auth=plain_user).json()

    # No comments at-all
    #

    if gist_description is None:
        gist_description = ""


    if gist_description != "Generated Index":
        if len(gist_comments) == 0:
            with open(tempdir + '/tags/untagged', 'a') as tag_buffer:
                markdown_link = '* [' + filename + '](' + 'https://gist.github.com/' + git_user + '/' + gist_id + ') ' + gist_description
                tag_buffer.write(markdown_link + "\n")


    for gist_comment in gist_comments:
        for tag in gist_comment['body'].split():
            if tag.startswith('#'):
                tag = re.sub('#', '', tag)

                with open(tempdir + '/tags/' + tag, 'a') as tag_buffer:
                    markdown_link = '* [' + filename + '](' + 'https://gist.github.com/' + git_user + '/' + gist_id + ') ' + gist_description
                    tag_buffer.write(markdown_link + "\n")



this_screen = 1
gists_per_page = 20
screen_count_value = screen_count(gists_per_page)


while int(this_screen) <= int(screen_count_value):
    gist_url = 'https://api.github.com/users/' + git_user + '/gists?per_page=' + str(gists_per_page) + '&page=' + str(this_screen)

    all_gists = requests.get(gist_url, auth=plain_user).json()

    for gist in all_gists:
        for gistfile in gist['files']:
            this_language = gist['files'][gistfile]['language']
            this_filename = gist['files'][gistfile]['filename']
            this_raw_url = gist['files'][gistfile]['raw_url']
            this_gist_id = gist['id']
            this_gist_description = gist['description']

            hashes[this_filename] = this_gist_id
            hashes[this_gist_id] = this_gist_description

            topical(this_filename, this_gist_id, this_gist_description)

            try:
                if this_language != "Markdown":
                    buffer_file = tempdir + '/' + this_filename

                    source = requests.get(this_raw_url, auth=plain_user).text

                    with open(buffer_file, 'w') as buffer_handle:
                        buffer_handle.write(source)

            except Exception as e:
                print(str(e))
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

                        line = line + "  \n    - Possible duplicate of " + os.path.basename(b)
                        line = line + "  (" + str(int(cozy * 100)) + "% confidence)  \n"

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

all_gists = requests.patch(gist_index_url, data=json.dumps(payload), auth=plain_user)
