Preparation of Abel before using the images framework:

1. add module purge to /etc/bash.bash_logout on all compute nodes
   This allows module cleanup when user uses an interactive login to a compute node, or a login node.


2. add to /etc/sudoers.d/users on all compute nodes

%users        ALL=(ALL) NOPASSWD:      /cluster/bin/mount_image
%users        ALL=(ALL) NOPASSWD:      /cluster/bin/umount_image

Change /etc/sudoers to allow login without a tty

sed -i -e 's/^Defaults.*requiretty/# Defaults requiretty/' /etc/sudoers

3. make sure that the path to tools inside module_load is correct:

TOOLS_PATH="/cluster/bin"

4. If doing automatic migration, in update_module_scripts.sh, set path to module_load

/cluster/bin/module_load

  and as root run update_module_scripts.sh

  If converting a single module, the following line needs to be added at the end of the module file (next to last line) to enable image mounting:

system /cluster/bin/module_load $appname/$appversion \$\{SLURM_JOB_ID=NOJOBID\} $action | logger -t software_images 

5. add slurm TaskProlog and JobEpilog that clears modules for a given job, or does a module purge before the job is done

/hpc/src/slurm/scripts/prolog_task: append

## Mount software images:
if [[ -e /cluster/etc/use_software_images ]]; then
    ## Debugging:
    mfa=`type -t module`
    if [[ $mfa == "" ]]; then
        logger -t software_images_prolog $SLURM_JOB_ID `hostname` "module command not availabe (II), printing environment"
        set > /tmp/$SLURM_JOB_ID.II.set
    fi

    modules=`module list --terse 2>&1 | grep -v "Currently Loaded"`
    for m in $modules; do
        if [[ ! -e /cluster/etc/modulefiles/$m ]]; then
            logger -t software_images_prolog $SLURM_JOB_ID $m: unknown module
            continue
        fi
        # logger -t software_images_prolog $SLURM_JOB_ID `hostname` checking $m
        using_modules=`cat /cluster/etc/modulefiles/$m | grep /cluster/bin/module_load`
        if [[ $using_modules == "" ]]; then
            logger -t software_images_prolog $SLURM_JOB_ID `hostname` module $m NOT imaged
            continue
        fi
        logger -t software_images_prolog $SLURM_JOB_ID `hostname` loading image $m
        /cluster/bin/module_load $m $SLURM_JOB_ID load 2>&1 | logger -t software_images
    done
fi


/hpc/src/slurm/scripts/epilog_slurmd: append

## Umount software images:
if [[ -e /cluster/etc/use_software_images ]]; then
    logger -t software_images_epilog `hostname` unmounting all images for job $SLURM_JOB_ID
    /cluster/bin/umount_all_images --job_id $SLURM_JOB_ID 2>&1 | logger -t software_images
    if (( $? != 0 )); then
        remove_log=0
    fi
fi







-------------- ISSUES

double-cache issue. loopback device caches blocks, FS caches files. fixed in linux 4.4...
http://unix.stackexchange.com/questions/278647/overhead-of-using-loop-mounted-images-under-linux

similar when dealing with containers
https://lwn.net/Articles/588309/

ploop can solve this?

