#!/usr/bin/env python3
# coding: utf-8

# this script is needed for shell wrappers

import sys
from config import CONFIG


stanza = sys.argv[1]
key = sys.argv[2]
try:
    value = CONFIG._config[stanza][key]
    print(value)
except:
    print("config {}:{} not found".format(stanza, key))
