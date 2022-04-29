import re
import sys
from collections import OrderedDict
import polib
import os
import shutil
from contextlib import contextmanager
from natsort import natsorted
from config import CONFIG
from datetime import datetime

# extensions recognized by file2po, etc
VALID_EXTENSIONS = ["msg", "txt", "sve", "tra"]

# supported file formats
# pattern is used to parse original files
# line_format to write to translated files
# index, value, context, female - order of these tokens in pattern
# dotall - whether file entries are multiline
FILE_FORMAT = {
    "msg": {
        "pattern": "{(\d+)}{([^}]*)}{([^}]*)}",
        "dotall": True,
        "index": 0,
        "value": 2,
        "context": 1,
        "line_format": {
            "default": "{{{index}}}{{}}{{{value}}}\n",
            "context": "{{{index}}}{{{context}}}{{{value}}}\n",
            "female": "separate",
        },
    },
    "sve": {
        "pattern": "(\d+):(.*)",
        "dotall": False,
        "index": 0,
        "value": 1,
        "line_format": {
            "default": "{index}:{value}\n",
            "female": "separate",
        },
    },
    "txt": {
        "pattern": "(\d+):(.*)",
        "dotall": False,
        "index": 0,
        "value": 1,
        "comment": "indexed_txt",
        "line_format": {
            "default": "{index}:{value}\n",
            "female": "separate",
        },
    },
    "tra": {
        "pattern": "@(\d+)\s*?=\s*?~([^~]*?)~(?:\s)?(?:\[([^]]*)\])?(?:~([^~]*)~)?",
        "dotall": True,
        "index": 0,
        "value": 1,
        "context": 2,
        "female": 3,
        "line_format": {
            "default": "@{index} = ~{value}~\n",
            "context": "@{index} = ~{value}~ [{context}]\n",
            "female": "@{index} = ~{value}~ ~{female}~\n",
        },
    },
}


# used for determining empty strings, which are invalid by PO spec
EMPTY_COMMENT = "LEAVE empty space in translation"

# po: new translations added through weblate use case sensitive code: pt_BR.po. Keeping them.
LOWERCASE_EXCLUDE = [".git", ".svn", ".hg", "README.md", "po"]

CONTEXT_FEMALE = "female"


# file and dir manipulation
#################################
def get_ext(path):
    try:
        ext = path.rsplit(".", 1)[1].lower()
    except:
        ext = None
    return ext


def basename(path):
    if path.endswith(os.sep):
        path = path[:-1]
    return os.path.abspath(path).rsplit(os.sep, 1)[1]


def parent_dir(path):
    if path.endswith(os.sep):
        path = path[:-1]
    return os.path.abspath(path).rsplit(os.sep, 1)[0]


def strip_ext(filename):
    return filename.rsplit(".", 1)[0]


def get_dir(path: str):
    return path.rsplit(os.sep, 1)[0]


def create_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


# lowercase directory
def lowercase_rename(root_dir, items):
    for item in items:
        old_name = os.path.join(root_dir, item)
        new_name = os.path.join(root_dir, item.lower())
        if new_name != old_name:
            print("renaming {} to {}".format(old_name, new_name))
            os.rename(old_name, new_name)


def lowercase_recursively(dir):  # this is the function that is actually used
    for dir_name, subdir_list, file_list in os.walk(dir, topdown=False):
        subdir_list[:] = [d for d in subdir_list if d not in LOWERCASE_EXCLUDE]
        for sd in subdir_list:
            for dname, sdir_list, file_list in os.walk(sd, topdown=False):
                lowercase_rename(dir_name, file_list)
                lowercase_rename(dir_name, sdir_list)
    # why is this separate?
    children = os.listdir(dir)
    children[:] = [c for c in children if c not in LOWERCASE_EXCLUDE]
    with cd(dir):
        for c in children:
            new_c = c.lower()
            if c != new_c:
                print("renaming {} to {}".format(c, new_c))
                os.rename(c, new_c)


def dir_or_exit(d):
    if os.path.isdir(d):
        print("Found directory {}".format(d))
    else:
        print("Directory {} does not exist, cannot continue!".format(d))
        sys.exit(1)


def find_files(dir: str, ext: str):
    """
    Find files with extension ext in directory dir
    """
    files = []
    for root, subdir_list, file_list in os.walk(dir):
        for f in file_list:
            if get_ext(f) == ext:
                files.append((os.path.join(root, f)))
    return files


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


