imgname=samviewer
osname=ubuntu
rm -f ${osname}_${imgname}.img
sudo singularity create --size 2048 ${osname}_${imgname}.img
sudo singularity bootstrap ${osname}_${imgname}.img Singularity


