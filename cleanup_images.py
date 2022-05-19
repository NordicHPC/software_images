#!/usr/bin/env python2

import argparse
import sys
from hpcmodules import *
from umount_image import umount_image


def cleanup_images(cleanup=False, kill=False, verbosity=1):

    # get used loop devices
    loopdevs = list_loopdevs()

    # get all mounted images
    images = get_mounted_images()

    for (img, mnt, loopdev) in iter(images):

        # check if used by a job
        usage = get_image_usage(img)
        if usage == 0:
            try:
                # is this a software image?
                module_name = get_module_name(img)
            except:
                # no, it's a user image
                module_name = None

            if module_name is None:
                umount_image(img, mnt)
            else:
                umount_image(module_name)

        # remove loop device from list of used devices
        idx = [i for i, loop in enumerate(loopdevs) if loop[0] == loopdev]
        idx = idx[0]
        loopdevs = loopdevs[:idx] + loopdevs[idx + 1:]

    # remaining loop devices are blocked
    if len(loopdevs):

        # loop devices cleanup
        if not cleanup:
            if verbosity:
                print(' --- WARNING: The following images are attached to loop devices, but not mounted:')

        for l in range(0, len(loopdevs)):
            if not cleanup:
                print(loopdevs[l][0] + ' - attached image ' + loopdevs[l][1])
            else:
                print('deleting blocked loop device: ' + loopdevs[l][0] + ' - attached image ' + loopdevs[l][1])
                try:
                    delete_loopdev(loopdevs[l][0], kill)
                except:
                    print(str(sys.exc_info()[1]))

        if not cleanup:
            if verbosity:
                import inspect
                [dr, sc] = os.path.split(inspect.getfile(inspect.currentframe()))
                print(' --- To detatch the loopback devices, run `' + sc + ' --cleanup`')
                print(' --- To also kill the processes that use them, run `' + sc + ' --cleanup --kill`')


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Cleanup loop-back devices.")
    parser.add_argument("--cleanup", help="Detatch used loop devices that are not mounted as images.", action='store_true')
    parser.add_argument("--kill", help="Kill processes that use the unmounted loop devices. Requires --cleanup.", action='store_true')
    parser.add_argument("--verbosity", help="Print some extra information", default=1)
    args = parser.parse_args()

    try:
        cleanup_images(args.cleanup, args.kill, int(args.verbosity))

    except ModuleException:
        print(str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
