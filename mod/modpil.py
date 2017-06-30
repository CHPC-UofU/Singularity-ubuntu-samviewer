#
#
# "modpil.py": a module of using Python Image Library
#
# Author: Maofu Liao	Created on: 05/06/2010	Last updated on: 05/06/2010
#
# ----------------------------------------------------------------------
#
# Author: Maofu Liao (maofuliao@gmail.com)
#
# This program is free open-source software, licensed under the terms of 
# the GNU Public License version 3 (GPLv3). If you redistribute it and/or 
# modify it, please make sure the contribution of Maofu Liao 
# is acknowledged appropriately.
#
#
#

import Image, ImageFile
import wx
import math
import struct
import os
from numpy import *
from numpy.fft import fft2


def Brightness(img, factor):			# factor [-1,1]: 0: original pix; 1: all 255; -1: all 0
	im_auto = Contrast(img,-1,-1)		# factor positive: increase brightness, and vice versa
	factor_abs = abs(factor)
	a = 1 - factor_abs
	if factor >= 0:
		b = 255 * factor_abs
		return im_auto.point(lambda i: i * a + b)
	else:
		return im_auto.point(lambda i: i * a)
			

def Contrast(img, pix_min, pix_max, brightness):
	if pix_min == pix_max:
		return img

	a = 255 / (pix_max - pix_min)
	mini = pix_min * (-a) + brightness
	return img.point(lambda i: i * a + mini)

def Contrast_sigma(img, stat, sigma):
	if stat[3] > stat[4]:
		return img
	# Contrast by sigma multiplier (e.g. 3), no brightness adjustment
	#print stat
	setmin = stat[0] - stat[1] * sigma
	setmax = stat[0] + stat[1] * sigma
	#print setmin, setmax
	return Contrast(img, setmin, setmax, 0)

def CountFrame(img):
	# Count how many images inside one stack file
	try:
		nimages = img.nimages
		return nimages
	except:
		goon = True
		i = 0
		try:
			while goon:
				img.seek(i)
				i += 1
		except EOFError:
			return i

def CutPartNormal(img, xylist, boxsize):
	regionnormallist = []
	regionlist = CutPart(img, xylist, boxsize)
	for region in regionlist:
		stat = StatCal(region)
		regionnormallist.append(Contrast_sigma(region, stat, 3))
	return regionnormallist

def CutPart(img, xylist, boxsize):
	regionlist = []
	rad = int(boxsize / 2.0)
	for xy in xylist:
		box = (xy[0]-rad, xy[1]-rad, xy[0]+rad, xy[1]+rad)
		region = img.crop(box)
		regionlist.append(region)
	return regionlist

def Fft(img, tile):
	# Calculate FFT of an image

	imgx, imgy = img.size
	nx = int(imgx / tile) * 2 - 1	# all tiles overlap half
	ny = int(imgy / tile) * 2 - 1
	dis = int(tile / 2.0)

	npa = array(img.getdata()).reshape(imgy, imgx)

	powersum = zeros((tile, tile))	# Zeros array to store the sum
	for ctx in xrange(nx):
		for cty in xrange(ny):
			x1 = dis * ctx
			y1 = dis * cty
			x2 = x1 + tile
			y2 = y1 + tile
			tilearray = npa[y1:y2,x1:x2]
			fftimg = fft2(tilearray)
			#tilepower = (fftimg.real)**2
			tilepower = (abs(fftimg))**2
			powersum += tilepower
	powersum = powersum / (nx * ny)	# Average power

	tmpdata = []
	for item in powersum.flat:
		#powerdata.append(math.log(math.sqrt(item)*(1e-4) + 1))
		tmpdata.append(math.log(item + 1))

	imgfft = Image.new("F", (tile, tile))
	imgfft.putdata(tmpdata)
	imgfft_center = ShiftImg(imgfft, dis, dis)		# Assembly the 4 corners together

	# Replace the center and outer(corners) with average values
	limit = (tile/9.0)**2
	powerdata = array(imgfft_center.getdata()).reshape(tile, tile)
	pixavg = average(powerdata)
	for cx in range(tile):
		for cy in range(tile):
			if (cx-dis)**2 + (cy-dis)**2 <= limit:
				powerdata[cx,cy] = pixavg
	imgfft_center.putdata(powerdata.ravel())

	return imgfft_center


def FftNotile(img, outsize):
	# Calculate FFT of an image

	imgx, imgy = img.size
	minxy = min(imgx,imgy)
	minxy = (int(minxy/2)) * 2
	minxy_half = minxy / 2
	imguse = img.crop((0, 0, minxy, minxy))
	npa = array(imguse.getdata()).reshape(minxy, minxy)

	fftimg = fft2(npa)
	fftimg = abs(fftimg)
	imgdata = []
	for item in fftimg.flat:
		imgdata.append((math.log(item))**2)
	
	imgfft = Image.new("F", (minxy, minxy))
	imgfft.putdata(imgdata)
	imgfft_center = ShiftImg(imgfft, minxy_half, minxy_half)	# Assembly the 4 corners together

	return imgfft_center.resize((outsize, outsize), Image.ANTIALIAS)


