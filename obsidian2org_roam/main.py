#!/usr/bin/python
import sqlite3
import argparse
import os
import pathlib
import re
import hashlib
import subprocess

OBSIDIAN_DIR = ""
OUTPUT_DIR = ""

def sha256(string):
    return hashlib.sha256(bytes(string, "utf-8")).hexdigest()

def create_table(folderpath: str):
    # Get the cursor and check if the database alredy exists
    name = folderpath.split("/")[-1]
    con = sqlite3.connect(f"{name}.db")
    cur = con.cursor()
    res = cur.execute("SELECT name FROM sqlite_master where name='nodes'")
    fetch = res.fetchone()
    if fetch is None:
        cur.execute( "CREATE TABLE 'nodes' (id VARCHAR PRIMARY KEY, name VARCHAR UNIQUE, title VARCHAR)")
        cur.execute( "CREATE TABLE 'links' (id VARCHAR PRIMARY KEY, source VARCHAR, target VARCHAR)")
    else:
        cur.execute(f"DROP TABLE nodes")
        cur.execute(f"DROP TABLE links")
        cur.execute( "CREATE TABLE 'nodes' (id, name, title)")
        cur.execute( "CREATE TABLE 'links' (id, source, target)")
    return con, cur


def walk_dir(path, files=None):
    if files is None:
        files = {}
    for name in os.listdir(path):
        abs_name = os.path.join(path, name)
        if os.path.isfile(abs_name) and pathlib.Path(abs_name).suffix == ".md":
            rel_path = pathlib.Path(abs_name).relative_to(OBSIDIAN_DIR)
            rel_path = str(rel_path).rsplit(".", 1)[0]
            files[rel_path] = sha256(abs_name)
        elif os.path.isdir(abs_name) and "." not in name and name not in "templates":
                folder_dest = pathlib.Path(abs_name).relative_to(OBSIDIAN_DIR)
                folder_dest = OUTPUT_DIR / folder_dest
                os.makedirs(folder_dest, exist_ok=True)
                print(f"Create folder: {folder_dest}")
                walk_dir(abs_name, files)
    return files


def search_relations(files, org_files):
    rlink = re.compile(r"\[\[([A-Za-z0-9\s_./-]+)(?:\|(\w+))?\]\]")
    broken = []
    to_return = []
    for _file in files.keys():
        _file_path = pathlib.Path(os.path.join(OBSIDIAN_DIR, f"{_file}.md"))
        org_path = pathlib.Path(os.path.join(OUTPUT_DIR, _file) + ".org")
        org_content = org_path.read_text(encoding="utf-8")
        with open(_file_path, "r", encoding="utf-8") as open_file:
            content = open_file.read()
        out = rlink.findall(content)
        if len(out) > 0:
            for match in out:
                search = match[0] if ".md" not in match[0] else match[0].split(".md")[0]
                if search in files:
                    fetch = [(search, files[search])]
                else:
                    fetch = [(file, hashval) for file, hashval in files.items() if file.endswith(f"/{search}")] 
                if len(fetch) == 0:
                    broken.append((_file, match[0]))
                    continue
                elif len(fetch) > 1:
                    print(f"Conflict found in file {_file} with link {search}")
                    menu = '\n'.join(f"[{pos}] {file}" for pos, (file, hashval) in enumerate(fetch))
                    val = input(f"Availables options are:\n{menu}")
                    if val.isnumeric():
                        fetch = [fetch[int(val)]]
                to_return.append((files[_file], fetch[0][1]))
                if match[1] != '':
                    org_content = org_content.replace(f"[[{match[0]}|{match[1]}]]", f"[[id:{fetch[0][1]}][{match[1]}]]")
                else:
                    org_content = org_content.replace(f"[[{match[0]}]]", f"[[id:{fetch[0][1]}][{match[0]}]]")
            with open(org_path, "w", encoding="utf-8") as open_file:
                open_file.write(org_content)

    yield from filter(lambda x: x is not None, to_return)


def convert_file(files):
    for file, iden in files.items():
        org_file = pathlib.Path(OUTPUT_DIR) / (file + ".org")
        process = [
            "pandoc",
            "--from=markdown-auto_identifiers",
            "--to=org",
            "--output",
            str(org_file),
            os.path.join(OBSIDIAN_DIR, file) + ".md"
        ]
        return_code = subprocess.run(process)
        if return_code.returncode:
            process2 = ["echo"]
            process2.extend(process)
            subprocess.run(process2)
            print(return_code)
            exit(-1)
        # Get the yaml frontmatter and convert it to org properties
        with open(os.path.join(OBSIDIAN_DIR, file) + ".md", "r", encoding="utf-8") as open_file:
            text = open_file.read()
        properties = {}
        if text.startswith("---"):
            prop = text.split("---", 2)[1]
            if prop:
                # If there is some colon in the properties, it will be changed to a dash
                regex = re.compile(r"((?:- )?\w+):\s*(.*)")
                matches = regex.findall(prop)
                for key, value in matches:
                    properties[key.lower()] = value
                if "title" not in properties:
                    properties["title"] = file.split("/")[-1]
        # add id property to org file
        with open(org_file, "r+", encoding="utf-8") as open_file:
            content = open_file.read()
            open_file.seek(0, 0)
            open_file.write(f":PROPERTIES:\n:ID: {iden}\n")
            if "alias" in properties or "aliases" in properties:
                open_file.write(f":ROAM_ALIAS: {properties.get('alias', properties.get('aliases'))}\n")
            open_file.write(":END:\n")
            for key, value in properties.items():
                if key not in ["alias", "aliases"]:
                    open_file.write(f"#+{key.upper()}: {value}\n")
            open_file.write(content)
        yield org_file


def create(args):
    global OBSIDIAN_DIR
    global OUTPUT_DIR
    if directory is None:
        raise Exception("action 'Create' needs a directory")
    OBSIDIAN_DIR = args.directory
    OUTPUT_DIR = args.output
    con, cur = create_table(args.directory)
    files = walk_dir(args.directory)
    org_files = list(convert_file(files))
    relations = list(search_relations(files, org_files))
    with con:
        cur.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [(identify, path, path.split("/")[0]) for identify, path in files.items()])
        cur.executemany("INSERT INTO links values (?, ?, ?)", [(sha256(f"{source[0]}-{source[1]}"), source[0], source[1] ) for source in relations if source is not None])
    con.close()



def directory(path):
    if not path or not os.path.isdir(path):
        raise argparse.ArgumentTypeError(f"'{path}' is not an existing directory")
    return os.path.abspath(path)

def main():
    parser = argparse.ArgumentParser(description="Script to get a vault in markdown and generate a database with sqlite")
    parser.add_argument("action", choices=["create", "migrate"])
    parser.add_argument("--dir", "-d", type=directory, dest="directory", default=None, required=True)
    parser.add_argument("--output", "-o", type=directory, dest="output", default=None, required=True)
    args = parser.parse_args()
    if args.action == "create":
        create(args)

if __name__ == "__main__":
    main()
