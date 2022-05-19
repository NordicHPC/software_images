import os
import re
import sys
import inspect
import errno
import glob
import stat
import getpass
import pwd
import signal
import fcntl
from os.path import isfile, join
import subprocess
from subprocess import PIPE

# paths: MUST BE without final separator

# software modules settings
# mount point and image location
image_ext = ".ext4"
image_path = os.path.realpath("/cluster/software/IMAGES")
mount_path = os.path.realpath("/cluster/software/")

# user modules mount point
mount_path_usr = os.path.realpath('/var/run/user_images')

# local information about images mounted on a compute node (local fs, NOT network fs)
local_lock_path = os.path.realpath("/var/lock/software_images")

# SLURM job identifier for displaying log messages
gl_job_id = "NOJOBID"


# get the caller function name for error reporting
def debug_get_current_function(level):
    stack = inspect.stack()
    return stack[level][3] + ":" + str(stack[level][2])


# handled exception type
class ModuleException(Exception):
    def __init__(self, value):
        self.value = " --- ERROR in " + debug_get_current_function(1) + " in " + debug_get_current_function(2) + " - " + value

    def __str__(self):
        return str(self.value)


# tricky - on some systems getpass.getuser() does not return the login username
# when using sudo - LOGNAME is set to root. We check SUDO_USER first
def get_login_username():
    su = os.environ.get('SUDO_USER')
    if su is None:
        su = getpass.getuser()
        if su == 'root':
            su = pwd.getpwuid(os.geteuid()).pw_name
    return su


def fs_lock_file(fname, rw, timeout=5):

    mask = os.umask(stat.S_IXUSR | stat.S_IRWXG | stat.S_IRWXO)

    try:

        # Open lock file, create it if doesn't exist.
        # Locking is based on the assumption that the lock file is never removed once created, and all write operations
        # to the lock file are done on the same physical file
        fd = os.open(fname, os.O_RDWR | os.O_CREAT)

        # We know the file is there now, update file permissions just in case.
        # The lock file MUST have 0600 permissions. Only the lock owner may be allowed to lock the file.
        os.chmod(fname, stat.S_IRUSR | stat.S_IWUSR)

        # open lock file
        fdo = os.fdopen(fd, 'r+')

        # obtain a lock with timeout. On beegfs this must be implemented using polling - SIGALRM does not interrupt the
        # flock call. We use SIGALRM only to measure time here.

        global retry
        retry = True
        locked = False
        def timeout_handler(signum, frame):
            global retry
            retry = False

        original_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

        # call a non-blocking, exclusive flock until locked, or until timed out
        while retry:
            try:
                fcntl.flock(fdo, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                retry = False

            except IOError, err:
                if err.errno != errno.EWOULDBLOCK:
                    raise

            finally:
                if not retry:
                    # restore original signal handler
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, original_handler)

        if not locked:
            raise ModuleException(" Timeout when locking file " + fname)

        # We have the lock. If requesting an rw lock, check the file size. The file MUST be empty to grant an rw lock.
        if rw:
            fdo.seek(0, os.SEEK_END)
            if fdo.tell() != 0:
                fdo.close()
                raise ModuleException(fname + " cannot be RW-locked in exclusive mode: other clients hold the lock.")

    finally:
        # restore umask
        os.umask(mask)

    return fdo


# lock local image information for update
def local_lock_images():

    # create directory if it does not exist
    try:
        os.makedirs(local_lock_path)
        print(" --- create lock directory " + local_lock_path)
    except OSError as err:
        # race - sb created it before us
        import errno
        if err.errno != errno.EEXIST:
            print("Cannot lock modules! Unexpected OSError:", sys.exc_info()[0])
            raise

    return fs_lock_file(os.path.join(local_lock_path, "lockfile"), False)


# internal - mount information per (SLURM) job is stored in this file
def get_job_filename(job_id):
    if job_id=='NOJOBID':
        job_id = get_login_username()
    return join(local_lock_path, str(job_id) + ".modules")


