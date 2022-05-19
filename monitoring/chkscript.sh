jobs=`ls /var/lock/software_images/*modules | sed -e 's/.modules//' | sed -e 's-.*/--g'`
for j in $jobs; do
    res=`sacct -j $j | grep RUNNING`
    if [ -z "$res" ] ; then

	# check again with scontrol, may be in COMPLETING state
	res=`scontrol show job $j | grep COMPLETING`
	if [ $j == NOJOBID ] || [ -z "$res" ] ; then
	    echo trash left after $j
	fi
    fi
done
