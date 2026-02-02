# This script downloads all metadata files from the Corral page and puts them into one directory

# Necessary libraries for this code
import regex as re
import ssl
import json
import urllib
import os
from urllib import request

URL = "https://web.corral.tacc.utexas.edu/digitalporousmedia/archive/"
context = ssl._create_unverified_context()

req = urllib.request.urlopen(URL,context=context)

string = req.read().decode('utf-8')

# Regex patter which searches through the above string and finds all project names which match the structure "DRP-###"
DRPs = re.findall(r'DRP-\d{1,3}',string)
DRPs = list(set(DRPs))

os.mkdir("./Metadata")

for DRP in DRPs:
    url="https://web.corral.tacc.utexas.edu/digitalporousmedia/archive/"+DRP+"/"+DRP+"_metadata.json"
    context = ssl._create_unverified_context()
    with urllib.request.urlopen(url, context=context) as response:
        charset = response.headers.get_content_charset() or 'utf-8'
        text = response.read().decode(charset)
    name = "./Metadata/"+DRP+".json"
    text_file = open(name, "w")
    text_file.write(text)
    text_file.close()