def is_job_owner(job_id):

    job_file = get_job_filename(job_id)
    if not os.path.isfile(job_file):
        # new job file
        return True
    uid = os.lstat(job_file)[4]

    username = get_login_username()
    userinfo = pwd.getpwnam(username)
    if userinfo.pw_uid == uid:
        return True
    else:
        return False


# return a list of all job files present on the compute node
def get_all_job_files():
    try:
        # see if there are any other jobs and their corresponding module files
        return [f for f in glob.glob(join(local_lock_path, "*.modules")) if isfile(join(local_lock_path, f))]

    except OSError:
        # if no job module files, return 0
        err = sys.exc_info()[1]
        if err.errno == errno.ENOENT:
            return []
        else:
            raise


# add image to list of images mounted by a job
def add_image_usage(job_id, imagename):
    filename = get_job_filename(job_id)
    try:
        if not os.path.isdir(local_lock_path):
            print(" --- create directory " + local_lock_path)
            os.makedirs(local_lock_path)

        with open(filename, 'a') as fd:

            # change file ownership to calling user, not root
            # used to establish owndership of jobs (job files)
            username = get_login_username()
            userinfo = pwd.getpwnam(username)
            os.chown(filename, userinfo.pw_uid, userinfo.pw_gid)
            fd.write(imagename + "\n")
    except:
        raise ModuleException("failed to update / create module file " + filename)


# return number of jobs that mount an image
def get_image_usage(imagename):
    modulefiles = get_all_job_files()
    usage = 0
    for f in modulefiles:

        # check if image name is present in that job file
        try:
            with open(f, 'r') as fd:
                lines = fd.readlines()
            usage = usage + any(imagename + "\n" in s for s in lines)
        except:
            print(" --- ERROR reading module information from " + f + ", assuming image " + imagename + " is used.")
            usage = usage + 1

    return usage


# Remove local information about images mounted by a job.
# If imagename is given, only remove info about that image.
# Otherwise remove all information about images mounted by a job.
def clear_image_usage(job_id, imagename=None):

    # Forcefully remove all job module files: admin cleanup.
    # Actual images are not unmounted!
    if job_id == 'ALL':
        modulefiles = get_all_job_files()
        for f in modulefiles:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    print(" --- removed job image information " + f)
            except:
                print(" --- ERROR: failed to remove job image information " + f)
        return

    # remove information about specific job
    filename = get_job_filename(job_id)

    # remove information about a specific module or image
    if imagename is not None:

        # get list of images used by a given job - duplicates removed
        images = get_image_list(job_id)
        images = [m for m in images if m != imagename]

        # save the remaining modules to file and exit
        if len(images):
            try:
                with open(filename, "w") as fd:
                    for m in images:
                        fd.write(m + "\n")
            except:
                raise ModuleException("failed to update / create module file " + filename)

            return

    # remove entire file - empty, or removing all modules
    try:
        if os.path.isfile(filename):
            os.remove(filename)
    except:
        print(" --- ERROR: failed to remove job image information " + filename)


# list of images loaded by a job
def get_image_list(job_id):
    filename = get_job_filename(job_id)
    images = []
    if not os.path.isfile(filename):
        return images

    # read list of used images
    try:
        with open(filename, 'r') as fd:
            lines = fd.readlines()
    except:
        print(" --- ERROR reading image information from " + filename)
        return images

    # strip newline
    images = [l.rstrip() for l in lines]

    return images


# check if an image is mounted
def is_image_mounted(imagename, mntpoint=None):

    # check if file is mounted where it should be by mount | grep imagename | grep mntpoint
    p1 = subprocess.Popen(["/bin/mount"], stdout=PIPE)
    p2 = subprocess.Popen(["/bin/grep", imagename], stdin=p1.stdout, stdout=PIPE)
    if mntpoint is not None:
        mntpoint = os.path.realpath(mntpoint)
        pend = subprocess.Popen(["/bin/grep", mntpoint], stdin=p2.stdout, stdout=PIPE)
    else:
        pend = p2
    stdout = pend.communicate()[0]

    # check if any output at all
    if not len(stdout):
        return False

    # match whole path components
    stdout = re.split("\s+", stdout)
    if stdout[0] != imagename:
        return False
    if mntpoint is not None and stdout[2] != mntpoint:
        return False

    return True