def get_enc(lang_path: str = "", file_path: str = ""):
    """
    Infers encoding based on dir/PO name and file path
    lang_path can be PO path or translation path, only basename is used
    """
    ENCODINGS = {
        "schinese": "cp936",
        "tchinese": "cp950",
        "czech": "cp1250",
        "japanese": "cp932",
        "korean": "cp949",
        "polish": "cp1250",
        "polski": "cp1250",
        "russian": "cp1251",
        "ukrainian": "cp1251",
    }

    DOS_ENCODINGS = {
        #  'czech': 'cp852',
        #  'polish': 'cp852',
        #  'polski': 'cp852',
        "russian": "cp866",
        "ukrainian": "cp866",
        #  'french': 'cp850',
        #  'francais': 'cp850',
        #  'german': 'cp850',
        #  'deutsch': 'cp850',
        #  'italian': 'cp850',
        #  'italiano': 'cp850',
        #  'spanish': 'cp850',
        #  'espanol': 'cp850',
        #  'castilian': 'cp850',
        #  'castellano': 'cp850',
    }

    DOS_FILENAMES = [
        "setup.tra",
        "install.tra",
    ]

    UTF_FILENAMES = [
        "ee.tra",
    ]

    encoding = CONFIG.encoding
    lang = strip_ext(basename(lang_path))
    filename = basename(file_path)

    if lang in ENCODINGS:
        encoding = ENCODINGS[lang]

    if filename in DOS_FILENAMES:
        try:
            encoding = DOS_ENCODINGS[lang]
        except:
            pass

    if filename in UTF_FILENAMES:
        encoding = "utf-8"

    utf_name = re.compile(".*_ee.tra$")
    if utf_name.match(filename):
        encoding = "utf-8"

    return encoding


################################


def metadata(old_metadata=None, pot=False, po=False):
    if old_metadata is None:
        data = {
            "Project-Id-Version": "PACKAGE VERSION",
            "Report-Msgid-Bugs-To": "",
            "Last-Translator": "FULL NAME <EMAIL@ADDRESS>",
            "Language-Team": "LANGUAGE <LL@li.org>",
            "Language": "",
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "X-Generator": "bgforge_po v.{}".format(CONFIG.version),
        }
        if pot:
            data["POT-Creation-Date"] = datetime.today().strftime("%Y-%m-%d-%H:%M") + "+0000"
        if po:
            data["PO-Revision-Date"] = datetime.today().strftime("%Y-%m-%d-%H:%M") + "+0000"
    else:
        return old_metadata
    return data


def file2po(filepath: str, po_path: str = "", encoding=CONFIG.encoding):
    """Returns PO file object"""

    trans = TRANSFile(filepath=filepath, is_source=True, encoding=encoding)  # load translations

    if po_path == "":
        po = polib.POFile()
        po.metadata = metadata()
    else:
        po = polib.pofile(po_path)

    trans_map = {}
    i = 0  # index in PO object
    for t in trans.entries:
        context = t.context

        # append to occurrences if id and context match
        if (t.value, context) in trans_map:
            e = po[trans_map[(t.value, context)]]
            e.occurrences.append((filepath, t.index))
            continue

        # no matching msgid + msgctxt, add new entry
        entry = polib.POEntry(
            msgid=t.value,
            msgstr="",
            occurrences=[
                (filepath, t.index),
            ],
            msgctxt=t.context,
            comment=t.comment,
        )
        po.append(entry)
        trans_map[(t.value, context)] = i
        i = i + 1

    return po


# check if extract file is present in po, exit with error if not
def check_path_in_po(po, path):
    present_files = set()
    for entry in po:
        for eo in entry.occurrences:
            present_files.add(eo[0])
    present_files_list = sorted(set(present_files))
    if path not in present_files_list:
        print("{} is not present in selected PO file".format(path))
        print("supply one of present files with --path argument:")
        for pf in present_files_list:
            print(pf)
        sys.exit(1)


def translation_entries(po: polib.POFile):
    """
    returns {filepath: [{"file_index": index_in_file, "po_index": index_in_po}] }
    does not include female entries, as they don't have occurences
    """
    entries = {}
    i = 0
    for entry in po:
        for eo in entry.occurrences:
            path = eo[0]
            linenum = eo[1]
            if path in entries:
                entries[path].append({"file_index": int(linenum), "po_index": i})
            else:
                entries[path] = [{"file_index": int(linenum), "po_index": i}]
        i = i + 1
    return entries


