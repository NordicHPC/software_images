#!/usr/bin/env python2

import sys
import os
import socket
from stat import *
import argparse
import subprocess
from subprocess import *
import pwd
import hpcmodules
from hpcmodules import *


def mount_image(mntname, mntpoint=None, rw=False, job_id='NOJOBID'):

    # argument validation: image name / module name, and mount point
    imagename, mntpoint, modulename = validate_mount_arguments(mntname, mntpoint)

    # make sure user is not trying to mount a software module in RW mode.
    if rw and modulename is not None:
        raise ModuleException('cannot mount a software module ' + modulename + ' in RW mode!')

    # if a job file exists, make sure the calling user is the job owner
    if not is_job_owner(job_id):
        raise ModuleException(get_login_username() + ": you are not the job owner of job_id " + job_id)

    # make sure the image file is not a symlink
    mode = os.lstat(imagename)[ST_MODE]
    if S_ISLNK(mode):
        raise ModuleException("image file " + imagename + " is a symbolic link, refusing to mount")

    # make sure the destination directory is not a symlink
    mode = os.lstat(mntpoint)[ST_MODE]
    if S_ISLNK(mode):
        raise ModuleException("mount point " + mntpoint + " is a symbolic link, refusing to mount")

    # lock access to local (per-compute node) image information
    with local_lock_images() as lock:

        # make sure the destination directory is not a mount point,
        # or that the same image is already mounted there.
        already_mounted = is_image_mounted(imagename, mntpoint)
        if os.path.ismount(mntpoint) and not already_mounted:
            raise ModuleException(mntpoint + " is already used as a mount point for a different image, refusing to mount")

        # Do not check rw mounts: if rw is set, we will get an error later, in fs_lock_file.
        if already_mounted and not rw:

            # Do not mount if image is already mounted. Only update image usage later.
            print(job_id + " --- cannot mount: " + imagename + " is already mounted at " + mntpoint)
        else:
            # next is the global cluster lock - keeps track of used images through a network file system lock file

            # lock the image in desired mode:
            #  RO: check if the image is not already mounted in RW mode. If not, append hostname to lock file and mount
            #  RW: check if the image is not already mounted in any mode. If not, append " rw "+hostname to lock file and mount
            #
            # To obtain an rw lock in fs_lock_file it is required that the lock file is empty,
            # i.e., no other host mounts that image.
            # An ro lock is obtained in fs_lock_file using flock. After that, below we check if the file does not contain
            # " rw ", i.e., the image is mounted in RW mode by someone.
            with fs_lock_file(imagename + ".lock", rw) as fd:

                if rw:
                    # guaranteed that the lock file is empty
                    fd.writelines(" rw ")
                else:
                    # check if not already mounted in RW
                    data = fd.readline()
                    if len(data) >= 4 and (data[0:4] == " rw "):
                        raise ModuleException("failed to mount " + imagename + ", it is already mounted in RW mode by another client: " + data[3:len(data)-1])

                # do mount
                cmd = ["/bin/mount", "-o", "loop,nosuid,nodev", imagename, mntpoint]
                log = job_id + " --- mounting " + imagename + " at " + mntpoint
                if not rw:
                    cmd.append("-o")
                    cmd.append("ro")
                    log += " (RO)"
                else:
                    log += " (RW)"

                p = subprocess.Popen(cmd, stderr=PIPE)
                stderrdata = p.communicate()[1]
                if not p.returncode:

                    # successfully mounted

                    # For RW mounts, change ownership of the mount point to allow the user to write
                    if rw:
                        username = get_login_username()
                        userinfo = pwd.getpwnam(username)
                        os.chown(mntpoint, userinfo.pw_uid, userinfo.pw_gid)

                    # now need to mark the mount in the global database:
                    # store host name in the lock file
                    try:
                        fd.seek(0, os.SEEK_END)
                        fd.write(socket.gethostname() + "\n")
                    except:

                        # If the hostname store fails, the mount must be unmounted!
                        print(log + " : FAILED - cannot write to " + imagename + ".lock. Image will be unmounted.")
                        cmd = ["/bin/umount", mntpoint];
                        p = subprocess.Popen(cmd, stderr=PIPE)
                        stderrdata = p.communicate()[1]
                        if not p.returncode:
                            raise ModuleException("mount failed: unable to write to " + imagename + ".lock")
                        else:
                            raise ModuleException("failed to unmount " + mntpoint + " after failed write to " + imagename + ".lock: "+ stderrdata + ". Manual cleanup required!")

                    print(log + " : SUCCESS ")
                else:
                    raise ModuleException("mount " + imagename + " on " + mntpoint + " failed: " + stderrdata)

        # reality check - if the image is mounted, update per-job usage information
        if is_image_mounted(imagename):
            try:
                add_image_usage(job_id, imagename)
                print(job_id + " --- added image usage, current image usage: " + str(get_image_usage(imagename)) + " jobs.")
            except:
                print(job_id + " --- ERROR adding information about " + imagename + " to local database.")
                raise
        else:
            raise ModuleException('Image ' + image_name + ' not identified as mounted.')


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Mount a disk image.")
    parser.add_argument("image_name", help="name of the software module, or path to disk image file.")
    parser.add_argument("mount_point", help="mount point under " + hpcmodules.mount_path_usr + '/$USER', nargs='?', default=None)
    parser.add_argument("--job_id", help="job identifier [default $USER].", default="NOJOBID")
    parser.add_argument("--rw", help="mount image in read-write mode (only one compute node can do that at a time)", action='store_true')
    args = parser.parse_args()

    hpcmodules.gl_job_id = args.job_id
    try:
        mount_image(args.image_name, rw=args.rw, mntpoint=args.mount_point, job_id=args.job_id)
    except ModuleException:
        print(args.job_id + str(sys.exc_info()[1]))
        exit(1)
    # other exceptions run through
