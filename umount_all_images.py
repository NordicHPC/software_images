#!/usr/bin/env python2

import argparse
import sys
import socket
from umount_image import umount_image
from cleanup_images import cleanup_images
import hpcmodules
from hpcmodules import *


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Unmount all mounted images, or unmount images loaded by a certain job.")
    parser.add_argument("--job_id", help="job identifier [default=ALL].", default="ALL")
    parser.add_argument("--cleanup", help="detatch used loop devices that are not mounted as images.", action='store_true')
    parser.add_argument("--kill", help="kill processes that use the unmounted loop devices. Requires --cleanup.", action='store_true')
    args = parser.parse_args()

    hpcmodules.gl_job_id = args.job_id
    try:

        if args.job_id == "ALL":

            # admin mode
            print(" --- forcing unmount of all mounted images on host " + socket.gethostname())
            images = get_mounted_images(False)
        else:

            # SLURM epilogue mode: get all images mounted by a job
            images = set(get_image_list(args.job_id))

        print(args.job_id + " --- unmounting images: " + " ".join(images))

        # Remove the images file for this job (or ALL jobs):
        # get_image_usage will not report those images, hence umount_all_images will not report 'still used' error
        # If we fail to unmount an image later, this will be reported by monitoring software as inconsistency:
        # image is mounted, but not reported as used
        clear_image_usage(args.job_id)

        # iterate over unique module names
        for imagename in images:

            try:
                try:
                    # try to treat as a module
                    img = get_module_name(imagename)
                    mnt = None
                except:
                    # it is a user image
                    img = imagename
                    mnt = get_image_mount_point(imagename)

                umount_image(img, mnt, args.job_id)
            except:
                # failed to clean-up after this module, try next one
                # could be due to a network error when releasing the global module usage lock, but the image
                # has been unmounted anyway
                print(args.job_id + str(sys.exc_info()[1]))

        # perform cleanup actions, look for blocked loop devices
        cleanup_images(args.cleanup, args.kill)

    except ModuleException:
        print(args.job_id + str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
