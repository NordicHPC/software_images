#!/usr/bin/env python2

# This script creates an ext4 fs image and optionally copies source data into it
#
# 1. calculate the space needed for the files (size of directory contents * oversize factor), or take user parameter
# 2. create empty image file at user specified location
# 3. create ext4 fs in the file
# 4. if source given, mount the file in a temporary directory under /var/run/user_images/$(username) over loopback
# 5. rsync the source directory to the loop-mounted image
# 6. unmount the image

import os
import sys
import subprocess
import argparse
import math
import tempfile

from hpcmodules import get_mount_path, ModuleException, fs_lock_file
from filefs import filefs
from get_dir_size import get_dir_size

# MB
MB = 1024*1024

# space for the image filesystem:
# Image size = oversize * space in bytes required for the files
oversize = 1.3
# give some slack to small modules - often fail to install with small oversize
oversize_small = 3

# image mount / umount utilities are executed using sudo
utils_path = os.path.split(os.path.realpath(__file__))[0]
mount_prog = os.path.join(utils_path, 'mount_image')
umount_prog = os.path.join(utils_path, 'umount_image')

def remove_bad_image(image_name):
    if os.path.isfile(image_name):
        try:
            print(" --- removing BAD IMAGE " + image_name)
            os.remove(image_name)
        except:
            print('could not remove image: ' + sys.exc_info()[1])

    if os.path.isfile(image_name + '.lock'):
        try:
            os.remove(image_name + '.lock')
        except:
            print('could not remove image lock file: ' + sys.exc_info()[1])

if __name__ == '__main__':

    # parse arguments
    parser = argparse.ArgumentParser(description="Create a disk image, optionally populate it with data.")
    parser.add_argument("image_name", help="Name of the disk image file, with path.")
    parser.add_argument("src", help="Directory, contents of which to copy into the image.", nargs='?', default=None)
    parser.add_argument("-f", "--overwrite", help="Overwrite existing image file [default: False].", default=False, action="store_true")
    parser.add_argument("-s", "--size", help="Size of the disk image (in MB), if src is not given.", default=None)
    parser.add_argument("--oversize", help="Image size = oversize * space in bytes required for the files in src [default: " + str(oversize) + "]", default=oversize)
    args = parser.parse_args()
    oversize = float(args.oversize)

    try:

        # check if image file exists
        image_name = os.path.abspath(args.image_name)
        print(" --- creating disk image at " + image_name)
        if os.path.isfile(image_name) and not args.overwrite:
            raise ModuleException(image_name + " exists, bailing out. Use --overwrite.")

        # find the image size (in MB)
        if args.src is not None:

            args.src = os.path.abspath(args.src)
            print(" --- estimating module space requirements for source data at " + args.src)

            size = get_dir_size(args.src)
            if size < 20*MB:
                size = int(math.ceil(float(oversize_small * size) / MB))
            else:
                size = int(math.ceil(float(oversize * size) / MB))
            if size == 0:
                raise ModuleException("src directory contains no data. Cannot create empty disk image, bailing out.")
        elif args.size is not None:
            size = args.size
        else:
            raise ModuleException("Unknown image size. You must specify either --size, or source data to copy into the image.")
        size = int(size)

        # create file system image and the corresponding lock file
        try:
            filefs(size, image_name)
            with fs_lock_file(image_name + '.lock', True) as fd:
                # lock the image file to trigger creation of the lock file. Otherwise, the lock file will be created in
                # (u)mount_image with root ownership
                pass
        except:
            remove_bad_image(image_name)
            raise ModuleException("while creating image: " + str(sys.exc_info()[1]))

        # copy source data, if requested
        if args.src is not None:

            # mount the image in a temporary directory
            try:

                # mount point will be created in mount_image, if it does not exist
                mntpoint = get_mount_path()
                if os.path.isdir(mntpoint):
                    tempdir = tempfile.mkdtemp(dir=mntpoint)
                else:
                    tempdir = os.path.join(mntpoint, 'temp')

                # mount must be done with root privileges
                cmd = ['sudo', mount_prog, '--rw', image_name, tempdir]
                p1 = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                p1.wait()
                if p1.returncode:
                    msg = p1.stdout.read().replace('\n', '')
                    raise ModuleException(msg)
            except:
                remove_bad_image(image_name)
                raise ModuleException("while mounting image: " + str(sys.exc_info()[1]))

            # assume we failed to produce a valid image, bad images are removed at the end
            image_ok = False

            # rsync - copy tree
            try:
                print(" --- copy source files into the image using rsync")
                cmd = ["rsync", "-av", args.src + "/", tempdir]
                p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                for line in iter(p1.stdout.readline, b''):
                    sys.stdout.write(line.decode())

                p1.wait()
                if not p1.returncode:
                    print(" --- rsync completed with SUCCESS")
                    image_ok = True
                else:
                    raise ModuleException("rsync returned with " + str(p1.returncode))

            except:
                print(" --- failed to rsync, trying to clean up...")

            #  unmount the image, remove temporary directory
            try:

                # umount must be done with root privileges
                print(' --- unmounting image at ' + tempdir)
                cmd = ['sudo', umount_prog, image_name, tempdir]
                p1 = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                p1.wait()
                if p1.returncode:
                    msg = p1.stdout.read().replace('\n', '')
                    raise ModuleException(msg)

                print(' --- removing temporary directory ' + tempdir)
                os.rmdir(tempdir)
            except ModuleException:
                print(str(sys.exc_info()[1]))
                print(" --- WARNING: image not unmounted and/or removed. Manual cleanup needed.")

            if not image_ok:
                remove_bad_image(image_name)
                raise ModuleException("deployment failed.")

        print('')
        print('The image has been created. You can mount with')
        print('')
        print('sudo mount_image ' + image_name + ' ' + os.path.join(get_mount_path(), 'some_directory'))
        print('')

    except ModuleException:
        print(str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
