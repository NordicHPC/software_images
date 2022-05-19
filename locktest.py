#!/usr/bin/env python2.6

import argparse
import time
from hpcmodules import fs_lock_file, local_lock_images

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Test parallel fs locks.")
    parser.add_argument("fname", help="file name to lock")
    parser.add_argument("--rw", help="rw lock", action='store_true')
    args = parser.parse_args()

    print("locking...")
    with fs_lock_file(args.fname, args.rw) as fd:
    #with local_lock_images() as lock:
        print("done!")
        while True:
            time.sleep(1)
            print(".")