def female_entries(po: polib.POFile) -> "dict[str: polib.POEntry]":
    """
    Returns mapping of male msgids to corresponding female PO entries
    """
    entries = {}
    fe_list = [e for e in po if len(e.occurrences) == 0 and e.msgctxt == CONTEXT_FEMALE]
    for fe in fe_list:
        # first, check male entries without context
        male_entries = [e for e in po if e.msgid == fe.msgid and not e.msgctxt]
        if len(male_entries) > 0:
            me = male_entries[0]
        else:  # then, those with
            male_entries = [e for e in po if e.msgid == fe.msgid and e.msgctxt != CONTEXT_FEMALE]
        try:
            me = male_entries[0]
            entries[me.msgid] = fe
        except:
            print("WARNING: couldn't find a corresponding male counterpart for a female entry")
            print(fe)
    return entries


def po2file(
    po: polib.POFile,
    output_file: str,
    encoding: str,
    occurrence_path: str,
    dst_dir=None,
    trans_map=None,
    female_map=None,
):
    """
    Extract and write to disk a single file from POFile
    output_file is path relative to dst_dir
    dst_dir is actually dst language. Used only in unpoify
    """
    if trans_map is None:  # when extracting single file with po2tra/po2msg, etc
        # check if file is present in po, exit if not
        check_path_in_po(po, occurrence_path)
        trans_map = translation_entries(po)
    if female_map is None:
        female_map = female_entries(po)

    # create parent directory
    create_dir(get_dir(output_file))

    ext = get_ext(output_file)
    ff = FILE_FORMAT[ext]
    line_format = ff["line_format"]

    context = ""
    resulting_entries = []
    extract_fuzzy = CONFIG.extract_fuzzy

    for file_trans in trans_map[occurrence_path]:
        file_index = file_trans["file_index"]
        po_index = file_trans["po_index"]
        entry = po[po_index]

        if entry.msgstr == "":  # if not translated, keep msgid
            value = entry.msgid
        elif "fuzzy" in entry.flags and not extract_fuzzy:  # skip fuzzy?
            value = entry.msgid
        else:
            value = entry.msgstr  # either translated or fuzzy+extract_fuzzy

        # empty lines detected by comment
        if entry.comment == EMPTY_COMMENT:
            value = ""

        # context
        context = entry.msgctxt

        # female strings
        female = None
        if entry.msgid in female_map:
            fe_entry = female_map[entry.msgid]
            if fe_entry.msgstr == "":
                female = fe_entry.msgid
            elif "fuzzy" in fe_entry.flags and not extract_fuzzy:
                female = fe_entry.msgid
            else:
                female = fe_entry.msgstr

        resulting_entries.append({"index": file_index, "value": value, "female": female, "context": context})

    # combined occurrences may mess up order, restoring
    resulting_entries = sorted(resulting_entries, key=lambda k: k["index"])

    lines = []
    lines_female = []

    for res in resulting_entries:
        # get line format
        lfrm = get_line_format(res, ext)

        # add line to common/male package
        line = lfrm.format(index=res["index"], value=res["value"], context=res["context"], female=res["female"])
        # TODO: get rid of replace, handle improper characters in weblate
        lines.append(line.encode(encoding, "replace").decode(encoding))

        # add string to female package if needed
        if "female" in line_format and line_format["female"] == "separate":
            if res["female"] is not None:
                female_line = lfrm.format(index=res["index"], value=res["female"], context=res["context"])
            else:
                female_line = lfrm.format(index=res["index"], value=res["value"], context=res["context"])
            lines_female.append(female_line.encode(encoding, "replace").decode(encoding))

    # write main package
    with open(output_file, "w", encoding=encoding, newline=CONFIG.newline) as file:
        file.writelines(lines)

    # explicitly disabled female?
    no_female = CONFIG.no_female

    if ("female" in line_format) and line_format["female"] == "separate" and dst_dir is not None and not no_female:
        # are translations the same? If yes, skipping copying "dialog" in sfall
        same = False
        if lines_female == lines:
            same = True
        # what's out path?
        female_file = get_female_filepath(output_file, dst_dir, same)

        if female_file is False:  # don't need to copy, automatic fallback
            print("  Female strings are same, not copying - sfall will fallback to male {}".format(output_file))
            return True  # cutoff the rest of the function

        # If need to create the file
        if same:  # if female translation is the same?
            print("  Female strings are same, copying to {}".format(female_file))
            copycreate(output_file, female_file)
        else:  # if it's different, extract separately
            print("  Also extracting female counterpart into {}".format(female_file))
            create_dir(get_dir(female_file))  # create dir if not exists
            with open(female_file, "w", encoding=encoding, newline=CONFIG.newline) as file2:
                file2.writelines(lines_female)


