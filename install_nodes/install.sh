## node installation

# bkp
cp /hpc/sbin/prolog_task /tmp
cp /hpc/sbin/epilog_slurmd /tmp

# install new files
cp /cluster/tmp/software_images/prolog_task /hpc/sbin/prolog_task
cp /cluster/tmp/software_images/epilog_slurmd /hpc/sbin/epilog_slurmd
cp /cluster/tmp/software_images/users /etc/sudoers.d/users
cp /cluster/tmp/software_images/bash.bash_logout /etc/bash.bash_logout
cp /cluster/tmp/software_images/sudoers /etc/sudoers
sed -i -e 's/^Defaults.*requiretty/# Defaults requiretty/' /etc/sudoers