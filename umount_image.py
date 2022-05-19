#!/usr/bin/env python2

import sys
import os
import socket
import argparse
import subprocess
from subprocess import *
import hpcmodules
from hpcmodules import *


def umount_image(mntname, mntpoint=None, job_id='NOJOBID'):

    # argument validation: image name / module name, and mount point
    imagename, mntpoint, modulename = validate_mount_arguments(mntname, mntpoint)

    # if a job file exists, make sure the calling user is the job owner
    if not is_job_owner(job_id):
        raise ModuleException(get_login_username() + ": you are not the job owner of job_id " + job_id)

    # lock access to local (per-compute node) image information
    with local_lock_images() as lock:

        # update per-job image usage information
        clear_image_usage(job_id, imagename)

        if not is_image_mounted(imagename, mntpoint):
            # this is not necessarily an error. Happens in this scenario:
            # - load a module (mount image)
            # - start a script. It will see the module as loaded
            # - unload the module from the script (will also unmount the image)
            # - exit the script, go back to original environment. The module is still 'loaded' here. unloading the module
            # attempts to unmount an image, which has already been unmounted in the script - hence the exception.
            raise ModuleException("It seems " + imagename + " is not mounted at " + mntpoint)

        # do not unmount if the image is used by sb. else
        usage = get_image_usage(imagename)
        if usage:
            print(job_id + " --- image " + imagename + " still used by " + str(usage) + " jobs, refusing to unmount.")
            return

        # call the umount process.
        cmd = ["/bin/umount", mntpoint]
        p = subprocess.Popen(cmd, stderr=PIPE)
        stderrdata = p.communicate()[1]
        if p.returncode:

            # do a lazy umount
            stderrdata = stderrdata.split('\n')
            print(job_id + " --- umount on " + mntpoint + " failed: " + stderrdata[0])
            print(job_id + " --- Performing lazy umount")
            cmd = ["/bin/umount", "-l", mntpoint]
            p = subprocess.Popen(cmd, stderr=PIPE)
            p.wait()
        else:
            print(job_id + " --- image " + imagename + " has been unmounted.")

        # remove host info from image lock file
        # if that fails, and the image has in fact been unmounted, this will be reported in monitoring as an inconsistency:
        # an image reported as mounted is in fact not mounted.
        with fs_lock_file(imagename + ".lock", False) as fd:

            # filter out local host name
            fd.seek(0)
            data = fd.readlines()
            data = [line for line in data if socket.gethostname() not in line]

            # truncate the file and write new, filtered data
            fd.truncate(0)
            fd.seek(0)
            if len(data):
                fd.writelines(data)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Unmount a disk image.")
    parser.add_argument("image_name", help="Name of the software module, or path to the mounted disk image file.")
    parser.add_argument("mount_point", help="Mount point under " + hpcmodules.mount_path_usr + '/$USER', nargs='?', default=None)
    parser.add_argument("--job_id", help="job identifier [default $USER].", default="NOJOBID")
    args = parser.parse_args()

    hpcmodules.gl_job_id = args.job_id
    try:
        umount_image(args.image_name, mntpoint=args.mount_point, job_id=args.job_id)
    except ModuleException:
        print(args.job_id + str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