# nasty hack for sfall's female strings placement
def get_female_filepath(path: str, dst_dir: str, same: bool = True):
    # default: just add _female suffix
    female_path = path.replace(dst_dir + os.sep, dst_dir + CONFIG.female_dir_suffix + os.sep)
    if CONFIG.extract_format == "sfall":
        female_path = False  # default for sfall: don't copy, it will fallback to male
        if "cuts" in path.split(os.sep):  # cuts dont' fallback
            female_path = path.replace(os.sep + "cuts" + os.sep, os.sep + "cuts_female" + os.sep)
        if "dialog" in path.split(os.sep) and not same:  # dialog, female translation differs
            female_path = path.replace(os.sep + "dialog" + os.sep, os.sep + "dialog_female" + os.sep)
    return female_path


def get_line_format(e, ext: str):
    """
    Takes translation entry in format {'index': index, 'value': value, 'female': female, 'context': context}
    And file extension
    Returns corresponding string with placeholders from line_format
    """
    ff = FILE_FORMAT[ext]
    line_format = ff["line_format"]
    if e["context"] is not None:  # entry with context
        lfrm = line_format["context"]
    elif (
        "female" in e and e["female"] is not None and "female" in line_format and line_format["female"] != "separate"
    ):  # format with native support for female strings
        lfrm = line_format["female"]
    else:  # no context and no female, or format without native support for female strings
        lfrm = line_format["default"]
    return lfrm


def copycreate(src_file, dst_file):
    dirname = os.path.dirname(dst_file)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    shutil.copyfile(src_file, dst_file)


def file2msgstr(
    input_file: str, po: polib.POFile, path: str, encoding=CONFIG.encoding, overwrite: bool = True, same: bool = False
):
    """returns PO file object"""

    trans = TRANSFile(filepath=input_file, is_source=False, encoding=encoding)  # load translations

    # map entries to occurrences for faster access, part 1
    entries_dict = OrderedDict()
    for e in po:
        for eo in e.occurrences:
            entries_dict[(eo[0], eo[1])] = e
    female_map = female_entries(po)

    for t in trans.entries:
        index = t.index
        value = t.value
        context = t.context
        female_value = t.female

        if (value is None) or (value == ""):
            print("WARN: no msgid found for {}:{}, skipping string\n      {}".format(path, index, value))
            continue

        if (path, index) in entries_dict:
            # map entries to occurrences for faster access, part 2
            e = entries_dict[(path, index)]

            # female entries have no occurences
            if female_value and e.msgid in female_map:
                fe: polib.POEntry = female_map[e.msgid]
                if fe and (fe.msgstr != female_value):
                    print("INFO: female translation change detected:")
                    print("  ORIG: {}".format(e.msgid))
                    print("  OLD:  {}".format(fe.msgstr))
                    print("  NEW: {}".format(female_value))
                    skip = False
                    if not overwrite:
                        print("  Female translation already exists, overwrite disabled, skipping")
                        skip = True
                    if not skip and (e.msgid == female_value):
                        if same:
                            print("INFO: source and female translation are the same. Using it regardless.")
                            print("   {}".format(e.msgid))
                            print("   {}".format(female_value))
                        else:
                            print(
                                "INFO: source and female translation are the same for {}. Skipping:".format(
                                    e.occurrences
                                )
                            )
                            print("   {}".format(e.msgid))
                            print("   {}".format(female_value))
                            skip = True
                    if not skip:
                        fe.msgstr = female_value
                        if "fuzzy" in fe.flags:
                            print("    Unfuzzied female entry")
                            fe.flags.remove("fuzzy")

            # translation is the same
            if e.msgstr == value and e.msgctxt == context:
                continue

            # translation is the same as source
            if e.msgid == value and not same:
                print("INFO: string and new translation are the same for {}. Skipping:".format(e.occurrences))
                print("   {}".format(e.msgid))
                continue

            # if translation already exists and different
            if e.msgstr is not None and e.msgstr != "" and e.msgstr != value:
                # if overwrite is disabled, cutoff
                if not overwrite:
                    print(
                        "INFO: translation already exists for {}, overwrite disabled, skipping:".format(e.occurrences)
                    )
                    continue

            # finally, all checks passed
            print("INFO: translation update found for {}.".format(e.occurrences))
            print("  Replacing old string with new:")
            print("    ORIG: {}".format(e.msgid))
            print("    OLD:  {}".format(e.msgstr))
            print("    NEW:  {}".format(value))
            e.msgstr = value
            e.msgctxt = context
            if "fuzzy" in e.flags:
                print("    Unfuzzied entry")
                e.flags.remove("fuzzy")

    return po


