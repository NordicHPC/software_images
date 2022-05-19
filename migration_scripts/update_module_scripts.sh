#!/bin/bash

MODIR=/cluster/etc/modulefiles
MODIR_OUT=/cluster/tmp/modulefiles

# deal with standard old and new modules
for m in `cat modules.new modules.old`; do
    odir=`dirname $m`
    mkdir -p $MODIR_OUT/$odir
    sed '/system logger -t module.*/a system /cluster/bin/module_load $appname/$appversion \\\$\\\{SLURM_JOB_ID=NOJOBID\\\} \$action | logger -t software_images ' $MODIR/$m > $MODIR_OUT/$m
done

# deal with unknown modules BY HAND
for m in `cat modules.unknown`; do
    odir=`dirname $m`
    mkdir -p $MODIR_OUT/$odir
    cp $MODIR/$m $MODIR_OUT/$odir/
done

# verson information
v=`find /cluster/etc/modulefiles -name "\.version"`
s="s.$MODIR.$MODIR_OUT.g"

for f in $v; do
    fnew=`echo $f | sed -e $s`
    cp $f $fnew
done

# sanity: old and new modules
# what is the .version file?
find $MODIR/ -type f | grep -v "\.version" | grep -v "~" | sed -e "s-$MODIR/--" | sort > modulefiles.old
find $MODIR_OUT/ -type f | grep -v "\.version" | sed -e "s-$MODIR_OUT/--" | sort > modulefiles.new

# prints files that are not present in both directories
echo "differences: "
comm -3 modulefiles.new modulefiles.old
