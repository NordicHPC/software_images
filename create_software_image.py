#!/usr/bin/env python2

# This script creates an ext4 fs image that contains the software module files.
#
# Input: module name, e.g., matlab-R2014b
#
# Output: image file located in cluster/software/IMAGES, e.g., /cluster/software/IMAGES/matlab/R2014b.ext4
#
# 1. calculate the space needed for the files (size of directory contents * oversize factor)
# 2. create empty image file in <workdir>
# 3. create ext4 fs in the file
# 4. mount the file in a temporary directory over loopback
# 5. rsync the source directory to the loop-mounted image
# 6. unmount the image
# 7. move the image to /cluster/software/IMAGES/<module_name>/<module_version>.ext4

import os
import sys
import subprocess
import shutil
import argparse
import math
import tempfile
from filefs import filefs

from hpcmodules import *
from get_dir_size import get_dir_size

# MB
MB = 1024*1024

# space for the image filesystem:
# Image size = oversize * space in bytes required for the files
oversize = 1.3
# give some slack to small modules - often fail to install with small oversize
oversize_small = 3


if __name__ == '__main__':

    # parse arguments
    parser = argparse.ArgumentParser(description="Package and deploy a software module.")
    parser.add_argument("module_name", help="Name of the module to deploy (installed software must reside in " + mount_path + "/<module_name>/<module_version>)")
    parser.add_argument("module_version", help="Name of the module to deploy (installed software must reside in " + mount_path + "/<module_name>/<module_version>)")
    parser.add_argument("-f", "--overwrite", help="Overwrite existing image file [default: False].", default=False, action="store_true")
    parser.add_argument("--oversize", help="Image size = oversize * space in bytes required for the files [default: " + str(oversize) + "]", default=oversize)
    parser.add_argument("--workdir", help="Temporary location where to create the image. A finished imaged will be moved to " + image_path + "/<module_name>/<module_version>.ext4 [default: /cluster/tmp]", default='/cluster/tmp')
    args = parser.parse_args()
    oversize = float(args.oversize)
    args.module_name = args.module_name + '/' + args.module_version

    try:

        # check if directory with software exists
        origpath = get_mount_path(args.module_name)
        if not os.path.isdir(origpath):
            raise ModuleException(args.module_name + " is not available in " + mount_path)
        print(" --- mount point for this module: " + origpath)

        # check if image file exists
        image_name = get_image_name(args.module_name)
        if os.path.isfile(image_name) and not args.overwrite:
            raise ModuleException(image_name + " exists, bailing out. Use --overwrite.")

        # find the size (in MB)
        print(" --- estimating module space requirements")
        size = get_dir_size(origpath)
        if size < 20*MB:
            size = int(math.ceil(float(oversize_small * size) / MB))
        else:
            size = int(math.ceil(float(oversize * size) / MB))
        print(" --- creating disk image of size: " + str(size) + "MB")
        if size == 0:
            raise ModuleException("module empty, bailing out.")

        # create file system image in a temporary location
        final_image_name = image_name
        (fd, image_name) = tempfile.mkstemp('', 'tmp', args.workdir)
        os.close(fd)
        print(" --- building image at " + image_name)
        try:
            filefs(size, image_name)
        except:
            raise ModuleException("while creating image: " + str(sys.exc_info()[1]))

        # mount the image in a temporary place
        try:
            tempdir = tempfile.mkdtemp()
            cmd = ['/bin/mount', '-o', 'loop,rw', image_name, tempdir]
            p1 = subprocess.Popen(cmd)
            p1.wait()
            if p1.returncode:
                raise ModuleException("mount failed with " + str(p.returncode))

        except ModuleException:
            print(str(sys.exc_info()[1]))
            print(" --- removing BAD IMAGE " + image_name)
            os.remove(image_name)
            raise ModuleException("while mounting image: " + str(sys.exc_info()[1]))

        # assume we failed to produce a valid image, bad images are removed at the end
        image_ok = False

        # rsync - copy tree
        try:
            print(" --- copy module files into the image using rsync")
            cmd = ["rsync", "-av", origpath + "/", tempdir]
            p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            for line in iter(p1.stdout.readline, b''):
                sys.stdout.write(line.decode("utf-8"))

            p1.wait()
            if not p1.returncode:
                print(" --- rsync completed with SUCCESS")
                image_ok = True
            else:
                raise ModuleException("rsync returned with " + str(p.returncode))

        except:
            print(" --- trying to clean up...")

        #  unmount the image, remove temporary directory
        try:
            cmd = ['/bin/umount', tempdir]
            p1 = subprocess.Popen(cmd)
            p1.wait()
            if p1.returncode:
                raise ModuleException("umount failed with " + str(p.returncode))

            os.rmdir(tempdir)
        except ModuleException:
            print(str(sys.exc_info()[1]))
            print(" --- WARNING: image not unmounted and/or removed. Manual cleanup needed.")

        if not image_ok:
            print(" --- removing BAD IMAGE " + image_name)
            os.remove(image_name)
            raise ModuleException("deployment failed.")

        # move the temporary image into its final location
        # might need to create the destination directory
        path = os.path.dirname(final_image_name)
        if not os.path.isdir(path):
            print(" --- create directory " + path)
            os.makedirs(path)
        print(" --- move temporary image " + image_name + " to " + final_image_name)
        shutil.move(image_name, final_image_name)
        print(" --- Successfully created module image at " + final_image_name)

    except ModuleException:
        print(str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