# check if TXT file is indexed
def is_indexed(txt_filename: str, encoding=CONFIG.encoding):
    f = open(txt_filename, "r", encoding=encoding)
    # count non-empty lines
    num_lines = sum(1 for line in f if line.rstrip())
    f.close()

    # count lines that are indexed
    pattern = FILE_FORMAT["txt"]["pattern"]
    f = open(txt_filename, "r", encoding=encoding)
    text = f.read()
    indexed_lines = re.findall(pattern, text)
    num_indexed_lines = len(indexed_lines)
    f.close()
    if num_lines == num_indexed_lines:
        return True
    else:
        return False


def sort_po(po: polib.POFile):
    for e in po:
        e.occurrences = natsorted(e.occurrences, key=lambda k: (k[0], k[1]))
    metadata = po.metadata
    po = natsorted(
        po, key=lambda k: k.occurrences[0] if len(k.occurrences) > 0 else ("zzzzz", "99999")
    )  # female empty occurences hack
    po2 = polib.POFile()
    po2.metadata = metadata
    po2.extend(po)
    return po2


def po_make_unique(po):
    entries_dict = OrderedDict()
    old_metadata = po.metadata
    for e in po:
        if (e.msgid, e.msgctxt) in entries_dict:

            e0 = entries_dict[(e.msgid, e.msgctxt)]
            e0.occurrences.extend(e.occurrences)

            if e.comment is not None:
                if e0.comment is None:
                    e0.comment = e.comment
                elif e0.comment != e.comment:
                    e0.comment = e0.comment + "; " + e.comment

            if e.tcomment is not None:
                if e0.tcomment is None:
                    e0.tcomment = e.tcomment
                elif e0.tcomment != e.tcomment:
                    e0.tcomment = e0.tcomment + "; " + e.tcomment

            for f in e.flags:
                if f not in e0.flags:
                    e0.flags.append(f)

            if e.previous_msgctxt and not e0.previous_msgctxt:
                e0.previous_msgctxt = e.previous_msgctxt
            if e.previous_msgid and not e0.previous_msgid:
                e0.previous_msgid = e.previous_msgid
            if e.previous_msgid_plural and not e0.previous_msgid_plural:
                e0.previous_msgid_plural = e.previous_msgid_plural

        else:
            entries_dict[(e.msgid, e.msgctxt)] = e
    po2 = polib.POFile()
    po2.metadata = old_metadata
    for key, value in list(entries_dict.items()):
        po2.append(value)
    return po2


class TRANSEntry:
    def __init__(self):
        self.index = None
        self.value = None
        self.context = None
        self.female = None
        self.comment = None


