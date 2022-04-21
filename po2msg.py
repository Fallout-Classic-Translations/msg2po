#!/usr/bin/env python3
# coding: utf-8

import argparse
from bgforge_po import EPOFile, po2file

parser = argparse.ArgumentParser(
    description="Extract Fallout MSG from gettext PO", formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument("INPUT_FILE", help="input PO file")
parser.add_argument("OUTPUT_FILE", help="output MSG file")
parser.add_argument("-e", dest="encoding", help="output MSG encoding", default="cp1252")
parser.add_argument("--path", dest="path", help="MSG occurrence in PO (relative path) - defaults to output MSG name")
args = parser.parse_args()

if args.path is None:
    path = args.OUTPUT_FILE
else:
    path = args.path

epo = EPOFile(args.INPUT_FILE)  # open once, it's a heavy op
po2file(epo, args.OUTPUT_FILE, args.encoding, path)
