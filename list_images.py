#!/usr/bin/env python2

import argparse
import sys
from hpcmodules import *


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="List all mounted images, or list images loaded by a certain job.")
    parser.add_argument("--job_id", help="job identifier", default="ALL")
    parser.add_argument("--unreported", help="only show mounted images that are not reported in " + local_lock_path + "/*modules", action='store_true')
    args = parser.parse_args()

    if args.unreported:
        if args.job_id != 'ALL':
            print(" --- WARNING: job_id ignored when using --unreported.")

        # look at the used loop devices
        loopdevs = list_loopdevs()

        # get all mounted images
        images = get_mounted_images()

        cnt = 0
        for (img, mnt, loopdev) in iter(images):

            # check if used by a job
            usage = get_image_usage(img)
            if usage == 0:
                print(img + " is mounted but not used.")
                cnt += 1

            # remove loop device from list of used devices
            idx = [i for i, loop in enumerate(loopdevs) if loop[0] == loopdev]
            idx = idx[0]
            loopdevs = loopdevs[:idx] + loopdevs[idx+1:]

        # remaining loop devices are blocked / used by not our images
        for l in range(0, len(loopdevs)):
            cnt += 1
            print('blocked loop device: ' + loopdevs[l][0] + ' - image ' + loopdevs[l][1])

        if cnt == 0:
            print("No unreported images.")

        exit(0)

    # admin mode: list all images mounted on the compute node
    if args.job_id == "ALL":

        # a list of used loop devices and images names
        loopdevs = list_loopdevs()
        print(" --- used loop devices: ")
        for i, ld in enumerate(loopdevs):
            print(ld[0] + " " + ld[1])
        print("")

        # list mounted images
        images = get_mounted_images()
        print(" --- mounted software images:")
        for (img, mnt, loopdev) in iter(images):
            print(img + " mounted at " + mnt)
        exit(0)

    # job-specific operations: list images loaded by that job
    try:
        print(" --- images used by job " + args.job_id)
        images = get_image_list(args.job_id)
        for m in images:
            if is_image_mounted(m):
                suffix = " (mounted)"
            else:
                suffix = " (ERROR: image reported, but NOT mounted)"
            print(m+suffix)
    except ModuleException:
        print(str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
