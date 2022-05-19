NODES=c[1-18,31]-[1-36],c19-[1-20],c60-[1-8]

# images reported in .lock files, but not mounted
echo "**************" checking if images that have a .lock file are mounted on reported nodes

# find /cluster/software/IMAGES/ -name "*lock" -exec cat {} \;
lf=`find /cluster/software/IMAGES/ -name "*lock"`
for f in $lf; do
    hns=`cat $f | uniq | sed -e 's/.local//' | sort`
    if [[ "$hns" == "" ]]; then
	echo -- EMPTY $f
	continue
    fi
    hn=`echo $hns | sed -e 's/ /,/g'`
    img=`echo $f | sed -e 's/.lock//'`
    echo -- checking image $img
    haveit=`pdsh -w $hn mount 2>/dev/null | grep $img | sed -e 's/:.*//' | sort`
    if [[ "$haveit" == "$hns" ]]; then
	continue
    fi
    for h in $hns; do
	res=`echo $haveit | grep $h`
	if [[ "$res" == "" ]]; then
	    echo $img not mounted on $h
	fi
    done
done

# find blocked / undetatched loop devices
echo
echo "**************" checking for blocked / undetatched loop devices
pdsh -w $NODES cleanup_images.py --verbosity 0 2>/dev/null

# find finished jobs that have unremoved .modules file in /var/lock/software_images
echo
echo "**************" checking if there is any trash left after finished jobs in /var/lock/software_images
cp chkscript.sh /cluster/tmp
pdsh -w $NODES 2>/dev/null /cluster/tmp/chkscript.sh

# mounted images not reported in /var/lock/software_images
echo
echo "**************" checking if all mounted images are reported in /var/lock/software_images
pdsh -w $NODES 2>/dev/null list_images.py --unreported | grep -v "No unrep"

# find nodes with 64 loop devices
echo
echo "**************" listing nodes with 64 loopback devices
pdsh -w $NODES 2>/dev/null "ls /dev/loop63"
