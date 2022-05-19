import os

# compute disk size needed to store files in a directory tree
def get_dir_size(start_path):

    total_size = 0
    repo_size = 0
    blsize = 1024

    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                sz = os.lstat(fp).st_size
                repo_size += sz
                total_size += ((sz//blsize)+1)*blsize
            else:
                print(" --- ERROR: get_dir_size: cannot stat " + fp)

    print(' --- reported file space: ' + str(repo_size) + ' bytes')
    print(' --- disk space: ' + str(total_size) + ' bytes')
    return total_size