# Admin: get a list of mounted images. Everything mounted under mount_path, or mount_path_usr is returned.
def get_mounted_images(return_details=True):

    p1 = subprocess.Popen(["/bin/mount"], stdout=PIPE)
    p2 = subprocess.Popen(["/bin/grep", mount_path+'\|'+mount_path_usr], stdin=p1.stdout, stdout=PIPE)
    stdout = p2.communicate()[0]
    stdout = stdout.split("\n")

    if len(stdout) == 0:
        return []

    modules = []
    for l in stdout:
        fields = l.split()

        # find the loop device
        if len(fields) == 0:
            continue
        if return_details:
            m = re.search('loop=([^)]*)', fields[len(fields) - 1])
            loopdev = m.group(1)
            modules.append((fields[0], fields[2], loopdev))
        else:
            modules.append(fields[0])

    return modules


# return path under which a given image is mounted
def get_image_mount_point(imagename):

    p1 = subprocess.Popen(["/bin/mount"], stdout=PIPE)
    p2 = subprocess.Popen(["/bin/grep", imagename], stdin=p1.stdout, stdout=PIPE)
    stdout = p2.communicate()[0]
    stdout = stdout.split("\n")

    if len(stdout) == 0:
        return []

    for l in stdout:
        fields = l.split()
        if len(fields) == 0:
            continue

        return fields[2]


# return full image name for a given software module
def get_image_name(modulename):
    verify_module_name(modulename)
    imagename = join(image_path, modulename + image_ext)
    return imagename


# input: valid image in image_path, e.g., /cluster/software/IMAGES/matlab-R2014b.ext4
# output: module name, e.g., matlab-R2014b
def get_module_name(imagename):

    # verify we are dealing with a file
    if not os.path.isfile(imagename):
        raise ModuleException("invalid image: " + imagename)

    imagename = os.path.realpath(imagename)
    if image_path not in imagename:
        raise ModuleException("not a software module: " + imagename)
    idx = imagename.index(image_path)
    if idx != 0:
        raise ModuleException("not a software module: " + imagename)

    modulename = os.path.realpath(imagename)

    # remove suffix : .ext4
    if len(modulename) < 5:
        raise ModuleException("invalid image: " + imagename)
    modulename = modulename[:len(modulename)-5]

    # get all path elements after image_path
    modulename = modulename[len(image_path):]
    if modulename[0] == os.sep:
        modulename = modulename[1:]
    return modulename


# module name can have at most one / indicating (software name / version)
def verify_module_name(modulename):

    # check that the module name does not contain more than two path components
    components = []
    path = modulename
    while 1:
        path, folder = os.path.split(path)

        if folder != "":
            components.append(folder)
        else:
            if path != "":
                components.append(path)
            break
    if len(components) > 2:
        raise ModuleException("invalid module name: " + modulename + " too many path components.")


# return path under which images are allowed to be mounted
# different for user images, and for software modules
def get_mount_path(modulename=None):

    if modulename is not None:
        verify_module_name(modulename)

        # try to remove the path separator - old style modules
        mountpt = join(mount_path, modulename.replace("/", "-"))
        if os.path.isdir(mountpt):
            return mountpt
        return join(mount_path, modulename)

    # return user mount path
    return os.path.join(mount_path_usr, get_login_username())


# verify that the mount point is legal, i.e., inside mount_path (for modules), or mount_path_usr (for user images)
# e.g., /cluster/software/VERSIONS/matlab-R2014b
# or /var/run/user_images/<username>/image1
def verify_mount_path(dname, modulename=None):

    dname = os.path.realpath(dname)
    if modulename is not None:

        # software modules must be mounted under mount_path
        verify_module_name(modulename)

        try:
            idx = dname.index(modulename)
            if not dname[:idx] == mount_path:
                raise ModuleException("mount point not suitable for module " + modulename + ": " + dname)
        except:
            raise ModuleException("mount point not suitable for module " + modulename + ": " + dname)

    else:

        # user images must be mounted under mount_path_usr
        try:
            idx_dir = dname.index(get_mount_path() + os.path.sep)
            if idx_dir != 0:
                raise ModuleException(
                    "mount point " + dname + " not suitable. Valid mount point must be located under " + get_mount_path() + os.path.sep)

        except:
            raise ModuleException("mount point " + dname + " not suitable. Valid mount point must be located under " + get_mount_path() + os.path.sep)


