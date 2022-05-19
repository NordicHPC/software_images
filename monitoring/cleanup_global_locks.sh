#!/bin/bash

f=$1
echo checking $f

hns=`cat $f | uniq | sed -e 's/.local//' | sort`
if [[ "$hns" == "" ]]; then
    echo -- EMPTY $f
    exit 0
fi
hn=`echo $hns | sed -e 's/ /,/g'`
img=`echo $f | sed -e 's/.lock//'`
haveit=`pdsh -w $hn mount 2>/dev/null | grep $img | sed -e 's/:.*//' | sort`
if [[ "$haveit" == "$hns" ]]; then
    exit 0
fi

# only save info about the mounted images
truncate --size=0 $f
for h in $hns; do
    res=`echo $haveit | grep $h`
    if [[ "$res" == "" ]]; then
	echo removing spurious entry $h
	continue
    fi
    echo $h.local >> $f
done