class TRANSFile:
    """
    Common translation class, holding translation entries of a single file
    is_source: if set, adds EMPTY_COMMENT to all empty lines
    This is because PO gettext format doesn't tolerate empty msgids
    """

    def __init__(self, filepath: str, is_source: False, encoding=CONFIG.encoding):
        self.entries: list[TRANSEntry] = []
        self.encoding = encoding
        fext = get_ext(filepath)
        self.fformat = FILE_FORMAT[fext]
        self.pattern = self.fformat["pattern"]
        self.dotall = self.fformat["dotall"]

        try:  # comment for all entries in file
            self.comment = self.fformat["comment"]
        except:
            pass

        self.lines = self.load_lines(filepath)

        # enabled for file2msgstr, disabled for file2po
        if not is_source:
            self.lines_female = None
            if self.fformat["line_format"]["female"] == "separate":
                female_dir = get_dir(filepath) + CONFIG.female_dir_suffix
                female_file = os.path.join(female_dir, basename(filepath))
                print("  separate file format, looking for female file {}... ".format(female_file), end="")
                if os.path.isfile(female_file):
                    print("found")
                    self.lines_female = self.load_lines(female_file)
                else:
                    print("didn't find")
            if self.lines_female and self.lines_female == self.lines:
                print("  female lines are identical")
            else:
                print("  female lines are different")

        # protection again duplicate indexes, part 1
        seen = []

        for line in self.lines:
            entry = TRANSEntry()

            # index and value
            index = line[self.fformat["index"]]
            entry.value = str(line[self.fformat["value"]])

            # skip invalid '000' entries in MSG files
            if fext == "msg" and index == "000":
                print(
                    "WARN: {} - invalid entry number found, skipping:\n     {{000}}{{}}{{{}}}".format(
                        filepath, entry.value
                    )
                )
                continue

            entry.index = line[self.fformat["index"]]

            # comment
            # 1. generic comment for all entries in file
            try:
                entry.comment = self.fformat["comment"]
            except:
                pass
            # 2. handle empty lines in source files
            if entry.value == "":
                if is_source is True:
                    entry.value = " "
                    entry.comment = EMPTY_COMMENT

            # context
            try:
                entry.context = line[self.fformat["context"]]
            except:
                pass
            if entry.context == "":
                entry.context = None

            # female
            if fext == "tra":  # TRA file specific
                try:
                    entry.female = str(line[self.fformat["female"]])
                except:
                    pass
                if entry.female == "":
                    entry.female = None

                if entry.female and entry.context:
                    print("ERROR. TRA strings with female variants may not have context.")
                    print(line)
                    print(entry)
                    sys.exit(1)

            # sfall female extraction
            if not is_source and self.lines_female and not (self.lines_female == self.lines):
                try:
                    female_line = [fl for fl in self.lines_female if fl[self.fformat["index"]] == entry.index][0]
                    entry.female = str(female_line[self.fformat["value"]])
                    if entry.female != entry.value:
                        print("  found alternative female string for line {}: {}".format(entry.index, entry.female))
                except:
                    pass

            # protection against duplicate indexes, part 2
            if entry.index in seen:
                print(
                    "WARN: duplicate string definition found {}:{}, using new value:\n      {}".format(
                        filepath, entry.index, entry.value
                    )
                )
                self.entries = [entry if x.index == entry.index else x for x in self.entries]
                continue
            else:
                seen.append(index)

            # produce the final list of strings
            if entry.value is not None and entry.value != "":
                self.entries.append(entry)

    def load_lines(self, filepath: str):
        with open(filepath, "r", encoding=self.encoding) as fh:
            text = fh.read()
            if self.dotall:
                lines = re.findall(self.pattern, text, re.DOTALL)
            else:
                lines = re.findall(self.pattern, text)
        return lines


def simple_lang_slug(po_filename):
    """
    Allows to extract PO files into simplified language names: pt_BR.po -> portuguese/1.msg.
    Working with language codes is not convenient in mods.
    A temporary hack until a better solution is found.
    """
    slug_map = {
        "de": "german",
        "fr": "french",
        "pt_br": "portuguese",
        "it": "italian",
        "pl": "polish",
        "es": "spanish",
        "ru": "russian",
        "uk": "ukrainian",
    }
    slug = strip_ext(po_filename).lower()
    if CONFIG.simple_languages:
        try:
            slug = slug_map[slug]
        except:
            pass
    return slug


def restore_female_entries(po: polib.POFile):
    """
    Unobsoletes and if necessary (un)fuzzies female strings that have a corresponding male counterpart.
    (Male = no context)
    """
    male_entries = {x.msgid: x for x in po if not x.previous_msgid and (x.msgctxt != CONTEXT_FEMALE)}
    fuzzy_male_entries = {x.previous_msgid: x for x in po if x.previous_msgid and (x.msgctxt != CONTEXT_FEMALE)}
    for e in po.obsolete_entries():
        if e.msgctxt != CONTEXT_FEMALE:
            continue

        # if exact male match found, unobsolete
        if e.msgid in male_entries:
            male_entry = male_entries[e.msgid]
            # if it's fuzzy, doing the same for female
            e.previous_msgid = male_entry.previous_msgid
            e.flags = male_entry.flags
            e.obsolete = False

        # if a fuzzy male string was found, fixing female to have the same attributes
        if (e.msgid not in male_entries) and (e.msgid in fuzzy_male_entries):
            male_entry = fuzzy_male_entries[e.msgid]
            e.msgid = male_entry.msgid
            e.previous_msgid = male_entry.previous_msgid
            if "fuzzy" not in e.flags:
                e.flags.append("fuzzy")
            e.obsolete = False
    return po