def ImgToBmp(img):
	image = wx.EmptyImage(img.size[0], img.size[1])
#	image.SetData(img.convert('RGB').tostring())
	image.SetData(img.convert('RGB').tobytes())
	bmp = image.ConvertToBitmap()
	return bmp

def InvertContrast(img, stat):
	if stat[3] > stat[4]:
		return img
	# newpix_value = 2 * avg - oldpix_value
	a = -1.0
	b = stat[0] * 2
	img_invert = img.point(lambda i: i * a + b)	
	return img_invert
	

def Resize(img, newsizex, newsizey):
	sizex, sizey = img.size
	if newsizex < sizex or newsizey < sizey:
		return img.resize((newsizex, newsizey), Image.ANTIALIAS)
	else:
		return img.resize((newsizex, newsizey), Image.BICUBIC)

def ResizeToBmp(img, newsizex, newsizey):
	sizex, sizey = img.size
	if newsizex < sizex or newsizey < sizey:	# Downsampling using PIL
		newimg = img.resize((newsizex, newsizey), Image.ANTIALIAS)
	else:						# Upsampling
		newimg = img.resize((newsizex, newsizey), Image.BICUBIC)
	return ImgToBmp(newimg)
	#bitmap = ImgToBmp(img)
	#image = wx.Bitmap.ConvertToImage(bitmap)
	#image.Rescale(newsizex, newsizey)
	#return wx.BitmapFromImage(image)

def ShiftImg(img, shx, shy):
	# Shift an image by x-y integer numbers
	imgsh = img.copy()
	xsize, ysize = imgsh.size
	nparray = array(imgsh.getdata()).reshape(ysize, xsize)
	if shx != 0:
		if shx < 0:
			shx = xsize + shx
		nparray = hstack((nparray[:,(xsize-shx):], nparray[:,:(xsize-shx)]))
	if shy != 0:
		if shy < 0:
			shy = ysize + shy
		nparray = vstack((nparray[(ysize-shy):,:], nparray[:(ysize-shy),:]))
	imgsh.putdata(nparray.ravel())
	return imgsh

def Stat(filename):
	# Get stat first by looking at the SPIDER header, if not found
	# calculate them

	hlist = SpiHeader(filename)
	if len(hlist) > 0:
		hdlist = (99,) + hlist
		if hdlist[6] == 1:		# IMAMI = 1, if stat was there
			std = hdlist[10]	# somtimes std is -1
			if std > 0:
				avg = hdlist[9]
				sumlist = avg * hdlist[2] * hdlist[12]
				imgmin = hdlist[8]
				imgmax = hdlist[7]
				stat = [avg, std, sumlist, imgmin, imgmax]
				return stat
	img = Image.open(filename)
	return StatCal(img)


def StatCal(img):
	# Calculate the stat using numpy array

	try:					# If color image: pixel value is a tuple, not a number
		float(img.getpixel((0,0)))
	except TypeError:			
		return [1, 1, 1, 1, -1]		# Mock values. stat[3](min) > stat[4](max) means 'color'

	newsize = 512
	sizex, sizey = img.size
	if sizex > newsize and sizey > newsize:
		imgs = img.copy()
		imgs.thumbnail((newsize, newsize))
		npa = array(imgs.getdata())
	else:
		npa = array(img.getdata())

	imgmin, imgmax = img.getextrema()
	return [average(npa), npa.std(), 0, imgmin, imgmax]	# [avg, std, dummy value, imgmin, imgmax]


def StatCal_bk100614(img):
	#print '--- Calculating ...'
	# Stat Calculation
	newsize = 512	# resize for a quick Std

	try:					# If color image: pixel value is a tuple, not a number
		float(img.getpixel((0,0)))
	except TypeError:			
		return [1, 1, 1, 1, -1]		# Mock values. stat[3](min) > stat[4](max) means 'color'

	#lt = list(img.getdata())
	#sumlist = sum(lt)
	#avg = sumlist / len(lt)

	sizex, sizey = img.size
	if sizex > newsize and sizey > newsize:
		imgs = img.copy()
		imgs.thumbnail((newsize, newsize))
		lts = list(imgs.getdata())
	else:
		lts = list(img.getdata())
	sumlist = sum(lts)
	avg = sumlist / len(lts)

	if sizex > newsize and sizey > newsize:
		sumlist = sumlist*img.size[0]/imgs.size[0]	# restore sum of original size image

	sumvar = 0.0
	for item in lts:
		sumvar += (item - avg)**2
	std = math.sqrt(sumvar / len(lts))

	imgmin, imgmax = img.getextrema()
	stat = [avg, std, sumlist, imgmin, imgmax]
	return stat

