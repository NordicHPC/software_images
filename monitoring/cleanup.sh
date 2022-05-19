NODES=c[1-18,31]-[1-36],c19-[1-20],c60-[1-8]

echo "**************" unmounting images in global /cluster/software/IMAGES/
lf=`find /cluster/software/IMAGES/ -name "*lock"`
for f in $lf; do
    echo trying to obtain lock on $f
    flock -x $f -c "./cleanup_global_locks.sh $f"
done

# find blocked / undetatched loop devices
echo
echo "**************" freeing blocked / undetatched loop devices
pdsh -w $NODES "cleanup_images.py --cleanup --verbosity 0" 2>/dev/null

echo "**************" unmounting images in local /var/lock/software_modules
# umount all mounted but unreported images
pdsh -w $NODES 2>/dev/null /cluster/bin/list_images --unreported | grep -v "No unrep" > out
unrep=`cat out`
IFS=$(echo -en "\n\b")
for i in $unrep; do
    node=`echo $i | sed -e 's/:.*//'`
    module=`echo $i | sed -e 's/.*://' | sed -e 's/ is mounted but not used.*//'`
    ssh $node sudo /cluster/bin/umount_image $module
done

# cleanup finished jobs that did not remove their job information
echo "**************" removing trash job information from /var/lock/software_modules
cp clscript.sh /cluster/tmp
pdsh -w $NODES 2>/dev/null /cluster/tmp/clscript.sh
