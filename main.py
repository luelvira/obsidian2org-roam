#!/usr/bin/python
import sqlite3
import argparse
import os
import pathlib
import re
import hashlib

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

def walk_dir(path):
    for name in os.listdir(path):
        abs_name = os.path.join(path, name)
        if os.path.isfile(abs_name) and pathlib.Path(abs_name).suffix == ".md":
            yield abs_name
        elif os.path.isdir(abs_name) and "." not in name:
                yield from walk_dir(abs_name)

def search_relations(files, cur):
    rlink = re.compile(r"\[\[([A-Za-z0-9\s_]+)(?:\|(\w+))?\]\]")
    broken = []
    to_return = []
    def search_links(_file, add):
        with open(_file, "r", encoding="utf-8") as open_file:
            content = open_file.read()
            out = rlink.findall(content)
            if len(out) > 0:
                for match in out:
                    res = cur.execute("SELECT id FROM nodes WHERE name = ? or title = ?", (match[0], match[0]))
                    fetch = res.fetchall()
                    if len(fetch) == 0:
                        if add:
                            broken.append((_file, match[0]))
                        print(f" Append {broken[-1]} to broken list")
                    elif len(fetch) > 1:
                        print(f"Conflict found in {_file}")
                        raise Exception()
                    else:
                        print("entra")
                        return sha256(_file), fetch[0][0]
    for _file in files:
        to_return.append(search_links(_file, True))

    for _file in broken:
        to_return.append(search_links(_file[0], False))

    yield from to_return


def create(args):
    if directory is None:
        raise Exception("Create action need a directory")
    con, cur = create_table(args.directory)
    files = list(walk_dir(args.directory))
    relations = list(search_relations(files, cur))
    print(relations)
    exit(0)
    with con:
        cur.executemany("INSERT INTO nodes VALUES (?, ?, ?)", [(sha256(path), path, path.split("/")[0]) for path in files])
        cur.executemany("INSERT INTO links values (?, ?, ?)", [(sha256(f"{source[0]}-{source[1]}"), source[0], source[1] ) for source in relations])
    con.close()



def main(args):
    if args.action == "create":
        create(args)

def directory(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError(f"'{path}' is not an existing directory")
    return os.path.abspath(path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to get a vault in markdown and generate a database with sqlite")
    parser.add_argument("action", choices=["create", "graph"])
    parser.add_argument("--dir", "-d", type=directory, dest="directory", default=None)
    main(parser.parse_args())