def SpiHeader(spiderfile):
	# Get spider header records 1-30
	hlist = []
	minsize = 30 * 4
	if os.path.getsize(spiderfile) < minsize:
		return hlist

	f = open(spiderfile, 'rb')			# Open in binary mode
	fh = f.read(minsize)
	f.close()

	endtype = 'BIG'
	hlist = struct.unpack('>30f', fh)		# Try big_endian first
	validheader = SpiTestIform(hlist)
	#print 'first=', hlist, validheader
	if not validheader:
		endtype = 'SMALL'
		hlist = struct.unpack('<30f', fh)	# Use small_endian first
		validheader = SpiTestIform(hlist)
		#print 'first=', hlist, validheader

	if not validheader:
		hlist = []
		#print '%s has NO valid SPIDER header!' % spiderfile
	#print endtype
	return hlist
	

def SpiTestIform(hlist):
	# Test if the list looks like a SPIDER header

	try:
		for item in hlist:
			int(item)
	except ValueError:
		return False


	h = (99,) + hlist				# Add one item, so index start=1
	valid = True
	for item in [1,2,5,12,13,22,23]:		# All these should be intergers
		if h[item] != int(h[item]):
			valid = False
	if int(h[23]) != int(h[13]) * int(h[22]):	# LENBYT = LABREC * LABBYT
		valid = False
	return valid

	
# --------------------------------------------------------------------
# For saving 2D stack images in Spider format

def makeSpiderHeaderInStack(im, ct):
    nsam,nrow = im.size
    lenbyt = nsam * 4  # There are labrec records in the header
    labrec = 1024 / lenbyt
    if 1024%lenbyt != 0: labrec += 1
    labbyt = labrec * lenbyt
    hdr = []
    nvalues = labbyt / 4
    for i in range(nvalues):
        hdr.append(0.0)

    if len(hdr) < 23:
        return []

    # NB these are Fortran indices
    hdr[1]  = 1.0           # nslice (=1 for an image)
    hdr[2]  = float(nrow)   # number of rows per slice
    hdr[5]  = 1.0           # iform for 2D image
    hdr[12] = float(nsam)   # number of pixels per line
    hdr[13] = float(labrec) # number of records in file header
    hdr[22] = float(labbyt) # total number of bytes in header
    hdr[23] = float(lenbyt) # record length in bytes
    hdr[27] = ct	    # Numbering of current stacked image

    # adjust for Fortran indexing
    hdr = hdr[1:]
    hdr.append(0.0)
    # pack binary data into a string
    hdrstr = []
    for v in hdr:
        hdrstr.append(struct.pack('f',v))
    return hdrstr


def makeSpiderHeaderOverall(im_stack):
    nsam,nrow = im_stack[0].size
    maxim = len(im_stack)

    lenbyt = nsam * 4  # There are labrec records in the header
    labrec = 1024 / lenbyt
    if 1024%lenbyt != 0: labrec += 1
    labbyt = labrec * lenbyt
    hdr = []
    nvalues = labbyt / 4
    for i in range(nvalues):
        hdr.append(0.0)

    if len(hdr) < 23:
        return []

    # NB these are Fortran indices
    hdr[1]  = 1.0           # nslice (=1 for an image)
    hdr[2]  = float(nrow)   # number of rows per slice
    hdr[5]  = 1.0           # iform for 2D image
    hdr[12] = float(nsam)   # number of pixels per line
    hdr[13] = float(labrec) # number of records in file header
    hdr[22] = float(labbyt) # total number of bytes in header
    hdr[23] = float(lenbyt) # record length in bytes
    hdr[24] = maxim
    hdr[26] = maxim

    # adjust for Fortran indexing
    hdr = hdr[1:]
    hdr.append(0.0)
    # pack binary data into a string
    hdrstr = []
    for v in hdr:
        hdrstr.append(struct.pack('f',v))
    return hdrstr

def saveStack(imstack, filename):
    hdr_stack = makeSpiderHeaderOverall(imstack)
    if len(hdr_stack) < 256:
        raise IOError, "Error creating Spider 2D stack header"
    # write the SPIDER header
    try:
        fp = open(filename, 'wb')
    except:
        raise IOError, "Unable to open %s for writing" % filename
    fp.writelines(hdr_stack)

    rawmode = "F;32NF"  #32-bit native floating point
    ct = 0
    for im in imstack:
	ct += 1		# numbering of stacked images
	if im.mode[0] != "F":
        	im = im.convert('F')
	hdr = makeSpiderHeaderInStack(im, ct)	# h[27]=ct
    	if len(hdr) < 256:
        	raise IOError, "Error creating Spider header"
	fp.writelines(hdr)
	#ims = im.tostring()
	#fp.write(ims)
	ImageFile._save(im, fp, [("raw", (0,0)+im.size, 0, (rawmode,0,1))])
    fp.close()