def create_mount_path(dname):

    dname = os.path.realpath(dname)
    verify_mount_path(dname)

    # create mount_path_usr with effective user privileges
    if not os.path.exists(mount_path_usr):
        os.makedirs(mount_path_usr)

    # create the remaining path with login user privileges
    if not os.path.exists(dname):
        os.makedirs(dname)

        # change ownership
        username = get_login_username()
        userinfo = pwd.getpwnam(username)
        while not dname == mount_path_usr:
            os.chown(dname, userinfo.pw_uid, userinfo.pw_gid)
            (dname, tail) = os.path.split(dname)


def list_loopdevs():

    # find all loop devices used by software images
    p1 = subprocess.Popen(["/sbin/losetup", "-a"], stdout=PIPE)
    stdout = p1.communicate()[0]
    stdout = stdout.split("\n")
    if len(stdout) == 0:
        return []

    images = []
    for l in stdout:
        fields = l.split()
        if len(fields) == 0:
            continue
        images.append((fields[0].replace(':', ''), fields[2]))

    return images


def delete_loopdev(loopdev, kill=False):

    # shoot first, ask questions later
    if kill:
        p1 = subprocess.Popen(["/sbin/fuser", "-c", "-k", loopdev], stdout=PIPE, stderr=subprocess.STDOUT)
        p1.wait()
        stdout = p1.communicate()[0]
        if p1.returncode and len(stdout):
            print('fuser returned ' + stdout);

    p1 = subprocess.Popen(["/sbin/losetup", "-d", loopdev], stdout=PIPE, stderr=subprocess.STDOUT)
    p1.wait()
    if p1.returncode:

        # probably sb. is still using the device - kill with fuser
        stdout = p1.communicate()[0]
        raise ModuleException('ERROR: ' + stdout)


def validate_mount_arguments(mntname, mntpoint):

    imagename = None
    modulename = None

    # figure out what is the user trying to mount: user image, or software module
    try:
        # assume mntname is a module name
        imagename = get_image_name(mntname)

        # check that the corresponding image exists
        if not os.path.isfile(imagename):
            raise ModuleException('image file ' + imagename + ' does not exist')

        modulename = mntname
    except:
        # assume mntname is an image name
        pass

    if modulename is not None:
        # when mounting a software module mount point is not accepted
        if mntpoint is not None:
            raise ModuleException('attempting to mount software module ' + modulename + ' at a non-standard location ' + mntpoint)
        mntpoint = get_mount_path(modulename)

    else:
        # trying to mount a user image
        imagename = os.path.abspath(mntname)
        imagename = os.path.realpath(imagename)

        # check that the corresponding image exists
        if not os.path.isfile(imagename):
            raise ModuleException('image file ' + imagename + ' does not exist')

        # imagename could point to a software image - do not allow that
        try:
            modulename = get_module_name(imagename)
        except:
            # not a module name - OK
            pass

        if modulename is not None:
            raise ModuleException('mounting a software module image ' + imagename + ' directly is not allowed.')

        if mntpoint is None:
            raise ModuleException('mount point has to be supplied when mounting ' + imagename)

        # can't mount software images at arbitrary locations
        # verify that user didn't explicitly provide path to a software image
        # create_mount_path verifies if a user is allowed to mount under specified path
        mntpoint = os.path.realpath(mntpoint)
        create_mount_path(mntpoint)

    return imagename, mntpoint, modulename


def set_from_environment(varname, envname):
    try:
        globals()[varname] = os.environ[envname]
    except:
        # not defined - use default
        pass

# module initialization
# set paths
set_from_environment('image_path', 'SI_IMAGE_PATH')
set_from_environment('mount_path', 'SI_MOUNT_PATH')
set_from_environment('mount_path_usr', 'SI_USR_MOUNT_PATH')
set_from_environment('local_lock_path', 'SI_LOCK_PATH')
