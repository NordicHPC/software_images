#!/usr/bin/env python2.6

import argparse
import subprocess
from hpcmodules import ModuleException


def filefs(size, name):
    print(" --- creating a " + str(size) + "MB sparse file filled with zeros")
    with open(name, 'wb+') as f:
        f.truncate(size*1024*1024)

    print(" --- creating an ext4 file system in file " + name)
    cmd = ["/sbin/mkfs", "-t", "ext4", "-T", "small", name]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    p.communicate(b"y\n")
    p.wait()
    if p.returncode:
        raise ModuleException("mkfs failed")

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Create a file system in a file.")
    parser.add_argument("size", help="Size of the file system [MB].")
    parser.add_argument("file_name", help="Name of the file in which fs will be created.")
    args = parser.parse_args()

    try:
        filefs(int(args.size), args.file_name)
    except ModuleException:
        print(str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
