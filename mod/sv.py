#!/usr/bin/python
#
#
# Author: Maofu Liao (maofuliao@gmail.com)
#
# This program is free open-source software, licensed under the terms of 
# the GNU Public License version 3 (GPLv3). If you redistribute it and/or 
# modify it, please make sure the contribution of Maofu Liao 
# is acknowledged appropriately.
#
#
import wx
import Image
import modpil
import os
from sys import argv
import cPickle as pickle
import math
import datetime


# =================================== #
# ---------- General Classes -------- #
# =================================== #

class ImageFile:
	def __init__(self, path):
		self.path = path
		self.img = Image.new('F',(0,0), None)		# initiate with a mock image
		self.preSize = [0,0]				# [for record only] Image size before loading (if different, > sizex/y_ori)
		self.preExtrema = [0,0]				# [for record only] Image min,max before loading

		self.img_invert = Image.new('F',(0,0), None)	# inverted version
		self.thumbnail = Image.new('F',(0,0), None)	# thumbnail version
		self.fft = Image.new('F',(0,0), None)		# FFT of the image

		self.sizex_ori, self.sizey_ori = self.img.size
		self.stat = []					# calculated when the image is loaded
		self.stat_invert = []				# stat for inverted image
		self.rotang = 0.0				# Image rotation angle
		self.shown = False
		self.shown_invert = False
		self.xylist = []				# particle coordinates (SVCO_*.dat)
		self.xylist_ref = []				# ref. particle coordinates (not modifiable)
								# (ref/SVCO_*.dat)
		self.distanceList = []				# Distance lines ([[[x1,y1,x2,y2],distanceShow],...])


	def DispList(self, factor, boxsize):
		# factor is (displayed image size / original image size)
		displist = []
		for item in self.xylist:
			newx = int(item[0] * factor)
			newy = int(item[1] * factor)
			rad = int(boxsize * factor / 2.0)
			newsize = rad * 2
			displist.append([newx-rad, newy-rad, newsize, newsize])
		return displist

	def DispListRef(self, factor, boxsize):
		# factor is (displayed image size / original image size)
		displistref = []
		for item in self.xylist_ref:
			newx = int(item[0] * factor)
			newy = int(item[1] * factor)
			rad = int(boxsize * factor / 2.0)
			newsize = rad * 2
			displistref.append([newx-rad, newy-rad, newsize, newsize])
		return displistref

	def InvertContrast(self):
		self.img_invert = modpil.InvertContrast(self.img, self.stat)
		#minmax = self.img_invert.getextrema()
		#self.stat_invert = []
		#self.stat_invert.extend(self.stat)
		#self.stat_invert[3] = minmax[0]
		#self.stat_invert[4] = minmax[1]
		self.stat_invert = modpil.StatCal(self.img_invert)


class ZoomBox:
	def __init__(self, bitmap, zoomxy):
		self.bitmap = bitmap		# A portion of this bmp will be zoomed
		self.zoomxy = zoomxy		# Center coordinate for zooming
		self.shown = True
		self.zoomarea = 40		# Original portion size
		self.blowarea = 200		# Blowup size

		self.zoomrad = int(self.zoomarea / 2.0)
		self.blowrad = int(self.blowarea / 2.0)
		self.rect = wx.Rect(self.zoomxy[0] - self.zoomrad, self.zoomxy[1] - self.zoomrad, self.zoomarea, self.zoomarea)
		self.blow_corner = (self.zoomxy[0] - self.blowrad, self.zoomxy[1] - self.blowrad)
		self.blowrect = wx.Rect(self.blow_corner[0], self.blow_corner[1], self.blowarea, self.blowarea)
		
	def DrawZoomBox(self, memDC):
		image = wx.Bitmap.ConvertToImage(self.bitmap)
		subimage = image.GetSubImage(self.rect)
		subimage.Rescale(self.blowarea, self.blowarea)
		blow = wx.BitmapFromImage(subimage)

		memDC.DrawBitmap(blow, self.blow_corner[0], self.blow_corner[1])
    		memDC.SetPen(wx.Pen(wx.WHITE, 1))
    		memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
		memDC.DrawRectangle(self.blow_corner[0], self.blow_corner[1], self.blowarea, self.blowarea)

	def UnZoomXY(self, pt):
		if self.blowrect.InsideXY(pt[0], pt[1]):
			newx = self.zoomxy[0] + (pt[0] - self.zoomxy[0]) * self.zoomarea / self.blowarea
			newy = self.zoomxy[1] + (pt[1] - self.zoomxy[1]) * self.zoomarea / self.blowarea
			pt_unzoom = (newx, newy)
		else:
			pt_unzoom = pt
		return pt_unzoom


# ========================================== #
# ---------- Main SamViewer Classes -------- #
# ========================================== #

class SamViewer(wx.Frame):
	def __init__(self, parent, id, title):
		wx.Frame.__init__(self, parent, id, title, wx.DefaultPosition, wx.Size(1024,768))

		self.cwd = os.getcwd()

		# ---------- Program Intro Text display ---------- #

		self.introShow = True		# Only show once after starting the program
		self.introText = [\
'SamViewer 2D Image Viewing System, Version 15.01,',
'a program written in wxPython, using Python Image Library and Numpy.',
'',
'Author: Maofu Liao, Ph.D. (maofuliao@gmail.com)',
'',
'',
'',
'SamViewer reads 2D images in SPIDER, MRC, DM3, TIFF, JPEG, PNG, GIF, BMP, etc.',
'',
'SamViewer has 4 modes:',
'  (1) Image Display : to browse and analyze images,',
'  (2) Particle Picking : to mark the particle positions,',
'  (3) Montage Screening : to view and screen image stacks,',
'  (4) Dual Viewer : to analyze RCT and tilt pairs.',
'',
'Switching mode does NOT save the current session.']

		introTotal = len(self.introText)
		self.introCoord = []
		for item in range(introTotal):
			self.introCoord.append((50, item*20+50))


		# ---------- Title, menu, statusbar ---------- #

		self.statusbar = self.CreateStatusBar(3)
		self.statusbar.SetStatusWidths([-3, -1, -3])

		menubar = wx.MenuBar()
		mmode = wx.Menu()
		mmode.Append(21, '&Image Display', 'Image display and analysis', kind=wx.ITEM_RADIO)
		mmode.Append(22, '&Particle Picking', 'Particle picking', kind=wx.ITEM_RADIO)
		mmode.Append(23, '&Montage Screening', 'Particle screening as montage', kind=wx.ITEM_RADIO)
		mmode.Append(24, '&Dual Viewer', 'Paired images display and analysis', kind=wx.ITEM_RADIO)
		mmode.AppendSeparator()
		mmode.Append(10, '&Quit', 'Exit the program')
		menubar.Append(mmode, '&Mode Selection')

		mhelp = wx.Menu()
		mhelp.Append(12, '&SamViewer Website')
		mhelp.AppendSeparator()
		mhelp.Append(14, '&About')
		menubar.Append(mhelp, '&Help')

		self.SetMenuBar(menubar)

		self.Bind(wx.EVT_MENU, self.OnMode1, id=21)
		self.Bind(wx.EVT_MENU, self.OnMode2, id=22)
		self.Bind(wx.EVT_MENU, self.OnMode3, id=23)
		self.Bind(wx.EVT_MENU, self.OnMode4, id=24)
		self.Bind(wx.EVT_MENU, self.OnQuit, id=10)
		self.Bind(wx.EVT_MENU, self.OnWeb, id=12)
		self.Bind(wx.EVT_MENU, self.OnAbout, id=14)

		self.mainPanel = wx.Panel(self, -1)		# MainPanel initiated

		if len(argv) == 1:
			self.StartMode1()
		else:
			if argv[1] == '1':
				self.StartMode1()
			elif argv[1] == '2':
				self.StartMode2()
			elif argv[1] == '3':
				self.StartMode3()
			elif argv[1] == '4':
				self.StartMode4()
			else:
				self.StartMode1()

	def StartMode1(self):
		self.mainPanel.Destroy()
		self.mainPanel = MainPanelM1(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.mainPanel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetTitle('SamViewer :: Image Display')
		self.Layout()

	def StartMode2(self):
		self.mainPanel.Destroy()
		self.mainPanel = MainPanelM2(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.mainPanel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetTitle('SamViewer :: Particle Picking')
		self.Layout()

	def StartMode3(self):
		self.mainPanel.Destroy()
		self.mainPanel = MainPanelM3(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.mainPanel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetTitle('SamViewer :: Montage Screening')
		self.Layout()

	def StartMode4(self):
		self.mainPanel.Destroy()
		self.mainPanel = MainPanelM4(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.mainPanel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetTitle('SamViewer :: Dual Viewer')
		self.Layout()

	def OnMode1(self, event):
		self.ClearStatusBar()
		self.StartMode1()

	def OnMode2(self, event):
		self.ClearStatusBar()
		self.StartMode2()

	def OnMode3(self, event):
		self.ClearStatusBar()
		self.StartMode3()

	def OnMode4(self, event):
		self.ClearStatusBar()
		self.StartMode4()

	def OnQuit(self, event):
		self.Close()

	def OnWeb(self, event):
		import webbrowser 
		webbrowser.open("https://sites.google.com/site/maofuliao/samviewer") 

	def OnAbout(self, event):
		dlgtext = '''
SamViewer (Author: Maofu Liao, maofuliao@gmail.com)
A visualization and analysis tool for 2D images

SamViewer is licensed under the terms of the GNU Public License version 3 (GPLv3). If you redistribute it and/or modify it, please make sure the contribution of Maofu Liao is acknowledged appropriately.


(dm3lib_v099.py) was adapted by Pierre-Ivan Raynal <raynal@med.univ-tours.fr> based on DM3_Reader plug-in (v 1.3.4) for ImageJ by Greg Jefferis <jefferis@stanford.edu>'''
		dlg = wx.MessageDialog(self, dlgtext, 'About SamViewer',
			wx.OK | wx.ICON_INFORMATION)
       		dlg.ShowModal()
		dlg.Destroy()


	def RefreshMainPanel(self, mode):
		self.mainPanel.Destroy()
		if mode == 1:
			self.mainPanel = MainPanelM1(self, -1)
		elif mode == 2:
			self.mainPanel = MainPanelM2(self, -1)
		elif mode == 3:
			self.mainPanel = MainPanelM3(self, -1)
		elif mode == 4:
			self.mainPanel = MainPanelM4(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.mainPanel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.Layout()

	def ClearStatusBar(self):
		for item in range(3):
			self.statusbar.SetStatusText('', item)


# =========================================== #
# ---------- Mode 1: Image Display ---------- #
# =========================================== #

class MainPanelM1(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		# ----- Initial variables -----
		self.imageFiles = []
		self.firstfileopen = True
		self.sigmalevel = 3
		self.invertMarker = 1		# 1: original, -1: invert contrast
		self.showFft = -1		# -1: show image, 1: show FFT

		#self.distanceList = []		# Distance lines ([[x1,y1,x2,y2],...])
		self.distanceStart = False
		self.distanceEnd = False

		self.zoombox = ZoomBox(wx.EmptyBitmap(1,1), (0, 0))	# Initial Mock zoombox, not shown
		self.zoombox.shown = False

		self.thnMag = 0.5			# Side panel (thumbnail) mag
		self.thnStartX = 0
		self.thnStartY = 0
		#self.pickedThn = -1

		# ----- Setup Layout ----- #

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel0 = Panel0_M1(self, -1)			# !!Tool panel Constructed from class
		sizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		self.splitter = wx.SplitterWindow(self, -1, style = wx.BORDER_SUNKEN)
		self.panel1 = Panel1_M1(self.splitter, -1)
		self.panel = Panel_M1(self.splitter, -1)		# Main image window
		self.splitter.SetMinimumPaneSize(5)
		self.splitter.SplitVertically(self.panel1, self.panel, 400)
		sizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizer(sizer)


		self.panel.Bind(wx.EVT_PAINT, self.OnPaint)
		self.panel.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
		self.panel.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
		self.panel.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
		self.panel.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
		self.panel.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleUp)
		self.panel.Bind(wx.EVT_MOTION, self.OnMotion)
		self.panel.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
		self.panel.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDclick)


		self.panel1.Bind(wx.EVT_PAINT, self.OnPaint1)
		self.panel1.Bind(wx.EVT_LEFT_UP, self.OnLeftUp1)
		self.panel1.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown1)
		self.panel1.Bind(wx.EVT_RIGHT_UP, self.OnRightUp1)
		self.panel1.Bind(wx.EVT_MOTION, self.OnMotion1)
		self.panel1.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel1)
		self.panel1.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDclick1)



	# ---------- "Panel0" events ---------- #

	def OnButCloseAll(self, event):
		dlg = wx.MessageDialog(self, 'Do you want to close ALL opened files?', 'Are you sure?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			self.GetParent().RefreshMainPanel(1)		# Reset Mode 2
		dlg.Destroy()

	def OnOpen(self, event):
		if len(self.imageFiles) == 0:
			self.firstfileopen = True

		paths = []
		dlg = wx.FileDialog(self, 'Open one or more image files', self.GetParent().cwd, '', '*', wx.OPEN | wx.MULTIPLE)
		if dlg.ShowModal() == wx.ID_OK:
			paths = dlg.GetPaths()
		dlg.Destroy()
		if len(paths) == 0:
			return
		self.GetParent().cwd = os.path.dirname(paths[0])

		# check for duplication
		paths_checked = []
		for path in paths:
			i = 0
			goon = True
			while goon and i < len(self.imageFiles):
				if path == self.imageFiles[i].path:
					goon = False
				i += 1
			if goon:
				paths_checked.append(path)

		# Read image files
		for path in paths_checked:
			try:
				img = Image.open(path)
				preSize = img.size
				preExtrema = img.getextrema()
				sizex, sizey = img.size
				sizel = 2048				# size limit
				if sizex > sizel and sizey > sizel:	# Make a smaller "original image"
					stinfo = 'Shrinking %s' % os.path.basename(path)
					self.GetParent().statusbar.SetStatusText(stinfo, 0)
					img.thumbnail((sizel, sizel))		# Not using ANTIALIAS for speed

				imagefile = ImageFile(path)			# Class constructed
				imagefile.img = img
				imagefile.preSize = preSize
				imagefile.preExtrema = preExtrema

				stinfo = 'Making thumbnail of %s' % os.path.basename(path)
				self.GetParent().statusbar.SetStatusText(stinfo, 0)
				thn = img.copy()
				thn.thumbnail((256,256), Image.ANTIALIAS)		# img_thumbnail resized inplace!!
				thn_stat = modpil.StatCal(thn)
				imagefile.thumbnail = modpil.Contrast_sigma(thn, thn_stat, 3)
				stinfo = 'Making thumbnail of %s ... Done!' % os.path.basename(path)
				self.GetParent().statusbar.SetStatusText(stinfo, 0)


				self.imageFiles.append(imagefile)

				item = '[%d]%s' % (len(self.imageFiles), os.path.basename(path))
				self.com_files.Append(item)

       			except IOError:
				print 'Can NOT open ', path

		if self.firstfileopen:				# if first time open, auto load the 1st image
			if len(self.imageFiles) > 0:
				self.curFile = 0
				self.com_files.SetSelection(0)
				self.curImageFile = self.imageFiles[0]
				self.LoadImage()

	def OnButClose(self, event):
		self.curFile = self.com_files.GetSelection()
		if self.curFile > -1:
			self.imageFiles.pop(self.curFile)
			self.com_files.Delete(self.curFile)
		if len(self.imageFiles) == 0:
			self.GetParent().RefreshMainPanel(1)
		else:
			if len(self.imageFiles) <= self.curFile:
				self.curFile = len(self.imageFiles) - 1

			count = 1			# refresh file list display
			self.com_files.Clear()
			for imagefile in self.imageFiles:
				item = '[%d]%s' % (count, os.path.basename(imagefile.path))
				self.com_files.Append(item)
				count += 1


			self.com_files.SetSelection(self.curFile)	
			self.curImageFile = self.imageFiles[self.curFile]
			self.LoadImage()

	def OnComFiles(self, event):						# Select and Load an image file
		self.curFile = self.com_files.GetSelection()
		self.curImageFile = self.imageFiles[self.curFile]
		self.LoadImage()						# "self.curImageFile" is loaded

	def LoadImage(self):
		self.GetParent().introShow = False	# Not show intro again, if the first image is loaded
		self.invertMarker = 1			# Autoset the image contrast as original (non-inverted)

		stinfo = 'Loading %s' % os.path.basename(self.curImageFile.path)
		self.GetParent().statusbar.SetStatusText(stinfo, 0)


		# ----- Calculate stat, img_invert, fft (when requested) ----- #

		if len(self.curImageFile.stat) == 0:				# Image Stat not calculated yet
			self.curImageFile.stat = modpil.Stat(self.curImageFile.path)

		#if self.invertMarker == -1:
		#	if self.curImageFile.img_invert.size[0] == 0:		# Inverted image not calculated yet
		#		self.curImageFile.InvertContrast()

		if self.showFft == 1:
			if self.curImageFile.fft.size[0] == 0:			# FFT not calculated yet
				minsize = min(self.curImageFile.img.size)		# Smaller one out of sizex/y
				if minsize >= 512:
					tile = 512
				elif minsize >= 256:
					tile = 256
				elif minsize >= 128:
					tile = 128
				elif minsize >= 64:
					tile = 64
				else:
					tile = 0					# No FFT, return a mock image
				if tile != 0:
					#fft = modpil.Fft(self.curImageFile.img, tile)		# use tile
					fft = modpil.FftNotile(self.curImageFile.img, tile)	# no tile
					fftstat = modpil.StatCal(fft)
					self.curImageFile.fft = modpil.Contrast_sigma(fft, fftstat, 3)
				else:
					self.curImageFile.fft = Image.new("F", (64,64))	# Mock image


		# ----- Show stat ----- #

		self.img_ori = self.curImageFile.img
		self.img_ori_invert = self.curImageFile.img_invert
		self.sizex_ori, self.sizey_ori = self.img_ori.size
		
		#if self.invertMarker == 1:
		self.imgstat = self.curImageFile.stat
		#else:
		#	self.imgstat = self.curImageFile.stat_invert

		if self.curImageFile.stat[3] <= self.curImageFile.stat[4]:	# otherwise color images
			statusinfo = 'Min=%.1f, Max=%.1f, Avg=%.1f, Std=%.1f, Size=%s->%s' %\
				(self.curImageFile.preExtrema[0], self.curImageFile.preExtrema[1],self.imgstat[0],self.imgstat[1], str(self.curImageFile.preSize), str(self.img_ori.size))
			self.GetParent().statusbar.SetStatusText(statusinfo, 0)


		# ----- Prepare image for display ----- #

		if self.firstfileopen:
			self.FitWin()					# Set all initial settings(map, size, pos, mag)
			self.firstfileopen = False
		else:							# Using previous settings
			if self.invertMarker == 1:
				self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.curImageFile.stat, self.sigmalevel)
			else:
				self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.curImageFile.stat_invert, self.sigmalevel)

			self.bitmap_sizex = int(float(self.sizex_ori) * self.mag)
			self.bitmap_sizey = int(float(self.sizey_ori) * self.mag)
			self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)


		# ----- Showing changes -----#

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)		# Set the values of contrast min/max fields
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)

		self.panel.Refresh()					# Draw image
		self.panel1.Refresh()

		statusinfo = '[Shift+L/R/Move]Zoom in/out/Value, [Ctrl+L/R/M]:Distance Ori/End/Del'
		self.GetParent().statusbar.SetStatusText(statusinfo, 2)


	def OnFitWin(self, event):
		if len(self.imageFiles) == 0:
			return

		self.FitWin()
		self.panel.Refresh()	

	def OnSize1(self, event):
		# Set the Mag directly

		if len(self.imageFiles) == 0:
			return

		mag = float(self.text_size.GetValue())
		if mag <= 0 or mag > 2:
			self.text_size.SetValue('1.0')
			return
		self.mag = mag

		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)		# Save old size for centering
		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		winsizex, winsizey = self.panel.GetSize()
		centerx = winsizex / 2
		centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)

	def OnSigma(self, event):
		if len(self.imageFiles) == 0:
			return

		item = event.GetSelection()
		self.sigmalevel = self.sigma_values[item]
		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)

		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.imgstat, self.sigmalevel)
		else:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.imgstat, self.sigmalevel)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()		

	def OnContrastApply(self, event):
		if len(self.imageFiles) == 0:
			return

		imgmin = self.imgstat[3]
		imgmax = self.imgstat[4]
		imgrange = imgmax - imgmin
		truemin = imgmin + imgrange * 0.001 * self.spin_contrastmin.GetValue()
		truemax = imgmin + imgrange * 0.001 * self.spin_contrastmax.GetValue()
		brightness = self.spin_bright.GetValue()
		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast(self.curImageFile.img_invert, truemin, truemax, brightness)
		else:
			self.img_contrast = modpil.Contrast(self.curImageFile.img, truemin, truemax, brightness)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()

	def OnInvert(self, event):
		if len(self.imageFiles) == 0:
			return

		self.invertMarker = self.invertMarker * (-1)
		if self.invertMarker == -1:
			if self.curImageFile.img_invert.size[0] == 0:		# Inverted image not calculated yet
				self.curImageFile.InvertContrast()
			self.imgstat = self.curImageFile.stat_invert
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.imgstat, self.sigmalevel)
		else:
			self.imgstat = self.curImageFile.stat
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.imgstat, self.sigmalevel)

		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)		# Set the values of contrast min/max fields
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)


	def OnFft(self, event):
		if len(self.imageFiles) == 0:
			return

		self.showFft = self.showFft * (-1)
		if self.showFft == 1:
			if self.curImageFile.fft.size[0] == 0:			# FFT not calculated yet
				self.curImageFile.fft = self.CalFft(self.curImageFile.img)
		self.panel.Refresh()

	def OnBuffer(self, event):
		if len(self.imageFiles) == 0:
			return

		for imageFile in self.imageFiles:
			stinfo = 'Buffering %s ... ' % os.path.basename(imageFile.path)
			self.GetParent().statusbar.SetStatusText(stinfo, 0)

			if len(imageFile.stat) == 0:				# Image Stat not calculated yet
				imageFile.stat = modpil.Stat(imageFile.path)

			if imageFile.fft.size[0] == 0:			# FFT not calculated yet
				imageFile.fft = self.CalFft(imageFile.img)

		stinfo = 'Buffering ALL DONE!'
		self.GetParent().statusbar.SetStatusText(stinfo, 0)

	def OnSave(self, event):
		if len(self.imageFiles) == 0:
			return

		wildcard = "PNG file (*.png)|*.png|TIFF file (*.tif)|*.tif"
		path = ''
		savename = os.path.splitext(os.path.basename(self.curImageFile.path))[0]
		dlg = wx.FileDialog(self, 'Save displayed image (%dx%d) as...' % (self.bitmap_sizex, self.bitmap_sizey), self.GetParent().cwd, savename, wildcard, wx.SAVE)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
			index = dlg.GetFilterIndex()
		dlg.Destroy()
		if path == '':
			return

		ext = os.path.splitext(path)[1]
		if ext == '.tif' or ext == '.png':
			fullpath = path
		else:
			if index == 0:
				fullpath = path + '.png'
			elif index == 1:
				fullpath = path + '.tif'
		self.img_contrast.resize((self.bitmap_sizex, self.bitmap_sizey), Image.ANTIALIAS).convert('RGB').save(fullpath)


	def CalFft(self, img):
		minsize = min(img.size)		# Smaller one out of sizex/y
		if minsize >= 512:
			tile = 512
		elif minsize >= 256:
			tile = 256
		elif minsize >= 128:
			tile = 128
		elif minsize >= 64:
			tile = 64
		else:
			tile = 0					# No FFT, return a mock image
		if tile != 0:
			#fft = modpil.Fft(img, tile)		# use tile
			fft = modpil.FftNotile(img, tile)	# no tile			
			fftstat = modpil.StatCal(fft)
			output_fft = modpil.Contrast_sigma(fft, fftstat, 3)
		else:
			output_fft = Image.new("F", (64,64))	# Mock image

		return output_fft



	# ---------- "Panel" events ---------- #

	def OnPaint(self, event):

        	dc = wx.PaintDC(self.panel)
		#self.panel.PrepareDC(dc)
		dc.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
		dc.SetBackground(wx.Brush(wx.BLACK))
		dc.Clear()					# Clears the device context using the current background brush.


		if len(self.imageFiles) == 0 or self.com_files.GetSelection() == -1:
			# If first open without images loaded, display some Intro Info, only show once
			if self.GetParent().introShow:
				dc.DrawTextList(self.GetParent().introText, self.GetParent().introCoord, wx.WHITE)
			return

		memDC = wx.MemoryDC()

		if self.showFft == -1:
			# Draw micrograph
			drawbmp = wx.EmptyBitmap(self.bitmap_sizex, self.bitmap_sizey)
			memDC.SelectObject(drawbmp)
			memDC.Clear()
			memDC.DrawBitmap(self.bitmap, 0, 0)

			# Draw sub_bitmap zoom
			if self.zoombox.shown:
				self.zoombox.DrawZoomBox(memDC)
		else:
			# Draw FFT
			fft = self.curImageFile.fft
			fftsizex, fftsizey = fft.size
			drawbmp = wx.EmptyBitmap(fftsizex, fftsizey)
			memDC.SelectObject(drawbmp)
			memDC.Clear()
			fftbmp = modpil.ImgToBmp(fft)
			memDC.DrawBitmap(fftbmp, 0, 0)

		# Draw distance lines
		if len(self.curImageFile.distanceList) > 0:
			font = wx.Font(12, wx.ROMAN, wx.NORMAL, wx.BOLD)
		        memDC.SetFont(font)
			memDC.SetTextForeground(wx.RED)

			for distance in self.curImageFile.distanceList:
				coorlist = []
				for coor in distance[0]:
					coorlist.append(int(coor * self.mag))
				#memDC.SetPen(wx.Pen(wx.RED, 2, wx.SHORT_DASH))
				memDC.SetPen(wx.Pen(wx.BLACK, 5, wx.SOLID))
				memDC.DrawLine(coorlist[0], coorlist[1], coorlist[2], coorlist[3])

				#memDC.SetPen(wx.Pen(wx.RED, 2, wx.SOLID))
				#memDC.DrawText(distance[1], coorlist[0], coorlist[1])


		# Real drawing
		if self.showFft == -1:
			dc.Blit(self.bitmap_x, self.bitmap_y, self.bitmap_sizex, self.bitmap_sizey, memDC, 0, 0, wx.COPY, True)
		else:
			winsizex, winsizey = self.panel.GetSize()	# Put the FFT in the center
			fft_x = int((winsizex - fftsizex)/2.0)
			fft_y = int((winsizey - fftsizey)/2.0)
			dc.Blit(fft_x, fft_y, fftsizex, fftsizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)

	def OnLeftDown(self, event):
		if len(self.imageFiles) == 0:
			return

	def OnLeftUp(self, event):
		if len(self.imageFiles) == 0:
			return

		if event.ControlDown():			# Record the starting point of distance line
			pt = event.GetPosition()
			self.distanceStartX = int((pt[0] - self.bitmap_x)/self.mag)
			self.distanceStartY = int((pt[1] - self.bitmap_y)/self.mag)
			self.distanceStart = True	# This will remain True unless (Ctrl+Middle)
			self.distanceEnd = False
			stinfo = 'Distance starting [%d, %d]' % (self.distanceStartX, self.distanceStartY)
			self.GetParent().statusbar.SetStatusText(stinfo, 2)

		elif event.ShiftDown():			# Increase Mag (= wheel function)
			self.mag += 0.2
			self.ClickMag()


	def OnRightDown(self, event):
		if len(self.imageFiles) == 0:
			return
		self.dragStartPos = event.GetPosition()
		self.panel.SetCursor(wx.StockCursor(wx.CURSOR_HAND))
		self.zoombox.shown = False				# Right sigle click to remove previous ZoomBox
		self.panel.Refresh()

	def OnRightUp(self, event):
		if len(self.imageFiles) == 0:
			return
		self.panel.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

		if event.ControlDown():
			if not self.distanceStart:			# skip if the starting point is not yet set
				return

			pt = event.GetPosition()
			self.distanceEndX = int((pt[0] - self.bitmap_x)/self.mag)
			self.distanceEndY = int((pt[1] - self.bitmap_y)/self.mag)
			distance = math.sqrt((self.distanceEndX - self.distanceStartX)**2 + (self.distanceEndY - self.distanceStartY)**2)
			distanceShow = '%.1f' % distance
			stinfo = 'Distance ending [%d, %d], %.2f pixels' % (self.distanceEndX, self.distanceEndY, distance)
			self.GetParent().statusbar.SetStatusText(stinfo, 2)

			if self.distanceEnd:				# (modifying the end point) remove the last item before appending
				self.curImageFile.distanceList.pop()

			self.curImageFile.distanceList.append([[self.distanceStartX, self.distanceStartY, self.distanceEndX, self.distanceEndY], distanceShow])
			self.distanceEnd = True				# Indicating the end point is set
			self.panel.Refresh()

		elif event.ShiftDown():			# Decrease Mag (= wheel function)
			sizex, sizey = wx.Bitmap.GetSize(self.bitmap)
			if sizex < 20 or sizey < 20:
				return			# Can not make any smaller
			self.mag += (-0.2)
			self.ClickMag()


	def OnMiddleUp(self, event):
		if len(self.imageFiles) == 0:
			return

		if event.ControlDown():
			if len(self.curImageFile.distanceList) > 0:
				self.curImageFile.distanceList.pop()			# Remove the last distance line
				stinfo = 'Last distance line removed!'
			else:
				stinfo = 'No distance line to remove!'
			self.GetParent().statusbar.SetStatusText(stinfo, 2)
			self.distanceStart = False
			self.distanceEnd = False
			self.panel.Refresh()
					

	def OnMotion(self, event):
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()
		if event.RightIsDown():					# Moving the micrograph
			self.zoombox.shown = False
			diff = pt - self.dragStartPos
			if abs(diff[0]) > 1 or abs(diff[1]) > 1:
				self.bitmap_x += diff[0]
				self.bitmap_y += diff[1]
				self.dragStartPos[0] += diff[0]
				self.dragStartPos[1] += diff[1]
		elif event.ShiftDown():
			ptimgx = int((pt[0] - self.bitmap_x)/self.mag)
			ptimgy = int((pt[1] - self.bitmap_y)/self.mag)
			try:
				pix = self.img_ori.getpixel((ptimgx, ptimgy))
				stinfo = 'X:%d, Y:%d, Value:%.3f' % (ptimgx+1, ptimgy+1, pix)
				self.GetParent().statusbar.SetStatusText(stinfo, 2)
			except IndexError:
				pass
		else:
			return
		self.panel.Refresh()

	def OnWheel(self, event):
		if len(self.imageFiles) == 0:
			return

		self.zoombox.shown = False
        	rotation = event.GetWheelRotation()	# -120: rotate down, shrink image; +120: up, enlarge
		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)
		if sizex < 20 or sizey < 20:
			if rotation < 0:
				return			# Can not make any smaller
		if rotation > 0:
			label = 1
		else:
			label = -1

		if event.ControlDown():
			step = 0.01
		else:
			step = 0.05
		self.mag += label*step

		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		# Position of the resized bitmap (Center with mouse or display center)
		if event.ControlDown():
			centerx, centery = event.GetPosition()
		else:
			winsizex, winsizey = self.panel.GetSize()
			centerx = winsizex / 2
			centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)


	def ClickMag(self):
		# This is only called by Shift+L/R, very similar to the above OnWheel function
		# This is made only because Windows doesn't recognize the wheel rotation

		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)
		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		# Position of the resized bitmap (Center with mouse or display center)
		winsizex, winsizey = self.panel.GetSize()
		centerx = winsizex / 2
		centery = winsizey / 2	
		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)


	def OnRightDclick(self, event):
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()
		pt_bitmap = pt - (self.bitmap_x, self.bitmap_y)
		self.zoombox = ZoomBox(self.bitmap, pt_bitmap)
		self.zoombox.shown = True
		self.panel.Refresh()


	# ---------- "Panel1" events ---------- #

	def OnPaint1(self, event):
		self.panel1.SetBackgroundColour(wx.BLACK)
		if len(self.imageFiles) == 0:
			return

		thnwinsize = self.panel1.GetSize()
		self.displistthn = []
		curx = 0
		cury = 0
		maxy = 0
		draw_sizex = 0			# thumbnails on one big image before drawing
		draw_sizey = 0
		for imagefile in self.imageFiles:
			thn_sizex = int(imagefile.thumbnail.size[0] * self.thnMag)
			thn_sizey = int(imagefile.thumbnail.size[1] * self.thnMag)

			if curx + thn_sizex <= thnwinsize[0]:		# keep in current row
				rect = [curx, cury, thn_sizex, thn_sizey]
				curx += (thn_sizex + 1)
				if maxy < thn_sizey:
					maxy = thn_sizey

				if draw_sizex < curx:
					draw_sizex = curx

			else:						# going to the next row
				if curx == 0:				# (put at least one image per row)
					rect = [curx, cury, thn_sizex, thn_sizey]
				else:
					curx = 0
					cury += (maxy + 1)
					rect = [curx, cury, thn_sizex, thn_sizey]
				curx += (thn_sizex + 1)
				maxy = thn_sizey			# new maxy in the next row

				if draw_sizex < curx:
					draw_sizex = curx

				if curx > thnwinsize[0]:		# test if only fit one
					curx = 0
					cury += (maxy + 1)

			self.displistthn.append(rect)
		draw_sizey = cury + maxy

		
        	dc = wx.PaintDC(self.panel1)
	#	self.panel1.PrepareDC(dc)
		drawbmp = wx.EmptyBitmap(draw_sizex, draw_sizey)
		memDC = wx.MemoryDC()
		memDC.SelectObject(drawbmp)
		memDC.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
		memDC.SetBackground(wx.Brush(wx.BLACK))
		memDC.Clear()					# Clears the device context using the current background brush.
		memDC.SetPen(wx.Pen(wx.GREEN, 1))
		memDC.SetBrush(wx.Brush(wx.BLACK, wx.TRANSPARENT))

		# Draw thumbnails
		i = 0
		for rect in self.displistthn:
			if self.thnMag == 1:
				bitmap = modpil.ImgToBmp(self.imageFiles[i].thumbnail)
			else:
				bitmap = modpil.ResizeToBmp(self.imageFiles[i].thumbnail, rect[2], rect[3])
			memDC.DrawBitmap(bitmap, rect[0], rect[1])
			i += 1

		rect = self.displistthn[self.curFile]		# highlight the selected image
		memDC.DrawRectangle(rect[0], rect[1], rect[2], rect[3])

		# Real drawing
		dc.Blit(self.thnStartX, self.thnStartY, draw_sizex, draw_sizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)

	def OnLeftUp1(self, event):		# Hit_test
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()
		pt_thn = pt - (self.thnStartX, self.thnStartY)

		i = 0						# Hit_test
		goon = True
		while i < len(self.imageFiles) and goon:
			rect = self.displistthn[i]
			if wx.Rect(rect[0], rect[1], rect[2], rect[3]).InsideXY(pt_thn[0], pt_thn[1]):
				goon = False
				self.curFile = i
				self.com_files.SetSelection(i)
				self.curImageFile = self.imageFiles[i]
				self.LoadImage()			# "self.curImageFile" is loaded
									# panel & panel1 are both refreshed
			i += 1
			

	def OnRightDown1(self, event):
		if len(self.imageFiles) == 0:
			return
		self.side_dragStartPos = event.GetPosition()
		self.panel1.SetCursor(wx.StockCursor(wx.CURSOR_HAND))

	def OnRightUp1(self, event):
		if len(self.imageFiles) == 0:
			return
		self.panel1.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

	def OnMotion1(self, event):
		if len(self.imageFiles) == 0:
			return
		pt = event.GetPosition()
		if event.RightIsDown():					# Moving the micrograph
			diff = pt - self.side_dragStartPos
			if abs(diff[0]) > 2 or abs(diff[1]) >2:
				self.thnStartX += diff[0]
				self.thnStartY += diff[1]
				self.side_dragStartPos[0] += diff[0]
				self.side_dragStartPos[1] += diff[1]
		self.panel1.Refresh()

	def OnWheel1(self, event):
		if len(self.imageFiles) == 0:
			return

        	rotation = event.GetWheelRotation()		# -120: rotate down, shrink image; +120: up, enlarge
		if rotation < 0:
			tmpmag = self.thnMag - 0.1		# Prevent the images become too small
			for imagefile in self.imageFiles:
				thn_sizex = int(imagefile.thumbnail.size[0] * tmpmag)
				thn_sizey = int(imagefile.thumbnail.size[1] * tmpmag)
				if thn_sizex < 5 or thn_sizey < 5:
					return
			self.thnMag = tmpmag			
		else:
			self.thnMag += 0.1
		self.panel1.Refresh()

	def OnLeftDclick1(self, event):
		# Refresh panel1 with starting of (0,0) and mag=1
		if len(self.imageFiles) == 0:
			return

		self.thnStartX = 0
		self.thnStartY = 0
		self.panel1.Refresh()


	# ---------- Called functions ----------

	def AutoContrastValue(self, stat, sigmalevel):
		# Set the values of contrast min & max TextCtrls
		truemin = stat[0] - stat[1] * sigmalevel
		truemax = stat[0] + stat[1] * sigmalevel
		imgmin = stat[3]
		imgmax = stat[4]
		imgrange = imgmax - imgmin
		if imgrange > 0:
			fmin = int(1000 * (truemin - imgmin) / imgrange)
			fmax = int(1000 * (truemax - imgmin) / imgrange)
			return fmin, fmax
		else:
			return 499, 500

	def FitWin(self):				# All initial settings when the 1st file is opened
		# Image fit into the window size
		winsizex, winsizey = self.panel.GetSize()
		if float(winsizey)/self.sizey_ori <= float(winsizex)/self.sizex_ori:
			self.bitmap_sizey = winsizey
			self.bitmap_sizex = int(self.bitmap_sizey * (float(self.sizex_ori) / self.sizey_ori))
		else:
			self.bitmap_sizex = winsizex
			self.bitmap_sizey = int(self.bitmap_sizex * (float(self.sizey_ori) / self.sizex_ori))
		self.bitmap_x = int((winsizex - self.bitmap_sizex)/2.0)
		self.bitmap_y = int((winsizey - self.bitmap_sizey)/2.0)
		if self.invertMarker == 1:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.curImageFile.stat, self.sigmalevel)
		else:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.curImageFile.stat_invert, self.sigmalevel)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.mag = self.bitmap_sizex / float(self.sizex_ori)
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)


	def RefreshPanel0(self):
		self.panel0.Destroy()
		self.panel0 = Panel0_M1(self, -1)
		frameSizer = wx.BoxSizer(wx.VERTICAL)
		frameSizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		frameSizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizer(frameSizer)
		self.Layout()


class Panel0_M1(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.ID_BUTCLOSEALL = 225
		self.ID_BUTOPEN = 227
		self.ID_BUTCLOSE = 229
		self.ID_COMFILES = 231
		self.ID_FITWIN = 233
		self.ID_SIZE1 = 235
		self.ID_COMSIGMA = 237
		self.ID_CONTRASTAPPLY = 241
		self.ID_INVERT = 242
		self.ID_FFT = 250
		self.ID_BUFFER = 254
		self.ID_SAVE = 260

		files_ch = []				# file lists for the combobox
		i = 1
		for imagefile in self.GetParent().imageFiles:
			item = '[%d]%s (%d)' % (i, os.path.basename(imagefile.path), len(imagefile.xylist))
			files_ch.append(item)
			i += 1

		self.GetParent().but_closeall = wx.Button(self, self.ID_BUTCLOSEALL, 'XX')
		self.GetParent().but_open = wx.Button(self, self.ID_BUTOPEN, 'Open')
		self.GetParent().but_close = wx.Button(self, self.ID_BUTCLOSE, 'Close->')
		self.GetParent().com_files = wx.ComboBox(self, self.ID_COMFILES, size=(50, -1), choices=files_ch, style=wx.CB_READONLY)
		self.GetParent().but_fitwin = wx.Button(self, self.ID_FITWIN, 'FIT Win', size=(20, -1))
		self.GetParent().text_size = wx.TextCtrl(self, -1, '1.0', size=(20,-1))
		self.GetParent().but_size1 = wx.Button(self, self.ID_SIZE1, '->Mag', size=(20, -1))
		sigma_choices = ['SIGMA 0.5', 'SIGMA 1', 'SIGMA 1.5', 'SIGMA 2', 'SIGMA 2.5', 'SIGMA 3', 'SIGMA 3.5', 'SIGMA 4', 'SIGMA 5']
		self.GetParent().sigma_values = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5]
	        self.GetParent().com_sigma = wx.ComboBox(self, self.ID_COMSIGMA, size=(30, -1), choices=sigma_choices, style=wx.CB_READONLY)
		self.GetParent().com_sigma.SetSelection(5)
		self.GetParent().spin_contrastmin = wx.SpinCtrl(self, -1, '100', size=(20, -1), min=0, max=1000)
		self.GetParent().spin_contrastmax = wx.SpinCtrl(self, -1, '600', size=(20, -1), min=0, max=1000)
		self.GetParent().but_contrastapply = wx.Button(self, self.ID_CONTRASTAPPLY, '->D<-', size=(20, -1))
		self.GetParent().spin_bright = wx.SpinCtrl(self, -1, '0', size=(20, -1), min=-255, max=255)
		self.GetParent().but_invert = wx.Button(self, self.ID_INVERT, 'INVT', size=(20, -1))
		self.GetParent().but_fft = wx.Button(self, self.ID_FFT, 'FFT', size=(20, -1))
		self.GetParent().but_buffer = wx.Button(self, self.ID_BUFFER, 'BUFFER', size=(20, -1))
		self.GetParent().but_save = wx.Button(self, self.ID_SAVE, 'SAVE SHOWN', size=(20, -1))
		#self.GetParent().emptytxt = wx.StaticText(self, -1, '')

		sizer = wx.BoxSizer(wx.HORIZONTAL)
		sizer1 = wx.BoxSizer(wx.HORIZONTAL)
		sizer2 = wx.BoxSizer(wx.HORIZONTAL)
		sizer3 = wx.BoxSizer(wx.HORIZONTAL)
		sizer4 = wx.BoxSizer(wx.HORIZONTAL)
		sizer1.Add(self.GetParent().but_closeall, 1, wx.EXPAND)
		sizer1.Add(self.GetParent().but_open, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().but_close, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().com_files, 8, wx.EXPAND)
		sizer2.Add(self.GetParent().but_fitwin, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().text_size, 1, wx.EXPAND)
		sizer2.Add(self.GetParent().but_size1, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().com_sigma, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmin, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmax, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_contrastapply, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_bright, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_invert, 2, wx.EXPAND | wx.LEFT, 10)
		sizer4.Add(self.GetParent().but_fft, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().but_buffer, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().but_save, 1, wx.EXPAND)
		#sizer4.Add(self.GetParent().emptytxt, 1, wx.EXPAND)
		sizer.Add(sizer1, 3, wx.EXPAND)
		sizer.Add(sizer2, 2, wx.EXPAND | wx.LEFT, 10)
		sizer.Add(sizer3, 4, wx.EXPAND | wx.LEFT, 10)
		sizer.Add(sizer4, 3, wx.EXPAND | wx.LEFT, 10)		
		self.SetSizer(sizer)

		self.Bind(wx.EVT_BUTTON, self.GetParent().OnButCloseAll, id = self.ID_BUTCLOSEALL)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnOpen, id = self.ID_BUTOPEN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnButClose, id = self.ID_BUTCLOSE)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnComFiles, id = self.ID_COMFILES)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFitWin, id = self.ID_FITWIN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSize1, id = self.ID_SIZE1)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnSigma, id = self.ID_COMSIGMA)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnContrastApply, id = self.ID_CONTRASTAPPLY)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnInvert, id = self.ID_INVERT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFft, id = self.ID_FFT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnBuffer, id = self.ID_BUFFER)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSave, id = self.ID_SAVE)



class Panel1_M1(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)


class Panel_M1(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)



# ============================================== #
# ---------- Mode 2: Particle Picking ---------- #
# ============================================== #

class MainPanelM2(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		# ----- Initial variables -----
		self.imageFiles = []
		self.firstfileopen = True
		self.partlist = []
		self.sigmalevel = 3
		self.boxsize_ref = 64
		self.boxsize = 64
		self.cursorDraw = False					# Draw a circle attached to cursor
									# when rad>1, ctrol is pressed, and mouse motion
		self.invertMarker = 1
		self.pickedRectID = -1					# Selected particles in the montage

		self.zoombox = ZoomBox(wx.EmptyBitmap(1,1), (0, 0))	# Initial Mock zoombox, not shown
		self.zoombox.shown = False

		self.sideFreePos = False		# Free docking of montage in the side panel
							# ON when montage is moved (right move), OFF when mag is changed (wheeler)
		self.sideDraw_x = 0
		self.sideDraw_y = 0
		self.sideMag = 1			# Side panel (Particle) mag


		# ----- Setup Layout ----- #

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel0 = Panel0_M2(self, -1)			# !!Tool panel Constructed from class
		sizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		self.splitter = wx.SplitterWindow(self, -1, style = wx.BORDER_SUNKEN)
		self.panel1 = Panel1_M2(self.splitter, -1)
		self.panel = Panel_M2(self.splitter, -1)		# Main image window
		self.splitter.SetMinimumPaneSize(5)
		self.splitter.SplitVertically(self.panel1, self.panel, 250)
		sizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizer(sizer)


		self.panel.Bind(wx.EVT_PAINT, self.OnPaint)
		self.panel.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
		self.panel.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
		self.panel.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
		self.panel.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
		self.panel.Bind(wx.EVT_MOTION, self.OnMotion)
		self.panel.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
		self.panel.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDclick)


		self.panel1.Bind(wx.EVT_PAINT, self.OnPaint1)
		self.panel1.Bind(wx.EVT_LEFT_UP, self.OnLeftUp1)
		self.panel1.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown1)
		self.panel1.Bind(wx.EVT_RIGHT_UP, self.OnRightUp1)
		self.panel1.Bind(wx.EVT_MOTION, self.OnMotion1)
		self.panel1.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel1)
		self.panel1.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDclick1)



	# ---------- "Panel0" events ---------- #

	def OnButCloseAll(self, event):
		if len(self.imageFiles) == 0:
			return

		dlg = wx.MessageDialog(self, 'Do you want to close ALL opened files?', 'Are you sure?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			self.com_files.Clear()
			self.imageFiles = []
			self.panel.Refresh()
			self.partlist = []
			self.panel1.Refresh()
			self.GetParent().ClearStatusBar()
		dlg.Destroy()


	def OnOpen(self, event):
		if len(self.imageFiles) == 0:
			self.firstfileopen = True

		paths = []
		dlg = wx.FileDialog(self, 'Open one or more image files', self.GetParent().cwd, '', '*', wx.OPEN | wx.MULTIPLE)
		if dlg.ShowModal() == wx.ID_OK:
			paths = dlg.GetPaths()
		dlg.Destroy()
		if len(paths) == 0:
			return
		self.GetParent().cwd = os.path.dirname(paths[0])

		# check for duplication
		paths_checked = []
		for path in paths:
			i = 0
			goon = True
			while goon and i < len(self.imageFiles):
				if path == self.imageFiles[i].path:
					goon = False
				i += 1
			if goon:
				paths_checked.append(path)

		# Read image files
		for path in paths_checked:
			try:
				img = Image.open(path)
				imagefile = ImageFile(path)				# Class constructed
				imagefile.img = img
				self.imageFiles.append(imagefile)

				basename = os.path.splitext(os.path.basename(path))
				refcoorf = os.path.dirname(path) + '/ref/SVCO_' + basename[0] + '.dat'	# Load ref. coordinate file, if present
				if os.path.exists(refcoorf):
					imagefile.xylist_ref = self.LoadCoor(refcoorf)

				coorf = os.path.dirname(path) + '/SVCO_' + basename[0] + '.dat'		# Load coordinate file, if present
				if os.path.exists(coorf):
					imagefile.xylist = self.LoadCoor(coorf)

				item = '[%d]%s [%d](%d)' % (len(self.imageFiles), os.path.basename(path), len(imagefile.xylist_ref), len(imagefile.xylist))
				self.com_files.Append(item)

       			except IOError:
				print 'Can NOT open ', path

		if self.firstfileopen:				# if first time open, auto load the 1st image
			if len(self.imageFiles) > 0:
				self.curFile = 0
				self.com_files.SetSelection(0)
				self.curImageFile = self.imageFiles[0]
				self.LoadImage()

	def LoadCoor(self, coorf):
		xylist = []
		f = open(coorf)
		for line in f:
			if not line.strip().startswith(';'):
				content = line.split()
				x = int(float(content[2])) - 1
				y = int(float(content[3])) - 1
				xylist.append([x,y])
		f.close()
		return xylist


	def OnButClose(self, event):
		self.curFile = self.com_files.GetSelection()
		if self.curFile > -1:
			self.imageFiles.pop(self.curFile)
			self.com_files.Delete(self.curFile)
		if len(self.imageFiles) == 0:
			self.GetParent().RefreshMainPanel(2)
		else:
			if len(self.imageFiles) <= self.curFile:
				self.curFile = len(self.imageFiles) - 1

			count = 1			# refresh file list display
			self.com_files.Clear()
			for imagefile in self.imageFiles:
				item = '[%d]%s [%d](%d)' % (count, os.path.basename(imagefile.path), len(imagefile.xylist_ref), len(imagefile.xylist))
				self.com_files.Append(item)
				count += 1


			self.com_files.SetSelection(self.curFile)	
			self.curImageFile = self.imageFiles[self.curFile]
			self.LoadImage()

	def OnComFiles(self, event):						# Select and Load an image file
		self.curFile = self.com_files.GetSelection()
		self.curImageFile = self.imageFiles[self.curFile]
		self.SaveAllParticles()						# Autosave all particles before loading a new image
		self.LoadImage()						# "self.curImageFile" is loaded

	def LoadImage(self):
		self.invertMarker = 1		# Autoset the image contrast as original (non-inverted)

		if len(self.curImageFile.stat) == 0:				# process the first time opened file
			self.curImageFile.stat = modpil.Stat(self.curImageFile.path)

		self.img_ori = self.curImageFile.img
		self.img_ori_invert = self.curImageFile.img_invert
		self.sizex_ori, self.sizey_ori = self.img_ori.size

		#if self.invertMarker == 1:
		self.imgstat = self.curImageFile.stat
		#else:
		#	self.imgstat = self.curImageFile.stat_invert

		statusinfo = 'Min=%.1f, Max=%.1f, Avg=%.1f, Std=%.1f, Size=%s' % (self.imgstat[3], self.imgstat[4],self.imgstat[0],self.imgstat[1], self.img_ori.size)
		self.GetParent().statusbar.SetStatusText(statusinfo, 0)
		self.img_contrast = modpil.Contrast_sigma(self.img_ori, self.imgstat, self.sigmalevel)

		if self.firstfileopen:
			self.FitWin()					# Set all initial settings(map, size, pos, mag)
			self.firstfileopen = False
		else:							# Using previous settings
			self.bitmap_sizex = int(float(self.sizex_ori) * self.mag)
			self.bitmap_sizey = int(float(self.sizey_ori) * self.mag)
			self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)		# Set the values of contrast min/max fields
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)

		self.panel.Refresh()					# Draw image
		if len(self.curImageFile.xylist) > 0:			# Draw box if xylist is not empty
			self.partlist = modpil.CutPartNormal(self.img_ori, self.curImageFile.xylist, self.boxsize)
		else:
			self.partlist = []
		self.pickedRectID = -1					# Clear the Selected particle ID in the montage from last file
		self.panel1.Refresh()


	def OnReadCo(self, event):
		if len(self.imageFiles) == 0:
			return
		conum = float(self.text_readco.GetValue())
		if conum < 0:
			return
		path = self.curImageFile.path
		basename = os.path.splitext(os.path.basename(path))
		autof = os.path.dirname(path) + '/auto/AUTO_' + basename[0] + '.dat'	# Load AUTO coordinate file, if present
		if not os.path.exists(autof):
			return
		autolist = self.LoadCoor(autof)
		if len(autolist) == 0:
			return

		if conum == 0:
			total = len(autolist)
		elif conum > len(autolist):
			total = len(autolist)
		elif conum > 0 and conum < 1:
			total = int(len(autolist) * conum)
		else:
			total = int(conum)
		#print 'total=', total

		shortname = os.path.basename(autof)
		dlgtext = '\n%s contains %d coors. Reading %d coors ...\n\n!!! ALL unsaved coors will be LOST !!!' % (shortname, len(autolist), total)
		dlg = wx.MessageDialog(self, dlgtext, 'Read in Coordinate?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			self.curImageFile.xylist = []
			self.curImageFile.xylist.extend(autolist[:total])
			self.panel.Refresh()

			self.partlist = modpil.CutPartNormal(self.img_ori, self.curImageFile.xylist, self.boxsize)
			self.pickedRectID = -1					# Clear the Selected particle ID in the montage from last file
			self.panel1.Refresh()

			# Refresh combo_box to show particle number
			self.com_files.Delete(self.curFile)
			newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path),\
					 len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
			self.com_files.Insert(newitem, self.curFile)
			self.com_files.SetSelection(self.curFile)


	def OnFitWin(self, event):
		if len(self.imageFiles) == 0:
			return
		self.FitWin()
		self.panel.Refresh()	


	def OnFitWidth(self, event):
		if len(self.imageFiles) == 0:
			return
		self.FitWidth()
		self.panel.Refresh()	


	def OnSize1(self, event):
		if len(self.imageFiles) == 0:
			return

		mag = float(self.text_size.GetValue())
		if mag <= 0 or mag > 2:
			self.text_size.SetValue('1.0')
			return
		self.mag = mag

		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)		# Save old size for centering
		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		winsizex, winsizey = self.panel.GetSize()
		centerx = winsizex / 2
		centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)


	def OnSigma(self, event):
		if len(self.imageFiles) == 0:
			return

		item = event.GetSelection()
		self.sigmalevel = self.sigma_values[item]
		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)

		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.imgstat, self.sigmalevel)
		else:
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.imgstat, self.sigmalevel)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()		

	def OnContrastApply(self, event):
		if len(self.imageFiles) == 0:
			return

		imgmin = self.imgstat[3]
		imgmax = self.imgstat[4]
		imgrange = imgmax - imgmin
		truemin = imgmin + imgrange * 0.001 * self.spin_contrastmin.GetValue()
		truemax = imgmin + imgrange * 0.001 * self.spin_contrastmax.GetValue()
		brightness = self.spin_bright.GetValue()
		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast(self.curImageFile.img_invert, truemin, truemax, brightness)
		else:
			self.img_contrast = modpil.Contrast(self.curImageFile.img, truemin, truemax, brightness)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()

	def OnInvert(self, event):
		if len(self.imageFiles) == 0:
			return

		self.invertMarker = self.invertMarker * (-1)
		if self.invertMarker == -1:
			if self.curImageFile.img_invert.size[0] == 0:		# Inverted image not calculated yet
				self.curImageFile.InvertContrast()
			self.imgstat = self.curImageFile.stat_invert
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img_invert, self.imgstat, self.sigmalevel)
		else:
			self.imgstat = self.curImageFile.stat
			self.img_contrast = modpil.Contrast_sigma(self.curImageFile.img, self.imgstat, self.sigmalevel)

		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.panel.Refresh()

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmalevel)		# Set the values of contrast min/max fields
		self.spin_contrastmin.SetValue(fmin)
		self.spin_contrastmax.SetValue(fmax)


	def OnBoxSize(self, event):
		self.boxsize = int(float(self.text_boxsize.GetValue()))
		self.boxsize_ref = int(float(self.text_boxsize_ref.GetValue()))
		#self.cursorRad = int(float(self.text_cursorRad.GetValue()))
		if len(self.imageFiles) == 0:
			return

		self.panel.Refresh()
		# also update the particle window
		self.partlist = modpil.CutPartNormal(self.img_ori, self.curImageFile.xylist, self.boxsize)
		self.panel1.Refresh()
		

	def OnSaveParticles(self, event):
		self.SaveAllParticles()


	def SaveAllParticles(self):
		total = 0
		imgcount = 0
		for imagefile in self.imageFiles:
			basename = os.path.splitext(os.path.basename(imagefile.path))
			coorf = os.path.dirname(imagefile.path) + '/SVCO_' + basename[0] + '.dat'

			if len(imagefile.xylist) > 0:
				f = open(coorf, 'w')
				i = 1
				for xy in imagefile.xylist:
					line = '%8d%3d%8d%8d\n' % (i, 2, xy[0]+1, xy[1]+1)
					f.write(line)
					i += 1
					total += 1
				f.close()
				imgcount += 1
			else:
				if os.path.exists(coorf):
					os.remove(coorf)

		self.GetParent().statusbar.SetStatusText('%d particles from %d images saved!' % (total, imgcount), 2)



	# ---------- "Panel" events ---------- #

	def OnPaint(self, event):

		self.panel.SetBackgroundColour(wx.BLACK)
		if len(self.imageFiles) == 0 or self.com_files.GetSelection() == -1:
			return

        	dc = wx.PaintDC(self.panel)
#		self.panel.PrepareDC(dc)
		memDC = wx.MemoryDC()

		# Draw micrograph
		drawbmp = wx.EmptyBitmap(self.bitmap_sizex, self.bitmap_sizey)
		memDC.SelectObject(drawbmp)
		memDC.Clear()
		memDC.DrawBitmap(self.bitmap, 0, 0)

		# Draw Boxes according to the xylist_ref
		self.displistref = self.curImageFile.DispListRef(self.mag, self.boxsize_ref)
		if len(self.displistref) > 0:
			memDC.SetPen(wx.Pen(wx.BLUE, 2))
    			memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
			memDC.DrawRectangleList(self.displistref)

		# Draw Boxes according to the xylist
		self.displist = self.curImageFile.DispList(self.mag, self.boxsize)
		if len(self.displist) > 0:
			memDC.SetPen(wx.Pen(wx.GREEN, 2))
    			memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
			memDC.DrawRectangleList(self.displist)

		# Draw picked_BOX (in RED)
		if self.pickedRectID > -1:
			rect = self.displist[self.pickedRectID]
			memDC.SetPen(wx.Pen(wx.RED, 2))
    			memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
			memDC.DrawRectangle(rect[0], rect[1], rect[2], rect[3])


		# Draw cursor circle, when ctrl+motion and rad>1
		if self.cursorDraw:
			ptx = self.cursorPt[0] - self.bitmap_x
			pty = self.cursorPt[1] - self.bitmap_y
			memDC.SetPen(wx.Pen(wx.RED, 2))
    			memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
			memDC.DrawCircle(ptx-1, pty-1, self.cursorRad)		# with mag already applied (in function "OnMotion")
										# pt-1 to get better positioning


		# Draw sub_bitmap zoom
		if self.zoombox.shown:
			self.zoombox.DrawZoomBox(memDC)


		# Real drawing
		dc.Blit(self.bitmap_x, self.bitmap_y, self.bitmap_sizex, self.bitmap_sizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)



	def HitTest(self, pt):
		if len(self.curImageFile.xylist) == 0:
			return []
		pt = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)	# True coordinate on micrograph
		hitpoints = []
		for i in xrange(len(self.displist)):
			disp = self.displist[i]
			#print disp
			if pt[0] >= disp[0] and pt[0] <= (disp[0] + disp[2]):
				if pt[1] >= disp[1] and pt[1] <= (disp[1] + disp[3]):
					hitpoints.append(i)
		return hitpoints

	def OnLeftDown(self, event):
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()

		pt_img = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)
		if self.zoombox.shown:
			pt_img = self.zoombox.UnZoomXY(pt_img)
		pt = (self.bitmap_x + pt_img[0], self.bitmap_y + pt_img[1])

		hitpoints = self.HitTest(pt)
		if len(hitpoints) > 0:					# if one particle is hit, save ID and the coordinate
			self.hit_leftdown = hitpoints[0]
			self.xylist_hit = []			
			self.xylist_hit.extend(self.curImageFile.xylist[self.hit_leftdown])
			self.hitPt = pt					# Saved for others, e.g. 'OnMotion' to move box
		else:
			self.hit_leftdown = -1			# -1: no hit; otherwise, hit a particle	

	def OnLeftUp(self, event):
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()
		pt_img = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)
		if self.zoombox.shown:
			pt_img = self.zoombox.UnZoomXY(pt_img)
		pt = (self.bitmap_x + pt_img[0], self.bitmap_y + pt_img[1])

		hitpoints = self.HitTest(pt)			# HitTest for mouse_up
		if event.ShiftDown():				# Delete one particle
			if len(hitpoints) == 1:
				self.curImageFile.xylist.pop(hitpoints[0])
				self.partlist.pop(hitpoints[0])
				self.pickedRectID = -1		# Clear the highlighted particle
				self.GetParent().statusbar.SetStatusText('One particle removed. Current total %d' % len(self.partlist), 2)
				self.panel1.Refresh()
				self.panel.Refresh()
									# Refresh combo_box to show particle number
				self.com_files.Delete(self.curFile)
				newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path), len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
				self.com_files.Insert(newitem, self.curFile)
				self.com_files.SetSelection(self.curFile)
			return

		if len(hitpoints) == 0:
			self.hit_leftup = -1
		elif len(hitpoints) == 1:
			self.hit_leftup = hitpoints[0]
		else:
			self.hit_leftup = -2			# This only happen when a box moved on top of another


		if self.hit_leftdown == -1:				# New particle picked
			if self.hit_leftup == -1:
				newx = int((pt[0] - self.bitmap_x) / self.mag)
				newy = int((pt[1] - self.bitmap_y) / self.mag)
				if newx > 0 and newx < self.sizex_ori and newy > 0 and newy < self.sizey_ori:
					self.curImageFile.xylist.append([newx, newy])
					newregion = modpil.CutPartNormal(self.img_ori, [[newx, newy]], self.boxsize)[0]
					self.partlist.append(newregion)
					self.GetParent().statusbar.SetStatusText('One particle picked. Current total %d' % len(self.partlist), 2)
									# Refresh combo_box to show particle number
					self.com_files.Delete(self.curFile)
					newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path), len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
					self.com_files.Insert(newitem, self.curFile)
					self.com_files.SetSelection(self.curFile)
		else:							# Modify previous particles
			i = self.hit_leftdown
			if self.hit_leftup == -2:			# No change, restore old coordinate
				self.curImageFile.xylist[i][0] = self.xylist_hit[0]
				self.curImageFile.xylist[i][1] = self.xylist_hit[1]			
			else:						# Change one particle coordinate
				#self.curImageFile.xylist[i][0] = int((pt[0] - self.bitmap_x) / self.mag)
				#self.curImageFile.xylist[i][1] = int((pt[1] - self.bitmap_y) / self.mag)
				self.curImageFile.xylist[i][0] = self.xylist_hit[0] + int((pt[0] - self.hitPt[0]) / self.mag)
				self.curImageFile.xylist[i][1] = self.xylist_hit[1] + int((pt[1] - self.hitPt[1]) / self.mag)
				newregion = modpil.CutPartNormal(self.img_ori, [[self.curImageFile.xylist[i][0], self.curImageFile.xylist[i][1]]], self.boxsize)[0]
				self.partlist[i] = newregion

		# print 'markershapes = ', self.curImageFile.xylist

		self.zoombox.shown = False
		self.panel.Refresh()
		self.panel1.Refresh()


	def OnRightDown(self, event):
		if len(self.imageFiles) == 0:
			return
		self.dragStartPos = event.GetPosition()
		self.panel.SetCursor(wx.StockCursor(wx.CURSOR_HAND))
		self.zoombox.shown = False				# Right sigle click to remove previous ZoomBox
		self.panel.Refresh()

	def OnRightUp(self, event):
		if len(self.imageFiles) == 0:
			return
		self.panel.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

	def OnMotion(self, event):
		if len(self.imageFiles) == 0:
			return

		if event.ShiftDown():					# No response for "Shift" (to delete particle)
			return

		pt = event.GetPosition()

		if event.ControlDown():					# "Ctrol" to draw a circle attached to cursor
			self.cursorRad_true = float(self.text_cursorRad.GetValue())
			self.cursorRad = int(self.cursorRad_true * self.mag)
			if self.cursorRad > 1:
				self.cursorDraw = True
				self.cursorPt = pt

				if event.RightIsDown():			# Eraser = Ctrl + Hold down Right + Move
					xtrue = int((pt[0] - self.bitmap_x)/self.mag)
					ytrue = int((pt[1] - self.bitmap_y)/self.mag)

					xylist_new = []			# The remaining particle coordinates and cut-particles
					partlist_new = []
					i = -1
					for item in self.curImageFile.xylist:
						i += 1
						if abs(item[0]-xtrue) > self.cursorRad_true or abs(item[1]-ytrue) > self.cursorRad_true:
							xylist_new.append(item)
							partlist_new.append(self.partlist[i])
					self.curImageFile.xylist = []
					self.curImageFile.xylist.extend(xylist_new)
					self.partlist = []
					self.partlist.extend(partlist_new)

					self.pickedRectID = -1		# Clear the highlighted particle
					self.GetParent().statusbar.SetStatusText('', 2)
					self.panel1.Refresh()

									# Refresh combo_box to show particle number
					self.com_files.Delete(self.curFile)
					newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path),\
							 len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
					self.com_files.Insert(newitem, self.curFile)
					self.com_files.SetSelection(self.curFile)


		else:
			self.cursorDraw = False

			if event.RightIsDown():					# Moving the micrograph
				self.zoombox.shown = False
				diff = pt - self.dragStartPos
				if abs(diff[0]) > 1 or abs(diff[1]) > 1:
					self.bitmap_x += diff[0]
					self.bitmap_y += diff[1]
					self.dragStartPos[0] += diff[0]
					self.dragStartPos[1] += diff[1]
			elif event.LeftIsDown() and self.hit_leftdown != -1:	# Moving the marker (box)
				i = self.hit_leftdown
				#self.curImageFile.xylist[i][0] = int((pt[0] - self.bitmap_x) / self.mag)
				#self.curImageFile.xylist[i][1] = int((pt[1] - self.bitmap_y) / self.mag)
				# Box movement is not determined by the clicking point, but rather the moving of mouse/box
				self.curImageFile.xylist[i][0] = self.xylist_hit[0] + int((pt[0] - self.hitPt[0]) / self.mag)
				self.curImageFile.xylist[i][1] = self.xylist_hit[1] + int((pt[1] - self.hitPt[1]) / self.mag)

				newregion = modpil.CutPartNormal(self.img_ori, [[self.curImageFile.xylist[i][0], self.curImageFile.xylist[i][1]]], self.boxsize)[0]
				self.partlist[i] = newregion
				self.panel1.Refresh()
			else:
				return
		self.panel.Refresh()


	def OnWheel(self, event):
		if len(self.imageFiles) == 0:
			return

		self.zoombox.shown = False
        	rotation = event.GetWheelRotation()	# -120: rotate down, shrink image; +120: up, enlarge
		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)
		if sizex < 20 or sizey < 20:
			if rotation < 0:
				return			# Can not make any smaller
		if rotation > 0:
			label = 1
		else:
			label = -1

		if event.ControlDown():
			step = 0.01
		else:
			step = 0.05
		self.mag += label*step

		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		# Position of the resized bitmap (Center with mouse or display center)
		if event.ControlDown():
			centerx, centery = event.GetPosition()
		else:
			winsizex, winsizey = self.panel.GetSize()
			centerx = winsizex / 2
			centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)


	def OnRightDclick(self, event):
		if len(self.imageFiles) == 0:
			return

		pt = event.GetPosition()
		pt_bitmap = pt - (self.bitmap_x, self.bitmap_y)
		self.zoombox = ZoomBox(self.bitmap, pt_bitmap)
		self.zoombox.shown = True
		self.panel.Refresh()


	# ---------- "Panel1" events ---------- #

	def OnPaint1(self, event):
		self.panel1.SetBackgroundColour(wx.BLACK)
		if len(self.partlist) == 0:
			return

		partwinsize = self.panel1.GetSize()
		mboxsize = int(self.boxsize * self.sideMag)

		if partwinsize[0] < mboxsize + 4:
			numperrow = 1
		else:
			numperrow = int(partwinsize[0] / float((mboxsize)+1))
		row = int(len(self.partlist) / numperrow) + 1

		
        	dc = wx.PaintDC(self.panel1)
#		self.panel1.PrepareDC(dc)
		draw_sizex = numperrow*(mboxsize + 1)
		draw_sizey = row*(mboxsize + 1)
		drawbmp = wx.EmptyBitmap(draw_sizex, draw_sizey)
		memDC = wx.MemoryDC()
		memDC.SelectObject(drawbmp)
		memDC.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
		memDC.SetBackground(wx.Brush(wx.BLACK))
		memDC.Clear()					# Clears the device context using the current background brush.
		memDC.SetPen(wx.Pen(wx.GREEN, 1))
		memDC.SetBrush(wx.Brush(wx.BLACK, wx.TRANSPARENT))

		# Draw montage
		self.particleRectList = []
		count = 0
		for y in range(row):
			for x in range(numperrow):
				if count < len(self.partlist):
					if self.sideMag == 1:
						bitmap = modpil.ImgToBmp(self.partlist[count])
					else:
						bitmap = modpil.ResizeToBmp(self.partlist[count], mboxsize, mboxsize)
					memDC.DrawBitmap(bitmap, x*(mboxsize+1), y*(mboxsize+1))
					self.particleRectList.append(wx.Rect(x*(mboxsize+1), y*(mboxsize+1), mboxsize, mboxsize))	# Reclist for Hittest
				count += 1
		if self.pickedRectID > -1:
			rect = self.particleRectList[self.pickedRectID]
			memDC.SetPen(wx.Pen(wx.RED, 1))
			memDC.DrawRectangle(rect[0], rect[1], rect[2], rect[3])

		# Reset montage up left corner
		if not self.sideFreePos:
			self.sideDraw_x = 0
			if draw_sizey < partwinsize[1]:
				self.sideDraw_y = 0
			else:
				self.sideDraw_y = partwinsize[1] - draw_sizey

		dc.Blit(self.sideDraw_x, self.sideDraw_y, draw_sizex, draw_sizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)


	def OnLeftUp1(self, event):		# Hit_test
		if len(self.partlist) == 0:
			return

		pt = event.GetPosition()
		pt_montage = pt - (self.sideDraw_x, self.sideDraw_y)

		i = 0						# Hit_test
		goon = True
		while i < len(self.particleRectList) and goon:
			if self.particleRectList[i].InsideXY(pt_montage[0], pt_montage[1]):
				if event.ShiftDown():				# Delete one particle
					self.partlist.pop(i)
					self.curImageFile.xylist.pop(i)
					self.pickedRectID = -1
					self.GetParent().statusbar.SetStatusText('One particle removed. Current total %d' % len(self.partlist), 2)

									# Refresh combo_box to show particle number
					self.com_files.Delete(self.curFile)
					newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path), len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
					self.com_files.Insert(newitem, self.curFile)
					self.com_files.SetSelection(self.curFile)
				elif event.ControlDown():			# Move this particle to the top of the particle list
					movepart = self.partlist.pop(i)
					self.partlist.insert(0, movepart)
					movexy = self.curImageFile.xylist.pop(i)
					self.curImageFile.xylist.insert(0,movexy)
					self.pickedRectID = -1
					self.GetParent().statusbar.SetStatusText('One particle moved to the top. Current total %d' % len(self.partlist), 2)
				else:						# Highlight one particle
					self.pickedRectID = i
					self.GetParent().statusbar.SetStatusText('Selected particle ID: %d' % (i+1), 2)
					winsizex, winsizey = self.panel.GetSize()
					self.bitmap_x = int(winsizex/2.0 - self.mag*self.curImageFile.xylist[i][0])
					self.bitmap_y = int(winsizey/2.0 - self.mag*self.curImageFile.xylist[i][1])

				self.panel1.Refresh()
				self.panel.Refresh()
				goon = False
			i += 1
			

	def OnRightDown1(self, event):
		if len(self.partlist) == 0:
			return
		self.side_dragStartPos = event.GetPosition()
		self.panel1.SetCursor(wx.StockCursor(wx.CURSOR_HAND))

	def OnRightUp1(self, event):
		if len(self.partlist) == 0:
			return
		self.panel1.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

		pt = event.GetPosition()
		pt_montage = pt - (self.sideDraw_x, self.sideDraw_y)

		i = 0						# Hit_test
		goon = True
		while i < len(self.particleRectList) and goon:
			if self.particleRectList[i].InsideXY(pt_montage[0], pt_montage[1]):
				if event.ShiftDown():				# Delete this and ALL following particles!
					rmtotal = len(self.partlist) - i
					self.partlist = self.partlist[:i]
					self.curImageFile.xylist = self.curImageFile.xylist[:i]
					self.pickedRectID = -1
					self.GetParent().statusbar.SetStatusText('%d particles removed. Current total %d' % (rmtotal, i), 2)

					# Refresh combo_box to show particle number
					self.com_files.Delete(self.curFile)
					newitem = '[%d]%s [%d](%d)' % (self.curFile+1, os.path.basename(self.curImageFile.path), len(self.curImageFile.xylist_ref), len(self.curImageFile.xylist))
					self.com_files.Insert(newitem, self.curFile)
					self.com_files.SetSelection(self.curFile)

				self.panel1.Refresh()
				self.panel.Refresh()
				goon = False
			i += 1


	def OnMotion1(self, event):
		if len(self.partlist) == 0:
			return
		pt = event.GetPosition()
		if event.RightIsDown():					# Moving the micrograph
			diff = pt - self.side_dragStartPos
			if abs(diff[0]) > 2 or abs(diff[1]) >2:
				self.sideDraw_x += diff[0]
				self.sideDraw_y += diff[1]
				self.side_dragStartPos[0] += diff[0]
				self.side_dragStartPos[1] += diff[1]
			self.sideFreePos = True			# Free positioning of the montage
		self.panel1.Refresh()

	def OnWheel1(self, event):
		if len(self.partlist) == 0:
			return

        	rotation = event.GetWheelRotation()	# -120: rotate down, shrink image; +120: up, enlarge
		mboxsize = int(self.boxsize * self.sideMag)
		if mboxsize < 20:
			if rotation < 0:
				return			# Can not make any smaller
		if rotation < 0:
			self.sideMag += -0.1
		else:
			self.sideMag += 0.1

		self.sideFreePos = False		# Reset the montage position
		self.panel1.Refresh()

	def OnLeftDclick1(self, event):
		# Open the next or previous image file in the list
		if len(self.imageFiles) == 0:
			return

		if event.ShiftDown():	# Avoid confusion with fast click of "Shift + Left" (to remove particles)
			return

		self.SaveAllParticles()		# Autosave all particles

		doloadimg = False
		if event.ControlDown():
			if self.curFile > 0:
				self.curFile = self.curFile - 1
				doloadimg = True				
		else:
			if self.curFile < (len(self.imageFiles) - 1):
				self.curFile += 1
				doloadimg = True
		if doloadimg:
			self.com_files.SetSelection(self.curFile)
			self.curImageFile = self.imageFiles[self.curFile]
			self.LoadImage()



	# ---------- Called functions ----------

	def AutoContrastValue(self, stat, sigmalevel):
		# Set the values of contrast min & max TextCtrls
		truemin = stat[0] - stat[1] * sigmalevel
		truemax = stat[0] + stat[1] * sigmalevel
		imgmin = stat[3]
		imgmax = stat[4]
		imgrange = imgmax - imgmin
		fmin = int(1000 * (truemin - imgmin) / imgrange)
		fmax = int(1000 * (truemax - imgmin) / imgrange)
		return fmin, fmax

	def FitWin(self):				# All initial settings when the 1st file is opened
		# Image fit into the window size
		winsizex, winsizey = self.panel.GetSize()
		if float(winsizey)/self.sizey_ori <= float(winsizex)/self.sizex_ori:
			self.bitmap_sizey = winsizey
			self.bitmap_sizex = int(self.bitmap_sizey * (float(self.sizex_ori) / self.sizey_ori))
		else:
			self.bitmap_sizex = winsizex
			self.bitmap_sizey = int(self.bitmap_sizex * (float(self.sizey_ori) / self.sizex_ori))
		self.bitmap_x = int((winsizex - self.bitmap_sizex)/2.0)
		self.bitmap_y = int((winsizey - self.bitmap_sizey)/2.0)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.mag = self.bitmap_sizex / float(self.sizex_ori)
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)

	def FitWidth(self):
		# Image fit into the window width, i.e. x
		winsizex, winsizey = self.panel.GetSize()
		newsizex = winsizex - 10	# make some edge
		if newsizex < 10:
			return
		self.bitmap_sizex = newsizex
		self.bitmap_sizey = int(self.bitmap_sizex * (float(self.sizey_ori) / self.sizex_ori))
		self.bitmap_x = int((winsizex - self.bitmap_sizex)/2.0)		# Align the image to the center top
		self.bitmap_y = 0
		#self.bitmap_y = int((winsizey - self.bitmap_sizey)/2.0)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.mag = self.bitmap_sizex / float(self.sizex_ori)
		self.GetParent().statusbar.SetStatusText('Mag= %.3f' % self.mag, 1)

	def RefreshPanel0(self):
		self.panel0.Destroy()
		self.panel0 = Panel0_M2(self, -1)
		frameSizer = wx.BoxSizer(wx.VERTICAL)
		frameSizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		frameSizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizer(frameSizer)
		self.Layout()


class Panel0_M2(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.ID_BUTCLOSEALL = 225
		self.ID_BUTOPEN = 227
		self.ID_BUTCLOSE = 229
		self.ID_COMFILES = 231
		self.ID_READCO = 232
		self.ID_FITWIN = 233
		self.ID_FITWIDTH = 234
		self.ID_SIZE1 = 235
		self.ID_COMSIGMA = 237
		self.ID_CONTRASTAPPLY = 241
		self.ID_INVERT = 242
		self.ID_BOXSIZE = 245
		self.ID_SAVEPARTICLES = 247


		files_ch = []				# file lists for the combobox
		i = 1
		for imagefile in self.GetParent().imageFiles:
			item = '[%d]%s (%d)' % (i, os.path.basename(imagefile.path), len(imagefile.xylist))
			files_ch.append(item)
			i += 1

		self.GetParent().but_closeall = wx.Button(self, self.ID_BUTCLOSEALL, 'XX')
		self.GetParent().but_open = wx.Button(self, self.ID_BUTOPEN, 'Open')
		self.GetParent().but_close = wx.Button(self, self.ID_BUTCLOSE, 'Close->')
		self.GetParent().com_files = wx.ComboBox(self, self.ID_COMFILES, size=(50, -1), choices=files_ch, style=wx.CB_READONLY)
		self.GetParent().text_readco = wx.TextCtrl(self, -1, '0', size=(10,-1))
		self.GetParent().but_readco = wx.Button(self, self.ID_READCO, '->ReadCo', size=(20, -1))
		self.GetParent().but_fitwin = wx.Button(self, self.ID_FITWIN, 'Fit', size=(20, -1))
		self.GetParent().but_fitwidth = wx.Button(self, self.ID_FITWIDTH, 'Wid', size=(20, -1))
		self.GetParent().text_size = wx.TextCtrl(self, -1, '1.0', size=(20,-1))
		self.GetParent().but_size1 = wx.Button(self, self.ID_SIZE1, '->Mag', size=(20, -1))
		sigma_choices = ['SIGMA 0.5', 'SIGMA 1', 'SIGMA 1.5', 'SIGMA 2', 'SIGMA 2.5', 'SIGMA 3', 'SIGMA 3.5', 'SIGMA 4', 'SIGMA 5']
		self.GetParent().sigma_values = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5]
	        self.GetParent().com_sigma = wx.ComboBox(self, self.ID_COMSIGMA, size=(30, -1), choices=sigma_choices, style=wx.CB_READONLY)
		self.GetParent().com_sigma.SetSelection(5)
		self.GetParent().spin_contrastmin = wx.SpinCtrl(self, -1, '100', size=(20, -1), min=0, max=1000)
		self.GetParent().spin_contrastmax = wx.SpinCtrl(self, -1, '600', size=(20, -1), min=0, max=1000)
		self.GetParent().but_contrastapply = wx.Button(self, self.ID_CONTRASTAPPLY, '->D<-', size=(20, -1))
		self.GetParent().spin_bright = wx.SpinCtrl(self, -1, '0', size=(20, -1), min=-255, max=255)
		self.GetParent().but_invert = wx.Button(self, self.ID_INVERT, 'INVT', size=(20, -1))
		self.GetParent().text_boxsize_ref = wx.TextCtrl(self, -1, '64', size=(20, -1))
		self.GetParent().text_boxsize = wx.TextCtrl(self, -1, '64', size=(20, -1))
		self.GetParent().but_boxsize = wx.Button(self, self.ID_BOXSIZE, '->BOX', size=(20, -1))
		self.GetParent().text_cursorRad = wx.TextCtrl(self, -1, '0', size=(20,-1))
		self.GetParent().but_saveparticles = wx.Button(self, self.ID_SAVEPARTICLES, 'Save particles!', size=(50, -1))

		sizer = wx.BoxSizer(wx.HORIZONTAL)
		sizer1 = wx.BoxSizer(wx.HORIZONTAL)
		sizer2 = wx.BoxSizer(wx.HORIZONTAL)
		sizer3 = wx.BoxSizer(wx.HORIZONTAL)
		sizer4 = wx.BoxSizer(wx.HORIZONTAL)
		sizer1.Add(self.GetParent().but_closeall, 1, wx.EXPAND)
		sizer1.Add(self.GetParent().but_open, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().but_close, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().com_files, 6, wx.EXPAND)
		sizer1.Add(self.GetParent().text_readco, 1, wx.EXPAND)
		sizer1.Add(self.GetParent().but_readco, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().but_fitwin, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().but_fitwidth, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().text_size, 1, wx.EXPAND)
		sizer2.Add(self.GetParent().but_size1, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().com_sigma, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmin, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmax, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_contrastapply, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_bright, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_invert, 2, wx.EXPAND | wx.LEFT, 10)
		sizer4.Add(self.GetParent().text_boxsize_ref, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().text_boxsize, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().but_boxsize, 2, wx.EXPAND)
		sizer4.Add(self.GetParent().text_cursorRad, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().but_saveparticles, 3, wx.EXPAND)
		sizer.Add(sizer1, 5, wx.EXPAND)
		sizer.Add(sizer2, 2, wx.EXPAND | wx.LEFT, 10)
		sizer.Add(sizer3, 5, wx.EXPAND | wx.LEFT, 10)
		sizer.Add(sizer4, 3, wx.EXPAND | wx.LEFT, 10)		
		self.SetSizer(sizer)

		self.Bind(wx.EVT_BUTTON, self.GetParent().OnButCloseAll, id = self.ID_BUTCLOSEALL)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnOpen, id = self.ID_BUTOPEN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnButClose, id = self.ID_BUTCLOSE)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnComFiles, id = self.ID_COMFILES)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnReadCo, id=self.ID_READCO)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFitWin, id = self.ID_FITWIN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFitWidth, id = self.ID_FITWIDTH)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSize1, id = self.ID_SIZE1)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnSigma, id = self.ID_COMSIGMA)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnContrastApply, id = self.ID_CONTRASTAPPLY)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnInvert, id = self.ID_INVERT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnBoxSize, id = self.ID_BOXSIZE)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSaveParticles, id = self.ID_SAVEPARTICLES)


class Panel1_M2(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)


class Panel_M2(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)



# =============================================== #
# ---------- Mode 3: Montage Screening ---------- #
# =============================================== #

# (1) Most of "self.*" parameters are for "current opened image stack / file set"
# (2) The properties of "the displayed particle on the current window" are in the list "self.dispParts"

class MainPanelM3(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)


		# ----- Initial variables ----- #

		self.dispParts = []		# A list of the displayed_particle class
		self.disp_select = ''		# Text control to input selection
		self.dispFile = ''		# Image stack file path
		self.dispSelection = []		# Selection of frames in the stack
		self.dispCurSel = -1		# Pointer of 'self.dispSelection'
		self.batchMark = -1		# Batch marker particle ID
		self.mag = 1.0
		self.starnum = 0		# number of '#' in the file name (file set marker)
		self.spin_selid_value = 1	# Spin control selection ID

		self.distanceList = []		# A list of distance lines

		self.ch_contrast = -1		# Contrast Original (not auto contrast)
		self.ch_grpsz = -1		# Group size (member number) not shown
		self.ch_showid = -1		# Particle ID not shown
		self.ch_screen = -1		# Screen OFF
		self.GetParent().statusbar.SetStatusText('Screen OFF.', 0)

		self.curx = 0			# Top left position for the next drawn image
		self.cury = 0
		self.pageList = []		# One display screen page for the particle images


		# ----- Main Layout ----- #

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel0 = Panel0_M3(self, -1)			# !!Tool panel Constructed from class
		sizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		self.panel = Panel_M3(self, -1)				# Main image window
		sizer.Add(self.panel, 1, wx.EXPAND)
		self.SetSizer(sizer)



	# ---------- "Panel0" events ---------- #

	def OnClear(self, event):
		self.dispParts = []		# clear all selected display_particles
		self.curx = 0
		self.cury = 0
		self.distanceList = []		# clear all distance lines
		self.panel.Refresh()
		self.GetParent().statusbar.SetStatusText('', 2)

	def OnQOpen(self, event):
		path = ''
		dlg = wx.FileDialog(self, 'Open one image stack file', self.GetParent().cwd, '', '*', wx.OPEN)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
		dlg.Destroy()
		if path == '':
			return
		self.GetParent().cwd = os.path.dirname(path)

		if path != '':
			self.starnum = 0		# Reset marker for image stack
			self.dispFile = path
			self.text_file.SetValue(path)

			img = Image.open(path)
			self.total = modpil.CountFrame(img)
			self.dispSelection = xrange(self.total)
			if len(self.dispSelection) > 0:
				self.dispCurSel = 0
			else:
				self.dispCurSel = -1

			self.LoadPart()				# Load all particles in the image stack


	def LoadPart(self):					# Use self.dispFile/dispSelection/dispFrame
		if len(self.dispSelection) == 0 or self.dispCurSel == -1:
			return

		if self.dispCurSel == 0 and self.ch_screen == 1:	# Load markers when the file is first loaded and SCREEN is ON
			self.curx = 0					# if screen ON, Always start fresh page
			self.cury = 0

			self.markerlist = []				# Make a screen marker list for every particle
			for item in xrange(self.total):
				self.markerlist.append(-1)
			for ct in [1,2,3,4]:				# Load the marker from previously saved files
				svmsfile = os.path.dirname(self.dispFile) + '/SVMS' + str(ct) + '_' + os.path.splitext(os.path.basename(self.dispFile))[0] + '.plt'
				if os.path.exists(svmsfile):
					f = open(svmsfile)
					for line in f:
						partid = int(float(line.strip('\n'))) - 1
						self.markerlist[partid] = ct
					f.close()

		if self.curx == 0 and self.cury == 0:		# Clear old memory if starting a new page
			self.dispParts = []

		mag = float(self.text_mag.GetValue())
		self.mag = mag
		winx, winy = self.panel.GetSize()

		dispCurSelStart = self.dispCurSel		# Record the current starting 


		while self.dispCurSel < len(self.dispSelection):

			if self.starnum == 0:	# Open image stack
				img = Image.open(self.dispFile)
				img.seek(self.dispSelection[self.dispCurSel])
			else:			# Open file set
				curname = str(self.dispSelection[self.dispCurSel] + 1).zfill(self.starnum)
				curpath = self.dispFile.replace('#'*self.starnum, curname)
				img = Image.open(curpath)
			sizex, sizey = img.size
			newsizex = int(sizex * mag)
			newsizey = int(sizey * mag)
				

			nextx = self.curx + newsizex + 1
			nexty = self.cury + newsizey + 1
			if nextx > winx:
				self.curx = 0
				self.cury = nexty
				nexty = self.cury + newsizey + 1
			if nexty > winy:				# Turn to a new page
				self.curx = 0
				self.cury = 0
				if self.dispCurSel == 0:
					self.dispParts = []		# Clear current screen if start a new file
				else:
					statusinfo = '[%d-%d] shown. %d remained. (Shift+)Middle:Back/Forward.' % \
							(self.dispSelection[dispCurSelStart]+1, self.dispSelection[self.dispCurSel-1]+1, len(self.dispSelection) - self.dispCurSel)
					self.GetParent().statusbar.SetStatusText(statusinfo, 2)
					self.panel.Refresh()						
					return				# Stop if in the middle of a file

			if self.ch_contrast == -1:		# Original contrast
				imgmin, imgmax = img.getextrema()
				img_contrast = modpil.Contrast(img, imgmin, imgmax, 0)
			else:					# Contrast 3 Sigma
				stat = modpil.StatCal(img)
				img_contrast = modpil.Contrast_sigma(img, stat, 3)
			if mag == 1:
				partbmp = modpil.ImgToBmp(img_contrast)
			else:
				partbmp = modpil.ResizeToBmp(img_contrast, newsizex, newsizey)

			# Get the number of group member for every particle (averages)
			grpsz = 0
			if self.ch_grpsz == 1:
				grpfile1 = os.path.dirname(self.dispFile) + '/sel/sel%s.dat' % str(self.dispSelection[self.dispCurSel]+1).zfill(5)
				grpfile2 = os.path.dirname(self.dispFile) + '/sel/sel%s.dat' % str(self.dispSelection[self.dispCurSel]+1).zfill(3)
				if os.path.exists(grpfile1):
					grpsz = len(self.getnumlist(grpfile1))
				elif os.path.exists(grpfile2):
					grpsz = len(self.getnumlist(grpfile2))
				else:
					grpsz = 0

			# Displayed particles, last item = 'Hit type'(-1(no hit), 1, 2, 3, 4)
			if self.ch_screen == 1:
				self.dispParts.append([partbmp, self.curx, self.cury, newsizex, newsizey, self.dispFile, self.dispSelection[self.dispCurSel], self.markerlist[self.dispSelection[self.dispCurSel]], grpsz])
			else:
				self.dispParts.append([partbmp, self.curx, self.cury, newsizex, newsizey, self.dispFile, self.dispSelection[self.dispCurSel], -1, grpsz])

			self.curx += (newsizex + 1)
			self.dispCurSel += 1


		if self.curx > 0:			# Get the starting point to open the next image stack file
			self.cury += (newsizey + 1)
			self.curx = 0

		#self.GetParent().statusbar.SetStatusText('', 2)
		statusinfo = '[%d-%d] shown. %d remained. (Shift+)Middle:Back/Forward.' % \
				(self.dispSelection[dispCurSelStart]+1, self.dispSelection[self.dispCurSel-1]+1, len(self.dispSelection) - self.dispCurSel)
		self.GetParent().statusbar.SetStatusText(statusinfo, 2)
		self.panel.Refresh()
		

	def OnFile(self, event):
		path = ''
		dlg = wx.FileDialog(self, 'Open one image stack file', self.GetParent().cwd, '', '*', wx.OPEN)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
		dlg.Destroy()
		if path == '':
			return
		self.GetParent().cwd = os.path.dirname(path)

		self.dispFile = path
		self.text_file.SetValue(path)

#		self.curFrame = 0
#		self.LoadPart()


	def OnSelect(self, event):
		path = ''
		wildcard = "All files(*)|*|SPIDER file(*.dat)|*.dat|PLT file(*.plt)|*.plt"
		dlg = wx.FileDialog(self, 'Open one selection file', self.GetParent().cwd, '', wildcard, wx.OPEN)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
		dlg.Destroy()
		if path == '':
			return
		self.GetParent().cwd = os.path.dirname(path)
		self.text_select.SetValue(path)


	def OnOpen(self, event):
		sel = self.text_select.GetValue()
		numlist = []
		if sel != '':
			sel_starnum = sel.count('#')
			if sel_starnum > 0:
				curselid = self.spin_selid.GetValue()
				self.spin_selid_value = curselid	# Save the current selID in display
				curname = str(curselid).zfill(sel_starnum)
				curpath = sel.replace('#'*sel_starnum, curname)
				if os.path.exists(curpath):
					numlist = self.getnumlist(curpath)
				else:
					print 'Can NOT find selection file: %s' % curpath
			else:
				numlist = self.getnumlist(sel)

				#if os.path.exists(sel):
				#	numlist = self.getnumlist(sel)
				#else:
				#	print 'Can NOT find selection file: %s' % sel

		path = self.text_file.GetValue()
		self.dispFile = path
		self.starnum = os.path.basename(path).count('#')	# Marker for image stack / file set
									# Can be e.g. 'cycle_###/angles###.dat'


		self.dispSelection = []		# The list of (particle ID number-1)

		if self.starnum == 0:		# Single file/stack
			if not os.path.exists(path):
				print '%s is NOT found!' % path
				return
			else:
				img = Image.open(path)
				self.total = modpil.CountFrame(img)
				if len(numlist) == 0:
					numlist = range(1, self.total + 1)	# to compensate the following (item-1)

				for item in numlist:
					listitem = item - 1	# 0-starting system
					if listitem < self.total:
						self.dispSelection.append(listitem)

		else:				# File set
			self.total = 10**self.starnum
			if len(numlist) == 0:				# If not specified, try all possible file name numbers
				numlist.extend(range(1, self.total))	# only count to 99..., so no (+ 1)

			for item in numlist:
				curname = str(item).zfill(self.starnum)
				curpath = path.replace('#'*self.starnum, curname)
				if os.path.exists(curpath):
					self.dispSelection.append(item - 1)	# 0-starting system

		if len(self.dispSelection) > 0:
			self.dispCurSel = 0
		else:
			self.dispCurSel = -1

		self.LoadPart()				# Load all (specified) particles in the image stack OR all existing files in the fileset


	def getnumlist(self, list_rawinput):
		# Get an integer number list from a raw input
		# The input is "raw input": an integer number list, or the 1st column of SPIDER/PLT file
		numlist = []
		name = ''.join(list_rawinput.split())

		if name.replace(',','').replace('-','').isdigit():
			for content in name.split(','):
				if content.isdigit():
					numlist.append(int(content))
				else:
					min_max = content.split('-')
					cycle_min = int(min_max[0])
					cycle_max = int(min_max[1])
					numlist.extend(range(cycle_min, cycle_max + 1))
		else:
			if not os.path.exists(name):
				return numlist

			elif name[-4:] == '.dat' or name[-4:] == '.DAT':
				f = open(name)
				for line in f:
					if not line.lstrip().startswith(';'):
						value = line.strip('\n').split()
						numlist.append(int(float(value[2])))
				f.close()
			elif name[-4:] == '.plt':
				f = open(name)
				for line in f:
					value = line.strip('\n').split()
					numlist.append(int(float(value[0])))
				f.close()
		return numlist


	def OnContrast(self, event):
		self.ch_contrast = self.ch_contrast * (-1)
		self.dispFile = self.text_file.GetValue()
		self.disp_select = self.text_select.GetValue()
		self.mag = float(self.text_mag.GetValue())
		self.RefreshPanel0()

	def OnGrpsz(self, event):
		self.ch_grpsz = self.ch_grpsz * (-1)
		self.dispFile = self.text_file.GetValue()
		self.disp_select = self.text_select.GetValue()
		self.mag = float(self.text_mag.GetValue())
		self.RefreshPanel0()

	def OnShowID(self, event):
		self.ch_showid = self.ch_showid * (-1)
		self.dispFile = self.text_file.GetValue()
		self.disp_select = self.text_select.GetValue()
		self.mag = float(self.text_mag.GetValue())
		self.RefreshPanel0()

	def OnScreen(self, event):
		self.GetParent().statusbar.SetStatusText('', 2)
		self.distanceList = []		# clear all distance lines
		self.ch_screen = self.ch_screen * (-1)
		if self.ch_screen == -1:
			self.GetParent().statusbar.SetStatusText('Screen OFF.', 0)
		else:
			self.GetParent().statusbar.SetStatusText('Screen ON! (1)Left,(2)Right,(3)Ctrl-Left,(4)Ctrl-Right. Ctrl+Shft:Batch', 0)

		self.dispFile = self.text_file.GetValue()
		self.disp_select = self.text_select.GetValue()
		self.mag = float(self.text_mag.GetValue())
		self.RefreshPanel0()

		self.dispParts = []		# clear all selected display_particles
		self.curx = 0
		self.cury = 0
		self.panel.Refresh()


	def RefreshPanel0(self):
		self.panel0.Destroy()		# The purpose of this is to change the panel; note: all bindings are also removed
						# sizer/layout of the main panel is required to show the newly recontructed panel0
		self.panel0 = Panel0_M3(self, -1)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		sizer.Add(self.panel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.Layout()



class Panel0_M3(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.ID_CLEAR = 12
		self.ID_QOPEN = 14	
		self.ID_FILE = 16
		self.ID_SELECT = 18
		self.ID_OPEN = 20
		self.ID_CONTRAST = 22
		self.ID_GRPSZ = 23
		self.ID_SHOWID = 24
		self.ID_SCREEN = 26

		if self.GetParent().ch_contrast == -1:
			text_contrast = 'CNT OFF'
		else:
			text_contrast = 'CNT  ON'
		if self.GetParent().ch_grpsz == -1:
			text_grpsz = 'SZ OFF'
		else:
			text_grpsz = 'SZ  ON'
		if self.GetParent().ch_showid == -1:
			text_showid = 'ID OFF'
		else:
			text_showid = 'ID  ON'
		if self.GetParent().ch_screen == -1:
			text_screen = 'SCRN OFF'
		else:
			text_screen = 'SCRN ON!'

		self.GetParent().but_clear = wx.Button(self, self.ID_CLEAR, 'Clear')
		self.GetParent().but_qopen = wx.Button(self, self.ID_QOPEN, 'Q_Open')
		self.GetParent().but_file = wx.Button(self, self.ID_FILE, 'File')
		self.GetParent().text_file = wx.TextCtrl(self, -1, self.GetParent().dispFile, size=(60, -1))
		self.GetParent().but_select = wx.Button(self, self.ID_SELECT, 'Select')
		self.GetParent().text_select = wx.TextCtrl(self, -1, self.GetParent().disp_select, size=(60,-1))
		self.GetParent().but_open = wx.Button(self, self.ID_OPEN, '->Open')
		self.GetParent().st_mag = wx.StaticText(self, -1, 'Mag:')
		self.GetParent().text_mag = wx.TextCtrl(self, -1, str(self.GetParent().mag), size=(50,-1))
		self.GetParent().but_contrast = wx.Button(self, self.ID_CONTRAST, text_contrast)
		self.GetParent().but_grpsz = wx.Button(self, self.ID_GRPSZ, text_grpsz)
		self.GetParent().but_showid = wx.Button(self, self.ID_SHOWID, text_showid)
		self.GetParent().but_screen = wx.Button(self, self.ID_SCREEN, text_screen)
		self.GetParent().spin_selid = wx.SpinCtrl(self, -1, str(self.GetParent().spin_selid_value), size=(20, -1), min=0, max=999999999)

		sizer = wx.BoxSizer(wx.HORIZONTAL)
		sizera = wx.BoxSizer(wx.HORIZONTAL)
		sizera.Add(self.GetParent().but_qopen, 1, wx.EXPAND | wx.RIGHT, 2)

		sizerb = wx.BoxSizer(wx.VERTICAL)
		sizer1 = wx.BoxSizer(wx.HORIZONTAL)
		sizer2 = wx.BoxSizer(wx.HORIZONTAL)
		sizer11 = wx.BoxSizer(wx.HORIZONTAL)
		sizer12 = wx.BoxSizer(wx.HORIZONTAL)
		sizer13 = wx.BoxSizer(wx.HORIZONTAL)
		sizer11.Add(self.GetParent().but_file, 1, wx.EXPAND)
		sizer11.Add(self.GetParent().text_file, 6, wx.EXPAND)
		sizer12.Add(self.GetParent().st_mag, 0, wx.TOP, 5)
		sizer12.Add(self.GetParent().text_mag, 1, wx.EXPAND)
		sizer13.Add(self.GetParent().but_contrast, 1, wx.EXPAND | wx.RIGHT, 5)
		sizer13.Add(self.GetParent().but_grpsz, 1, wx.EXPAND | wx.RIGHT, 5)
		sizer13.Add(self.GetParent().but_showid, 1, wx.EXPAND)
		sizer1.Add(sizer11, 6, wx.EXPAND)
		sizer1.Add(sizer12, 1, wx.EXPAND)
		sizer1.Add(sizer13, 4, wx.EXPAND)

		sizer21 = wx.BoxSizer(wx.HORIZONTAL)
		sizer22 = wx.BoxSizer(wx.HORIZONTAL)
		sizer23 = wx.BoxSizer(wx.HORIZONTAL)
		sizer21.Add(self.GetParent().but_select, 1, wx.EXPAND)
		sizer21.Add(self.GetParent().text_select, 6, wx.EXPAND)
		sizer22.Add(self.GetParent().spin_selid, 1, wx.EXPAND)
		sizer23.Add(self.GetParent().but_open, 1, wx.EXPAND | wx.RIGHT, 5)
		sizer23.Add(self.GetParent().but_clear, 1, wx.EXPAND | wx.RIGHT, 5)
		sizer23.Add(self.GetParent().but_screen, 1, wx.EXPAND)
		sizer2.Add(sizer21, 6, wx.EXPAND)
		sizer2.Add(sizer22, 1, wx.EXPAND)
		sizer2.Add(sizer23, 4, wx.EXPAND)

		sizerb.Add(sizer1, 1, wx.EXPAND)
		sizerb.Add(sizer2, 1, wx.EXPAND)
		sizer.Add(sizera, 1, wx.EXPAND)
		sizer.Add(sizerb, 12, wx.EXPAND)
		self.SetSizer(sizer)

		# ----- Control panel (panel0) functions ----- #

		self.Bind(wx.EVT_BUTTON, self.GetParent().OnClear, id=self.ID_CLEAR)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnQOpen, id=self.ID_QOPEN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFile, id=self.ID_FILE)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSelect, id=self.ID_SELECT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnOpen, id=self.ID_OPEN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnContrast, id=self.ID_CONTRAST)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnGrpsz, id=self.ID_GRPSZ)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnShowID, id=self.ID_SHOWID)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnScreen, id=self.ID_SCREEN)




class Panel_M3(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.distanceStart = False
		self.distanceEnd = False


		# ----- Major panel (panel) functions ----- #

		self.Bind(wx.EVT_PAINT, self.OnPaint)
		self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
		self.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
		self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
		self.Bind(wx.EVT_MIDDLE_UP, self.OnMiddleUp)

	# ---------- "Panel" events ---------- #

	def OnPaint(self, event):		

		self.SetBackgroundColour(wx.BLACK)
		if len(self.GetParent().dispParts) == 0:
			return

		stinfo = 'Mag= %.3f' % self.GetParent().mag
		self.GetParent().GetParent().statusbar.SetStatusText(stinfo, 1)

        	dc = wx.PaintDC(self)
#		self.PrepareDC(dc)
		memDC = wx.MemoryDC()

		# Draw displayed particles
		winsizex, winsizey = self.GetSize()
		drawbmp = wx.EmptyBitmap(winsizex, winsizey)
		memDC.SelectObject(drawbmp)
		memDC.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
		memDC.SetBackground(wx.Brush(wx.BLACK))
		memDC.Clear()						# Clears the device context using the current background brush.

		memDC.SetBrush(wx.Brush(wx.BLACK, wx.TRANSPARENT))
		for part in self.GetParent().dispParts:
			memDC.DrawBitmap(part[0], part[1], part[2])	# Draw particle

			if part[7] != -1:				# Draw marker circles
				if part[7] == 1:
					memDC.SetPen(wx.Pen(wx.GREEN, 3))
				elif part[7] == 2:
					memDC.SetPen(wx.Pen(wx.BLUE, 3))
				elif part[7] == 3:
					memDC.SetPen(wx.Pen(wx.RED, 3))
				elif part[7] == 4:
					memDC.SetPen(wx.Pen(wx.WHITE, 3))
				memDC.DrawEllipse(part[1], part[2], part[3], part[4])

			if part[6] == self.GetParent().batchMark:	# Draw marker frame for Batch selection start/end particle
				memDC.SetPen(wx.Pen(wx.WHITE, 5, wx.SHORT_DASH))
				memDC.DrawRectangle(part[1]+3, part[2]+3, part[3]-3, part[4]-3)

		if self.GetParent().batchMark > -1:
			stinfo = 'Batch selection activated! ID:%d' % (self.GetParent().batchMark + 1)
		#else:
		#	stinfo = 'No batch selection.'
			self.GetParent().GetParent().statusbar.SetStatusText(stinfo, 2)


		# Draw distance lines
		if len(self.GetParent().distanceList) > 0:
			font = wx.Font(12, wx.ROMAN, wx.NORMAL, wx.BOLD)
		        memDC.SetFont(font)
			memDC.SetTextForeground(wx.RED)

			for distance in self.GetParent().distanceList:
				coorlist = distance[0]
				#memDC.SetPen(wx.Pen(wx.RED, 2, wx.SHORT_DASH))
				memDC.SetPen(wx.Pen(wx.BLACK, 5, wx.SOLID))
				memDC.DrawLine(coorlist[0], coorlist[1], coorlist[2], coorlist[3])

				#memDC.SetPen(wx.Pen(wx.RED, 2, wx.SOLID))
				#memDC.DrawText(distance[1], coorlist[0], coorlist[1])


		# Real drawing
		dc.Blit(0, 0, winsizex, winsizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)

		# Draw particle ID
		if self.GetParent().ch_showid == 1:				# Settings to Draw particle ID
			font = wx.Font(7, wx.ROMAN, wx.NORMAL, wx.NORMAL)	# options: wx.BOLD

			for part in self.GetParent().dispParts:
				idtext = str(part[6]+1)
				idtextExtent = self.GetFullTextExtent(idtext, font)
				idbmp = wx.EmptyBitmap(idtextExtent[0], idtextExtent[1])
				memDC.SelectObject(idbmp)
				memDC.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
				memDC.SetBackground(wx.Brush(wx.BLACK))
				memDC.Clear()
			        memDC.SetFont(font)
				memDC.SetTextForeground(wx.WHITE)
			        memDC.DrawText(idtext, 0, 0)
				dc.Blit(part[1], part[2], idtextExtent[0], idtextExtent[1], memDC, 0, 0, wx.COPY, True)
				memDC.SelectObject(wx.NullBitmap)

		# Draw group size (number)
		if self.GetParent().ch_grpsz == 1:				# Settings to Draw
			font = wx.Font(7, wx.ROMAN, wx.NORMAL, wx.NORMAL)	# options: wx.BOLD

			for part in self.GetParent().dispParts:
				sztext = str(part[8])
				sztextExtent = self.GetFullTextExtent(sztext, font)
				szbmp = wx.EmptyBitmap(sztextExtent[0], sztextExtent[1])
				memDC.SelectObject(szbmp)
				memDC.SetBrush(wx.Brush(wx.BLACK, wx.SOLID))
				memDC.SetBackground(wx.Brush(wx.BLACK))
				memDC.Clear()
			        memDC.SetFont(font)
				memDC.SetTextForeground(wx.WHITE)
			        memDC.DrawText(sztext, 0, 0)
				dc.Blit(part[1], part[2]+part[4]-sztextExtent[1], sztextExtent[0], sztextExtent[1], memDC, 0, 0, wx.COPY, True)
				memDC.SelectObject(wx.NullBitmap)


	def OnMiddleUp(self, event):
		if event.ControlDown():
			if len(self.GetParent().distanceList) > 0:
				self.GetParent().distanceList.pop()			# Remove the last distance line
				stinfo = 'Last distance line removed!'
			else:
				stinfo = 'No distance line to remove!'
			self.GetParent().GetParent().statusbar.SetStatusText(stinfo, 2)
			self.distanceStart = False
			self.distanceEnd = False
			self.GetParent().panel.Refresh()
		else:
			# Middle Mouse Button is up, continue to load the rest of images in the stack
			if event.ShiftDown():					# Backword
				self.GetParent().dispCurSel += (-2) * len(self.GetParent().dispParts)
				if self.GetParent().dispCurSel < 0:
					self.GetParent().dispCurSel = 0
										# Forward
			if self.GetParent().dispCurSel < (len(self.GetParent().dispSelection)-1):
				self.GetParent().LoadPart()

	def OnLeftUp(self, event):
		if len(self.GetParent().dispParts) == 0:
			return

		pt = event.GetPosition()
		if self.GetParent().ch_screen == 1:		# Screen ON
			match = self.HitTest(pt)
			if match == -1:		# no hit
				return

			partid = self.GetParent().dispParts[match][6]		# 0-based numbering
			if event.ShiftDown() and event.ControlDown():		# "Batch marker" action
				if self.GetParent().batchMark == partid:
					self.GetParent().batchMark = -1		# Remove BatchMarker by clicking the same particle
				else:
					self.GetParent().batchMark = partid	# Activate BatchMarker by clicking a particle

			else:
				if event.ShiftDown():
					marker = -1	# remove the marker
				elif event.ControlDown():
					marker = 3
				else:
					marker = 1

				if self.GetParent().batchMark > -1:		# BatchID effective
					match_index = self.GetParent().dispSelection.index(partid)
					batch_index = self.GetParent().dispSelection.index(self.GetParent().batchMark)
					if match_index > batch_index:
						batchlist = self.GetParent().dispSelection[batch_index:match_index+1]
					else:
						batchlist = self.GetParent().dispSelection[match_index:batch_index+1]
					self.GetParent().batchMark = -1		# Reset BatchMarker
				else:
					batchlist = [partid]

				for item in batchlist:
					self.GetParent().markerlist[item] = marker
				self.MarkerSave()			# Save new marker list

				for part in self.GetParent().dispParts:		# Change current display page
					if part[6] in batchlist:
						part[7] = marker
			self.GetParent().panel.Refresh()

		else:
			if event.ControlDown():				# Record the starting point of distance line
				self.distanceStartX = pt[0]
				self.distanceStartY = pt[1]
				self.distanceStart = True		# This will remain True unless (Ctrl+Middle)
				self.distanceEnd = False
				stinfo = 'Distance starting [%d, %d]' % (self.distanceStartX, self.distanceStartY)
				self.GetParent().GetParent().statusbar.SetStatusText(stinfo, 2)


	def OnRightUp(self, event):
		if len(self.GetParent().dispParts) == 0:
			return

		pt = event.GetPosition()
		if self.GetParent().ch_screen == 1:
			match = self.HitTest(pt)
			if match == -1:		# no hit
				return	
			if event.ControlDown():
				marker = 4
			else:
				marker = 2

			partid = self.GetParent().dispParts[match][6]		# 0-based numbering
			if self.GetParent().batchMark > -1:		# BatchID effective
				match_index = self.GetParent().dispSelection.index(partid)
				batch_index = self.GetParent().dispSelection.index(self.GetParent().batchMark)
				if match_index > batch_index:
					batchlist = self.GetParent().dispSelection[batch_index:match_index+1]
				else:
					batchlist = self.GetParent().dispSelection[match_index:batch_index+1]
				self.GetParent().batchMark = -1		# Reset BatchMarker
			else:
				batchlist = [partid]

			for item in batchlist:
				self.GetParent().markerlist[item] = marker
			self.MarkerSave()			# Save new marker list

			for part in self.GetParent().dispParts:		# Change current display page
				if part[6] in batchlist:
					part[7] = marker
			self.GetParent().panel.Refresh()

		else:
			if event.ControlDown():					# Record the ending point of distance line
				if not self.distanceStart:			# skip if the starting point is not yet set
					return
				self.distanceEndX = pt[0]
				self.distanceEndY = pt[1]
				distance = math.sqrt((self.distanceEndX - self.distanceStartX)**2 + (self.distanceEndY - self.distanceStartY)**2)
				distanceShow = '%.1f' % (distance/self.GetParent().mag)
				stinfo = 'Distance ending [%d, %d], %.2f pixels' % (self.distanceEndX, self.distanceEndY, distance)
				self.GetParent().GetParent().statusbar.SetStatusText(stinfo, 2)
	
				if self.distanceEnd:				# (modifying the end point) remove the last item before appending
					self.GetParent().distanceList.pop()
	
				self.GetParent().distanceList.append([[self.distanceStartX, self.distanceStartY, self.distanceEndX, self.distanceEndY], distanceShow])
				self.distanceEnd = True				# Indicating the end point is set
				self.GetParent().panel.Refresh()


	def HitTest(self, pt):
		match = -1
		goon = True
		i = 0
		while goon and i < len(self.GetParent().dispParts):
			part = self.GetParent().dispParts[i]
			rect = wx.Rect(part[1], part[2], part[3], part[4])
			if rect.InsideXY(pt[0], pt[1]):
				match = i
				goon = False
				self.GetParent().GetParent().statusbar.SetStatusText('%d is hit' % (i+1), 1)
			i += 1
		return match

	def MarkerSave(self):
		outputlist = [[],[],[],[]]
		i = 0
		for marker in self.GetParent().markerlist:
			if marker != -1:
				outputlist[marker-1].append(i)
			i += 1

		mtype = 1
		for sublist in outputlist:
			svmsfile = os.path.dirname(self.GetParent().dispFile) + '/SVMS' + str(mtype) + '_' + os.path.splitext(os.path.basename(self.GetParent().dispFile))[0] + '.plt'
			if len(sublist) == 0:
				if os.path.exists(svmsfile):
					os.remove(svmsfile)
			else:
				f = open(svmsfile, 'w')
				for item in sublist:
					line = '%d\n' % (item+1)	# save in 1-starting format
					f.write(line)
				f.close()
			mtype += 1


	def OnWheel(self, event):
		event.Skip()


# =========================================== #
# ---------- Mode 4: Dual Viewer ---------- #
# =========================================== #

class MainPanelM4(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		sizer = wx.BoxSizer(wx.VERTICAL)
		self.panel0 = Panel0_M4(self, -1)			# !!Tool panel Constructed from class
		sizer.Add(self.panel0, 0, wx.EXPAND | wx.BOTTOM, 5)
		self.splitter = wx.SplitterWindow(self, -1, style = wx.BORDER_SUNKEN)
		self.panel1 = Panel_M4(self.splitter, 0)		# V1 window
		self.panel2 = Panel_M4(self.splitter, 1)		# V2 window
	
		self.panel1.intro = 'V1 window'
		self.panel2.intro = 'V2 window'

		self.splitter.SetMinimumPaneSize(5)
		self.splitter.SplitVertically(self.panel1, self.panel2)
		sizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizer(sizer)


		# ---------- Starting values ----------#
		self.modePartSyn = 0		# Syn Particles between panels
		self.modeShLink = 0		# Syn mag and shift between panels
		self.resDis = 0.0		# Residual angle fit distance
		self.resDisMax = 0.0		# Residual angle fit distance max value
		self.resDisMaxID = 0		# Residual angle fit distance max value particle ID


	def ClearStatus(self):
		self.GetParent().statusbar.SetStatusText('', 0)
		self.GetParent().statusbar.SetStatusText('', 1)
		self.GetParent().statusbar.SetStatusText('', 2)

	def SetStatus(self):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		com_file = self.com_files.GetSelection()
		if com_file == 0:
			stinfo0 = 'Min=%.1f, Max=%.1f, Avg=%.1f, Std=%.1f, Size=%s' % \
				(self.panel1.imgstat[3], self.panel1.imgstat[4],self.panel1.imgstat[0],self.panel1.imgstat[1], self.panel1.img_ori.size)
		elif com_file == 1:
			stinfo0 = 'Min=%.1f, Max=%.1f, Avg=%.1f, Std=%.1f, Size=%s' % \
				(self.panel2.imgstat[3], self.panel2.imgstat[4],self.panel2.imgstat[0],self.panel2.imgstat[1], self.panel2.img_ori.size)
		else:
			stinfo0 = 'Display adjustment: V1 V2 both Active !!'
		
		if self.panel1.imagefile.path != '':
			mag1 = '%.2f' % self.panel1.mag
		else:
			mag1 = ''
		if self.panel2.imagefile.path != '':
			mag2 = '%.2f' % self.panel2.mag
		else:
			mag2 = ''
		stinfo1 = 'Mag= [V1]%s, [V2]%s' % (mag1, mag2)

		stinfo2 = 'SynPart= '
		if self.modePartSyn == 0:
			stinfo2 += 'V1 V2 unlinked'
		elif self.modePartSyn == 1:
			stinfo2 += 'V1 >>>> V2'
		elif self.modePartSyn == 2:
			stinfo2 += 'V1 <<<< V2'
		else:
			stinfo2 += 'V1 V2 interlinked'
		stinfo2 += '    Axis_V2= %.2f' % self.panel2.imagefile.rotang
		stinfo2 += '    AngleFit Res= %.1f, MaxID= %d(%.1f)' % (self.resDis, self.resDisMaxID, self.resDisMax)
		self.GetParent().statusbar.SetStatusText(stinfo0, 0)
		self.GetParent().statusbar.SetStatusText(stinfo1, 1)
		self.GetParent().statusbar.SetStatusText(stinfo2, 2)


	# ---------- "Panel0" events ---------- #

	def OnButCloseAll(self, event):

		dlg = wx.MessageDialog(self, 'Do you want to reset all parameters and close all opened files?', 'Are you sure?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			self.com_files.Clear()
			self.panel1.imagefile.path = ''
			self.panel2.imagefile.path = ''
			self.panel1.Refresh()
			self.panel2.Refresh()
			self.GetParent().ClearStatusBar()
			self.com_files.SetSelection(0)

			self.modePartSyn = 0
			self.com_partsyn.SetSelection(0)
			self.modeShLink = 0
			self.com_shlink.SetSelection(0)

			self.text_phi.SetValue('0.00')
			self.text_theta.SetValue('0.00')
			self.text_shx.SetValue('0')
			self.text_shy.SetValue('0')
			self.text_tiltv2.SetValue('0.00')
			self.panel2.imagefile.rotang = 0.0
			self.resDis = 0.0

			self.ClearStatus()
		dlg.Destroy()

		self.panel1.firstfileopen = True
		self.panel2.firstfileopen = True

	def OnOpenV1(self, event):
		self.panel1.OpenFile()
		path = self.panel1.imagefile.path
		if os.path.exists(path):
			self.com_files.SetSelection(1)
			file1 = self.com_files.GetValue()
			self.com_files.Clear()
			newfile0 = 'V1: %s (%d)' % (os.path.basename(path), len(self.panel1.imagefile.xylist))
			newfile2 = 'V1 V2 LOCKED (%d) (%d)' % (len(self.panel1.imagefile.xylist),len(self.panel2.imagefile.xylist) )
			self.com_files.Append(newfile0)
			self.com_files.Append(file1)
			self.com_files.Append(newfile2)
			self.com_files.SetSelection(0)

	def OnOpenV2(self, event):
		self.panel2.OpenFile()
		path = self.panel2.imagefile.path
		if os.path.exists(path):
			self.com_files.SetSelection(0)
			file0 = self.com_files.GetValue()
			self.com_files.Clear()
			newfile1 = 'V2: %s (%d)' % (os.path.basename(path), len(self.panel2.imagefile.xylist))
			newfile2 = 'V1 V2 Active (%d) (%d)' % (len(self.panel1.imagefile.xylist),len(self.panel2.imagefile.xylist) )
			self.com_files.Append(file0)
			self.com_files.Append(newfile1)
			self.com_files.Append(newfile2)
			self.com_files.SetSelection(1)

	def OnComFiles(self, event):						# Set the active V1/V2 for display adjustment
		if self.com_files.GetSelection() == 2:				# Lock the display setting of V2 to that of V1
			self.panel2.sigmaLevel = self.panel1.sigmaLevel		# Only lock and syn SIGMA, do not adjust fine contrast
			self.panel2.invertMarker = self.panel1.invertMarker
			self.panel2.mag = self.panel1.mag
			self.panel2.brightness = self.panel1.brightness
			self.panel2.DrawNewImg()				# New drawing based on: sigmaLevel, invertMarker, mag, brightness
		self.SetStatus()

	def RefreshComFiles(self):
		# Refresh combo_box to show particle number, called by panel1/2
		oldsel = self.com_files.GetSelection()
		self.com_files.Clear()
		item1 = 'V1: %s (%d)' % (os.path.basename(self.panel1.imagefile.path), len(self.panel1.imagefile.xylist))
		item2 = 'V2: %s (%d)' % (os.path.basename(self.panel2.imagefile.path), len(self.panel2.imagefile.xylist))
		item3 = 'V1 V2 Active (%d) (%d)' % (len(self.panel1.imagefile.xylist), len(self.panel2.imagefile.xylist))
		self.com_files.Append(item1)
		self.com_files.Append(item2)
		self.com_files.Append(item3)
		self.com_files.SetSelection(oldsel)	# "SetSelection" show the new value

	def OnRefco(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return
		fsel = self.com_files.GetSelection()
		if fsel == 2:
			return

		if fsel == 0:
			path = self.panel1.imagefile.path
		else:
			path = self.panel2.imagefile.path
		basename = os.path.splitext(os.path.basename(path))
		autof = os.path.dirname(path) + '/ref/SVCO_' + basename[0] + '.dat'	# Load "ref/SVCO" coordinate file, if present
		if not os.path.exists(autof):
			return
		autolist = self.LoadCoor(autof)
		if len(autolist) == 0:
			return

		shortname = os.path.basename(autof)
		dlgtext = '\n%s contains %d coors. Reading %d coors ...\n\n!!! ALL unsaved coors will be LOST !!!' % (shortname, len(autolist), len(autolist))
		dlg = wx.MessageDialog(self, dlgtext, 'Read in Coordinate?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			if fsel == 0:
				self.panel1.imagefile.xylist = []
				self.panel1.imagefile.xylist.extend(autolist)
				self.panel1.Refresh()
			else:
				self.panel2.imagefile.xylist = []
				self.panel2.imagefile.xylist.extend(autolist)
				self.panel2.Refresh()
			self.RefreshComFiles()

	def LoadCoor(self, coorf):
		xylist = []
		f = open(coorf)
		for line in f:
			if not line.strip().startswith(';'):
				content = line.split()
				x = int(float(content[2])) - 1
				y = int(float(content[3])) - 1
				xylist.append([x,y])
		f.close()
		return xylist

	def OnFitWin(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		if self.com_files.GetSelection() == 0:
			self.panel1.FitWin()
		elif self.com_files.GetSelection() == 1:
			self.panel2.FitWin()
		else:
			self.panel1.FitWin()
			self.panel2.FitWin()

	def OnMag(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		if self.com_files.GetSelection() == 0:
			self.panel1.MagApply()
		elif self.com_files.GetSelection() == 1:
			self.panel2.MagApply()
		else:
			self.panel1.MagApply()
			self.panel2.MagApply()

	def OnSigma(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		if self.com_files.GetSelection() == 0:
			self.panel1.SigmaApply()
		elif self.com_files.GetSelection() == 1:
			self.panel2.SigmaApply()
		else:
			self.panel1.SigmaApply()
			self.panel2.SigmaApply()

	def OnContrastApply(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		if self.com_files.GetSelection() == 0:
			self.panel1.ContrastApply()
		elif self.com_files.GetSelection() == 1:
			self.panel2.ContrastApply()
		else:	# this fine contrast adjustment is disabled for V1/V2-locked MODE, only adjust brightness
			brightness = self.spin_bright.GetValue()
			self.panel1.brightness = brightness
			self.panel2.brightness = brightness
			self.panel1.DrawNewImg()
			self.panel2.DrawNewImg()
							

	def OnInvert(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		if self.com_files.GetSelection() == 0:
			self.panel1.InvertApply()
		elif self.com_files.GetSelection() == 1:
			self.panel2.InvertApply()
		else:
			self.panel1.InvertApply()
			self.panel2.InvertApply()

	def OnBoxSize(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		self.panel1.boxsize = int(float(self.text_boxsizeV1.GetValue()))
		self.panel2.boxsize = int(float(self.text_boxsizeV2.GetValue()))
		idsize = int(float(self.text_idsize.GetValue()))
		if idsize <= 0:
			self.text_idsize.SetValue(0)
			idsize = 0
		self.panel1.idsize = idsize
		self.panel2.idsize = idsize
		self.panel1.Refresh()
		self.panel2.Refresh()
		
	def OnSplitWin(self, event):
		winx, winy = self.GetSize()
		sashPos = int(winx / 2.0) + 1
		self.splitter.SetSashPosition(sashPos)

	def OnComPartSyn(self, event):
		self.modePartSyn = self.com_partsyn.GetSelection()
		self.SetStatus()

	def OnPartSynApply(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		# This is only active when mode = 1 or 2
		modePartSyn = self.com_partsyn.GetSelection()
		if modePartSyn == 1 or modePartSyn == 2:
			dlgtext = 'Synchronize All Particles!!!\n\n  '
			if modePartSyn == 1:
				dlgtext += 'V1 >>>> V2'
			elif modePartSyn == 2:
				dlgtext += 'V1 <<<< V2'
 
			dlg = wx.MessageDialog(self, dlgtext, 'Are You Sure?', wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        		if dlg.ShowModal() == wx.ID_YES:
				if modePartSyn == 1:
					self.PartSyn(self.panel1, self.panel2)
				else:
					self.PartSyn(self.panel2, self.panel1)
			dlg.Destroy()

	def PartSyn(self, plstart, plend):
		# Synchronize all particles!
		v2axis = self.panel2.imagefile.rotang
		if plstart.id == 0:
			boxsize = int(float(self.text_boxsizeV2.GetValue()))
			boxhalf = int(boxsize / 2)
			limitx = self.panel2.sizex_ori - boxhalf
			limity = self.panel2.sizey_ori - boxhalf
			tmplist = []
			tmplist.extend(self.panel1.imagefile.xylist)
			transxy = self.V1xytoV2(tmplist)
			compxy = []
			if v2axis == 0:
				compxy.extend(transxy)
			else:	# Inplane rotate coor back to compare with non-rotated V2 img
				compxy = self.RotateXY(self.panel2, transxy, v2axis)

			self.panel1.imagefile.xylist = []
			self.panel2.imagefile.xylist = []
			ct = -1
			for xy in compxy:
				ct += 1
				if xy[0] > boxhalf and xy[0] < limitx:
					if xy[1] > boxhalf and xy[1] < limity:
						self.panel1.imagefile.xylist.append(tmplist[ct])
						self.panel2.imagefile.xylist.append(transxy[ct])
		else:
			boxsize = int(float(self.text_boxsizeV1.GetValue()))
			boxhalf = int(boxsize / 2)
			limitx = self.panel1.sizex_ori - boxhalf
			limity = self.panel1.sizey_ori - boxhalf
			tmplist = []
			tmplist.extend(self.panel2.imagefile.xylist)
			transxyout = self.V2xytoV1(tmplist)	# This is directly compared to the V1 img limits.

			self.panel1.imagefile.xylist = []
			self.panel2.imagefile.xylist = []
			ct = -1
			for xy in transxyout:
				ct += 1
				if xy[0] > boxhalf and xy[0] < limitx:
					if xy[1] > boxhalf and xy[1] < limity:
						self.panel2.imagefile.xylist.append(tmplist[ct])
						self.panel1.imagefile.xylist.append(xy)
		self.panel1.Refresh()
		self.panel2.Refresh()
		self.RefreshComFiles()
		self.SetStatus()


	def V1xytoV2(self, v1list):
		if len(v1list) == 0:
			return
		sinPhi, cosPhi, sinTheta, cosTheta, shx, shy = self.GetAng()
		v2list = []
		for item in v1list:
			x = int(item[0]*cosPhi*cosTheta + item[1]*sinPhi*cosTheta + shx)
			y = int(-item[0]*sinPhi + item[1]*cosPhi + shy)
			v2list.append([x,y])
		return v2list

	def V2xytoV1(self, v2list):
		if len(v2list) == 0:
			return
		sinPhi, cosPhi, sinTheta, cosTheta, shx, shy = self.GetAng()
		v1list = []
		for item in v2list:
			x = int(-(item[1]-shy)*sinPhi + cosPhi*(item[0]-shx)/cosTheta)
			y = int((item[1]-shy)*cosPhi + sinPhi*(item[0]-shx)/cosTheta)
			v1list.append([x,y])
		return v1list

	def V1xytoV2_local(self, v1):		# Auto determine V2 coordiante from a single V1 (using closest 3 V1 sets)
		ct = -1
		test = []	# [dx**2+dy**2, ct]
		for item in self.panel1.imagefile.xylist:
			ct += 1
			testval = (item[0]-v1[0])**2 + (item[1]-v1[1])**2
			test.append([testval, ct])
		test.sort()

		v1xy = []
		v2xy = []
		for item in test[1:4]:		# Note that v1 itself is included, so skip the first one (v1 itself)
			v1xy.append(self.panel1.imagefile.xylist[item[1]])
			v2xy.append(self.panel2.imagefile.xylist[item[1]])
		phi, theta = self.AngFit(v1xy, v2xy)
		shx, shy = self.avgAB(v1xy, v2xy, phi, theta)

		sinPhi = math.sin(math.radians(phi))
		cosPhi = math.cos(math.radians(phi))
		sinTheta = math.sin(math.radians(theta))
		cosTheta = math.cos(math.radians(theta))

		x = int(v1[0]*cosPhi*cosTheta + v1[1]*sinPhi*cosTheta + shx)
		y = int(-v1[0]*sinPhi + v1[1]*cosPhi + shy)
		return [x,y]

	def V2xytoV1_local(self, v2):
		ct = -1
		test = []	# [dx**2+dy**2, ct]
		for item in self.panel2.imagefile.xylist:
			ct += 1
			testval = (item[0]-v2[0])**2 + (item[1]-v2[1])**2
			test.append([testval, ct])
		test.sort()

		v1xy = []
		v2xy = []
		for item in test[1:4]:
			v1xy.append(self.panel1.imagefile.xylist[item[1]])
			v2xy.append(self.panel2.imagefile.xylist[item[1]])
		phi, theta = self.AngFit(v1xy, v2xy)
		shx, shy = self.avgAB(v1xy, v2xy, phi, theta)

		sinPhi = math.sin(math.radians(phi))
		cosPhi = math.cos(math.radians(phi))
		sinTheta = math.sin(math.radians(theta))
		cosTheta = math.cos(math.radians(theta))

		x = int(-(v2[1]-shy)*sinPhi + cosPhi*(v2[0]-shx)/cosTheta)
		y = int((v2[1]-shy)*cosPhi + sinPhi*(v2[0]-shx)/cosTheta)
		return [x,y]

	#def InplaneRt(self, xylist, phi):
	#	# Inplane rotation via phi angle
	#	sinPhi = math.sin(math.radians(phi))
	#	cosPhi = math.cos(math.radians(phi))
	#	ipxylist = []
	#	for item in xylist:
	#		x = int(item[0] * cosPhi + item[1] * sinPhi)
	#		y = int(-item[0]* sinPhi + item[1] * cosPhi)
	#		ipxylist.append([x,y])
	#	return ipxylist

	def GetAng(self):
		phi = float(self.text_phi.GetValue())
		theta = float(self.text_theta.GetValue())
		shx = int(float(self.text_shx.GetValue()))
		shy = int(float(self.text_shy.GetValue()))

				# --------------------------------------------------
		phi = -phi	# Phi angle: true tilt axis related to image Y axis
				# --------------------------------------------------

		sinPhi = math.sin(math.radians(phi))
		cosPhi = math.cos(math.radians(phi))
		sinTheta = math.sin(math.radians(theta))
		cosTheta = math.cos(math.radians(theta))
		return sinPhi, cosPhi, sinTheta, cosTheta, shx, shy

	def OnComShLink(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		modeShLink = self.com_shlink.GetSelection()
		self.modeShLink = modeShLink
		if modeShLink == 1:
			self.ShLink(self.panel1, self.panel2)	# Apply the mag and shift from panel1 to panel2

	def ShLink(self, plstart, plend):
		# Called by 'modeShLink', apply the mag and shift from plstart to plend
		if plend.mag != plstart.mag:
			plend.mag = plstart.mag
			plend.bitmap_sizex = int(plend.mag * plend.sizex_ori)
			plend.bitmap_sizey = int(plend.mag * plend.sizey_ori)
			plend.bitmap = modpil.ResizeToBmp(plend.img_contrast, plend.bitmap_sizex, plend.bitmap_sizey)

		# 'The image point at the window center' of two panels fulfill the transform
		# To calculate the transform, the image point must convert back to original size!
		winsizex, winsizey = plstart.GetSize()
		ctimgpt_ori = [[(winsizex/2 - plstart.bitmap_x)/plstart.mag, (winsizey/2 - plstart.bitmap_y)/plstart.mag]]
		if plstart.id == 0:
			ctimgpt_end = self.V1xytoV2(ctimgpt_ori)
		else:
			ctimgpt_end = self.V2xytoV1(ctimgpt_ori)

		winsizex, winsizey = plend.GetSize()
		plend.bitmap_x = int(winsizex/2 - ctimgpt_end[0][0]*plstart.mag)
		plend.bitmap_y = int(winsizey/2 - ctimgpt_end[0][1]*plstart.mag)
		plend.Refresh()
		self.SetStatus()


	def OnTiltV2(self, event):
		# Rotate the V2 image by (-)"text_tiltv2", so that Y axis is the tilt axis
		if self.panel2.imagefile.path == '':
			return
		rotang = float(self.text_tiltv2.GetValue())
		self.TiltSet(self.panel2, rotang)

	def TiltSet(self, panel, rotang):
		# Rotate XY coordinates
		#if rotang != panel.imagefile.rotang:
		#drotang = rotang*(-1.0) + panel.imagefile.rotang
		#newxylist = self.RotateXY(panel, panel.imagefile.xylist, drotang)

		newxylist = self.RotateXY(panel, panel.imagefile.xylist, panel.imagefile.rotang-rotang)
		panel.imagefile.xylist = []
		panel.imagefile.xylist.extend(newxylist)

		panel.imagefile.rotang = rotang		# Update the setting

		# Rotate the image by rotang
		if rotang == 0.0:
			panel.imagefile.img = panel.img_ori
			panel.imagefile.img_invert = panel.img_ori_invert
		else:
			panel.imagefile.img = panel.img_ori.rotate(rotang*(-1.0))
			panel.imagefile.img_invert = panel.img_ori_invert.rotate(rotang*(-1.0))
		if panel.invertMarker == -1:
			panel.img_contrast = modpil.Contrast_sigma(panel.imagefile.img_invert, panel.imagefile.stat_invert, panel.sigmaLevel)
			panel.imgstat = panel.imagefile.stat_invert
		else:
			panel.img_contrast = modpil.Contrast_sigma(panel.imagefile.img, panel.imagefile.stat, panel.sigmaLevel)
			panel.imgstat = panel.imagefile.stat
		panel.bitmap = modpil.ResizeToBmp(panel.img_contrast, panel.bitmap_sizex, panel.bitmap_sizey)

		panel.Refresh()
		self.SetStatus()

	def RotateXY(self, panel, xylist, rotang):
		# Generate a rotated XY coordinate list; "rotang" in degrees
		if len(xylist) == 0:
			return []

		centerx = panel.sizex_ori / 2
		centery = panel.sizey_ori / 2
		xylist_rot = []
		for item in xylist:
			dx = item[0]-centerx
			dy = -item[1]+centery		# NOTE: PIL convention, Y is reversed
			ang = math.radians(rotang)
			newx = int(centerx + dx * math.cos(ang) - dy * math.sin(ang))
			newy = int(centery + (dx * math.sin(ang) + dy * math.cos(ang))*(-1))
#			ang0 = math.atan2(dy, dx)	# atan2: compute the correct quadrant for the angle
#			ang = math.radians(math.degrees(ang0)+rotang)
#			ang = ang0 + math.radians(rotang)
#			r = math.sqrt(dx**2 + dy**2)
#			newx = centerx + r*math.cos(ang)
#			newy = centery - r*math.sin(ang)
			xylist_rot.append([newx, newy])
		return xylist_rot


	# ---------- Tilt angle related functions ----------#

	def OnAngFit(self, event):
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		lenxyV1 = len(self.panel1.imagefile.xylist)
		lenxyV2 = len(self.panel2.imagefile.xylist)
		minlenxy = min(lenxyV1, lenxyV2)
		if minlenxy < 3:
			return
		v1xy = self.panel1.imagefile.xylist[:minlenxy]
		v2xy = self.panel2.imagefile.xylist[:minlenxy]
		phi, theta = self.AngFit(v1xy, v2xy)
		shx, shy = self.avgAB(v1xy, v2xy, phi, theta)

		# Calculate average residual distance (indicating how good the fit is)
		disanglist = self.disAngle(v1xy, v2xy, phi, theta, shx, shy)
		sumZsq = sum(disanglist)
		self.resDis = math.sqrt(sumZsq/minlenxy)
		tmpanglist = []
		tmpanglist.extend(disanglist)
		tmpanglist.sort()
		self.resDisMax = math.sqrt(tmpanglist[-1])
		self.resDisMaxID = disanglist.index(tmpanglist[-1]) + 1
		self.SetStatus()

				# --------------------------------------------------
		phi = -phi	# Phi angle: true tilt axis related to image Y axis
				# --------------------------------------------------

		setphi = '%.2f' % phi
		settheta = '%.2f' % theta
		self.text_phi.SetValue(setphi)
		self.text_theta.SetValue(settheta)
		self.text_shx.SetValue(str(shx))
		self.text_shy.SetValue(str(shy))


	def AngFit(self, ulist, tlist):
		# Master function (3 steps) to get tilt angle fit. 
		# NOTE: 'theta' only uses COS, no SIN, -/+ is not distinguished
		phi1, theta1 = self.searchPhiTheta(ulist, tlist, range(-90,90,2), range(0,90,2))
		phiList = []
		thetaList = []
		for ct in range(-20,20):
			phiList.append(phi1 + ct*0.1)
			thetaList.append(theta1 + ct*0.1)
		phi2, theta2 = self.searchPhiTheta(ulist, tlist, phiList, thetaList)
		phiList = []
		thetaList = []
		for ct in range(-10,10):
			phiList.append(phi1 + ct*0.01)
			thetaList.append(theta1 + ct*0.01)
		phi3, theta3 = self.searchPhiTheta(ulist, tlist, phiList, thetaList)
		return phi3, theta3

	def searchPhiTheta(self, ulist, tlist, phiList, thetaList):
		# Exhaustive search the min value of "disAngle"
		test = []
		for phi in phiList:
			for theta in thetaList:
				# (1) use initial phi and theta ---> average a and b
				iniA, iniB = self.avgAB(ulist, tlist, phi, theta)
				# (2) initial phi, average a and b ---> theta
				disAng = sum(self.disAngle(ulist, tlist, phi, theta, iniA, iniB))
				test.append([disAng, phi, theta])
		test.sort()
		# best phi/theta
		return test[0][1], test[0][2]

	def avgAB(self, ulist, tlist, phi, theta):
		sinPhi = math.sin(math.radians(phi))
		cosPhi = math.cos(math.radians(phi))
		cosTheta = math.cos(math.radians(theta))
		sumA = 0
		sumB = 0
		ct = 0
		for item in ulist:
			x = item[0]*cosPhi*cosTheta + item[1]*sinPhi*cosTheta
			y = -item[0]*sinPhi + item[1]*cosPhi
			sumA += (tlist[ct][0] - x)
			sumB += (tlist[ct][1] - y)
			ct += 1
		avgA = int(sumA/ct + 0.5) - 1
		avgB = int(sumB/ct + 0.5) - 1
		return avgA, avgB

	def disAngle(self, ulist, tlist, phi, theta, a, b):
		# Return a list of the distance square (Z**2)
		sinPhi = math.sin(math.radians(phi))
		cosPhi = math.cos(math.radians(phi))
		cosTheta = math.cos(math.radians(theta))
		disanglist = []
		ct = 0
		for item in ulist:
			x = item[0]
			y = item[1]
			# Calculate the distance square (Z**2)
			zsq = (x*cosPhi*cosTheta + y*sinPhi*cosTheta + a - tlist[ct][0])**2 + (-x*sinPhi + y*cosPhi + b - tlist[ct][1])**2
			disanglist.append(zsq)
			ct += 1
		return disanglist


	#---------- Save particles ----------#

	def OnSaveParticles(self, event):
		# Save 2 files: SVCO for V1 and V2
		# Format V1: x,y
		# Format V2: x,y,psi(0.0),theta,phi,z. 	(NOTE: z is assumed +, but could be - (with theta))
		if self.panel1.imagefile.path == '' or self.panel2.imagefile.path == '':
			return

		lenPartV1 = len(self.panel1.imagefile.xylist)
		lenPartV2 = len(self.panel2.imagefile.xylist)
		phi = self.text_phi.GetValue()
		theta = self.text_theta.GetValue()
		shx = int(self.text_shx.GetValue())
		shy = int(self.text_shy.GetValue())

		dlgtext = 'Particle number: V1= %d, V2= %d\nTilt_axis= %s, Tilt_angle= %s, Tilt_axis_V2= %.2f' % (lenPartV1, lenPartV2, phi, theta, self.panel2.imagefile.rotang)

		if lenPartV1 == 0 or lenPartV2 == 0:
			dlgtext = 'Warning! Particle number can NOT be 0!\n\n' + dlgtext
			dlg = wx.MessageDialog(self, dlgtext, 'Can NOT Save!',
					wx.OK | wx.ICON_INFORMATION)
        		dlg.ShowModal()
			dlg.Destroy()
			return

		if lenPartV1 != lenPartV2:
			dlgtext = 'Warning! Particle numbers do NOT match!\n\n' + dlgtext
			dlg = wx.MessageDialog(self, dlgtext, 'Can NOT Save!',
					wx.OK | wx.ICON_INFORMATION)
        		dlg.ShowModal()
			dlg.Destroy()
			return

		dlg = wx.MessageDialog(self, dlgtext, 'Save Particles and Angles?',
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_INFORMATION)
        	if dlg.ShowModal() == wx.ID_YES:
			basenameV1 = os.path.splitext(os.path.basename(self.panel1.imagefile.path))
			fV1 = os.path.dirname(self.panel1.imagefile.path) + '/SVCO_' + basenameV1[0] + '.dat'
			basenameV2 = os.path.splitext(os.path.basename(self.panel2.imagefile.path))
			fV2 = os.path.dirname(self.panel2.imagefile.path) + '/SVCO_' + basenameV2[0] + '.dat'
			sinPhi = math.sin(math.radians(float(phi)))
			cosPhi = math.cos(math.radians(float(phi)))
			sinTheta = math.sin(math.radians(float(theta)))

			# Rotate the panel2 xylist back to match original (not rotated) image
			v2xylist = self.RotateXY(self.panel2, self.panel2.imagefile.xylist, self.panel2.imagefile.rotang)

			f1 = open(fV1, 'w')
			f2 = open(fV2, 'w')
			f2.write(' ; %s (Recorded XYxy are with 1 pixel extra to match SPIDER format.)\n' % str(datetime.datetime.now()))
			f2.write(' ; X=xcosPhicosTheta+ysinPhicosTheta+shx, Y=-xsinPhi+ycosPhi+shy, Z=xcosPhisinTheta+ysinPhisinTheta\n')
			f2.write(' ; Where Phi= (-)Tilt_axis, Theta= Tilt_ang\n')
			f2.write(' ;               X        Y        Z   Tilt_axis Tilt_ang Tilt_axis(V2) dx      dy      x      y\n')
			i = 0
			for xy1 in self.panel1.imagefile.xylist:
				line = '%8d%3d%8d%8d\n' % (i+1, 2, xy1[0]+1, xy1[1]+1)
				f1.write(line)
				z = xy1[0]*cosPhi*sinTheta + xy1[1]*sinPhi*sinTheta

				xy2 = v2xylist[i]
				line = '%8d%3d%8d%8d%10.2f%10.2f%10.2f%10.2f%8d%8d%8d%8d\n' % (i+1, 10, xy2[0]+1, xy2[1]+1, z, \
					float(phi), float(theta), self.panel2.imagefile.rotang, shx, shy, xy1[0]+1, xy1[1]+1)
				f2.write(line)
				i += 1
			f1.close()
			f2.close()
		dlg.Destroy()


class Panel0_M4(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.ID_SPLITWIN = 209
		self.ID_ANGFIT = 211
		self.ID_COMSHLINK = 213
		self.ID_PARTSYN = 215
		self.ID_PARTSYNAPPLY = 217
		self.ID_BUTCLOSEALL = 225
		self.ID_V1 = 227
		self.ID_V2 = 229
		self.ID_COMFILES = 231
		self.ID_REFCO = 232
		self.ID_FITWIN = 233
		self.ID_MAG = 235
		self.ID_COMSIGMA = 237
		self.ID_CONTRASTAPPLY = 241
		self.ID_INVERT = 242
		self.ID_BOXSIZE = 245
		self.ID_IDSIZE = 246
		self.ID_SAVEPARTICLES = 247
		self.ID_TILTV2 = 249

		self.GetParent().but_splitwin = wx.Button(self, self.ID_SPLITWIN, 'SplitWIN')
		self.GetParent().but_angfit = wx.Button(self, self.ID_ANGFIT, 'Tilt_axis/angle/dX/dY-->')
		self.GetParent().text_phi = wx.TextCtrl(self, -1, '0.00', size=(20,-1))
		self.GetParent().text_theta = wx.TextCtrl(self, -1, '0.00', size=(20,-1))
		self.GetParent().text_shx = wx.TextCtrl(self, -1, '0', size=(20,-1))
		self.GetParent().text_shy = wx.TextCtrl(self, -1, '0', size=(20,-1))
		self.GetParent().text_tiltv2 = wx.TextCtrl(self, -1, '0.00', size=(20,-1))
		self.GetParent().but_tiltv2 = wx.Button(self, self.ID_TILTV2, '->Set V2_axis')
		choices_shlink = ['Shift V1V2 unlinked', 'Shift V1V2 LINKED !!']
	        self.GetParent().com_shlink = wx.ComboBox(self, self.ID_COMSHLINK, size=(30, -1), choices=choices_shlink, style=wx.CB_READONLY)
		self.GetParent().com_shlink.SetSelection(0)
		choices_partsyn = ['V1 - V2', 'V1-->V2', 'V1<--V2', 'V1<->V2']
	        self.GetParent().com_partsyn = wx.ComboBox(self, self.ID_PARTSYN, size=(30, -1), choices=choices_partsyn, style=wx.CB_READONLY)
		self.GetParent().com_partsyn.SetSelection(0)
		self.GetParent().but_partsynapply = wx.Button(self, self.ID_PARTSYNAPPLY, 'Syn Part<-')

		self.GetParent().but_closeall = wx.Button(self, self.ID_BUTCLOSEALL, 'XX')
		self.GetParent().but_v1 = wx.Button(self, self.ID_V1, 'V1->')
		self.GetParent().but_v2 = wx.Button(self, self.ID_V2, 'V2->')
		choices_files = ['V1:', 'V2:', 'V1 V2 Active']
		self.GetParent().com_files = wx.ComboBox(self, self.ID_COMFILES, size=(50, -1), choices=choices_files, style=wx.CB_READONLY)
		self.GetParent().com_files.SetSelection(0)
		self.GetParent().but_refco = wx.Button(self, self.ID_REFCO, '->refCO')
		self.GetParent().but_fitwin = wx.Button(self, self.ID_FITWIN, 'FIT Win', size=(20, -1))
		self.GetParent().text_size = wx.TextCtrl(self, -1, '1.0', size=(20,-1))
		self.GetParent().but_mag = wx.Button(self, self.ID_MAG, '->Mag', size=(20, -1))
		sigma_choices = ['SIGMA 0.5', 'SIGMA 1', 'SIGMA 1.5', 'SIGMA 2', 'SIGMA 2.5', 'SIGMA 3', 'SIGMA 3.5', 'SIGMA 4', 'SIGMA 5']
		self.GetParent().sigma_values = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5]
	        self.GetParent().com_sigma = wx.ComboBox(self, self.ID_COMSIGMA, size=(30, -1), choices=sigma_choices, style=wx.CB_READONLY)
		self.GetParent().com_sigma.SetSelection(5)
		self.GetParent().spin_contrastmin = wx.SpinCtrl(self, -1, '100', size=(20, -1), min=0, max=1000)
		self.GetParent().spin_contrastmax = wx.SpinCtrl(self, -1, '600', size=(20, -1), min=0, max=1000)
		self.GetParent().but_contrastapply = wx.Button(self, self.ID_CONTRASTAPPLY, '->D<-', size=(20, -1))
		self.GetParent().spin_bright = wx.SpinCtrl(self, -1, '0', size=(20, -1), min=-255, max=255)
		self.GetParent().but_invert = wx.Button(self, self.ID_INVERT, 'INVT', size=(20, -1))
		self.GetParent().text_boxsizeV1 = wx.TextCtrl(self, -1, '64', size=(20, -1))
		self.GetParent().text_boxsizeV2 = wx.TextCtrl(self, -1, '64', size=(20, -1))
		self.GetParent().but_boxsize = wx.Button(self, self.ID_BOXSIZE, '->BOX<-', size=(20, -1))
		self.GetParent().text_idsize = wx.TextCtrl(self, -1, '10', size=(20, -1))
		self.GetParent().but_saveparticles = wx.Button(self, self.ID_SAVEPARTICLES, 'SAVE particles,angles', size=(50, -1))

		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer_1st = wx.BoxSizer(wx.HORIZONTAL)
		sizer11 = wx.BoxSizer(wx.HORIZONTAL)
		sizer12 = wx.BoxSizer(wx.HORIZONTAL)
		sizer13 = wx.BoxSizer(wx.HORIZONTAL)
		sizer14 = wx.BoxSizer(wx.HORIZONTAL)
		sizer11.Add(self.GetParent().but_splitwin, 1, wx.EXPAND)
		sizer11.Add(self.GetParent().but_partsynapply, 1, wx.EXPAND)
		sizer11.Add(self.GetParent().com_partsyn, 1, wx.EXPAND)
		sizer11.Add(self.GetParent().com_shlink, 1, wx.EXPAND)
		sizer12.Add(self.GetParent().text_boxsizeV1, 1, wx.EXPAND)
		sizer12.Add(self.GetParent().text_boxsizeV2, 1, wx.EXPAND)
		sizer12.Add(self.GetParent().but_boxsize, 2, wx.EXPAND)
		sizer12.Add(self.GetParent().text_idsize, 1, wx.EXPAND)
		sizer13.Add(self.GetParent().but_angfit, 3, wx.EXPAND)
		sizer13.Add(self.GetParent().text_phi, 1, wx.EXPAND)
		sizer13.Add(self.GetParent().text_theta, 1, wx.EXPAND)
		sizer13.Add(self.GetParent().text_shx, 1, wx.EXPAND)
		sizer13.Add(self.GetParent().text_shy, 1, wx.EXPAND)
		sizer14.Add(self.GetParent().text_tiltv2, 1, wx.EXPAND)
		sizer14.Add(self.GetParent().but_tiltv2, 2, wx.EXPAND)

		sizer_1st.Add(sizer11, 6, wx.EXPAND)
		sizer_1st.Add(sizer12, 4, wx.EXPAND | wx.LEFT, 10)
		sizer_1st.Add(sizer13, 7, wx.EXPAND | wx.LEFT, 10)
		sizer_1st.Add(sizer14, 3, wx.EXPAND | wx.LEFT, 10)

		sizer_2nd = wx.BoxSizer(wx.HORIZONTAL)
		sizer1 = wx.BoxSizer(wx.HORIZONTAL)
		sizer2 = wx.BoxSizer(wx.HORIZONTAL)
		sizer3 = wx.BoxSizer(wx.HORIZONTAL)
		sizer4 = wx.BoxSizer(wx.HORIZONTAL)
		sizer1.Add(self.GetParent().but_closeall, 1, wx.EXPAND)
		sizer1.Add(self.GetParent().but_v1, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().but_v2, 2, wx.EXPAND)
		sizer1.Add(self.GetParent().com_files, 6, wx.EXPAND)
		sizer1.Add(self.GetParent().but_refco, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().but_fitwin, 2, wx.EXPAND)
		sizer2.Add(self.GetParent().text_size, 1, wx.EXPAND)
		sizer2.Add(self.GetParent().but_mag, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().com_sigma, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmin, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_contrastmax, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_contrastapply, 2, wx.EXPAND)
		sizer3.Add(self.GetParent().spin_bright, 1, wx.EXPAND)
		sizer3.Add(self.GetParent().but_invert, 1, wx.EXPAND)
		sizer4.Add(self.GetParent().but_saveparticles, 1, wx.EXPAND)

		sizer_2nd.Add(sizer1, 6, wx.EXPAND)
		sizer_2nd.Add(sizer2, 4, wx.EXPAND | wx.LEFT, 10)
		sizer_2nd.Add(sizer3, 7, wx.EXPAND | wx.LEFT, 10)
		sizer_2nd.Add(sizer4, 3, wx.EXPAND | wx.LEFT, 10)
		sizer.Add(sizer_1st, 1, wx.EXPAND)		
		sizer.Add(sizer_2nd, 1, wx.EXPAND)		
		self.SetSizer(sizer)

		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSplitWin, id = self.ID_SPLITWIN)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnComPartSyn, id = self.ID_PARTSYN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnPartSynApply, id = self.ID_PARTSYNAPPLY)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnComShLink, id = self.ID_COMSHLINK)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnAngFit, id = self.ID_ANGFIT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnTiltV2, id = self.ID_TILTV2)

		self.Bind(wx.EVT_BUTTON, self.GetParent().OnButCloseAll, id = self.ID_BUTCLOSEALL)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnOpenV1, id = self.ID_V1)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnOpenV2, id = self.ID_V2)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnComFiles, id = self.ID_COMFILES)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnRefco, id = self.ID_REFCO)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnFitWin, id = self.ID_FITWIN)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnMag, id = self.ID_MAG)
		self.Bind(wx.EVT_COMBOBOX, self.GetParent().OnSigma, id = self.ID_COMSIGMA)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnContrastApply, id = self.ID_CONTRASTAPPLY)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnInvert, id = self.ID_INVERT)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnBoxSize, id = self.ID_BOXSIZE)
		self.Bind(wx.EVT_BUTTON, self.GetParent().OnSaveParticles, id = self.ID_SAVEPARTICLES)




class Panel_M4(wx.Panel):
	def __init__(self, parent, id):
		wx.Panel.__init__(self, parent, id)

		self.id = id

		#---------- Draw/Mouse Events ----------#

		self.Bind(wx.EVT_PAINT, self.OnPaint)
		self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
		self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
		self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
		self.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
		self.Bind(wx.EVT_MOTION, self.OnMotion)
		self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
		self.Bind(wx.EVT_RIGHT_DCLICK, self.OnRightDclick)


		#---------- Initial values ----------#

		self.statusbar = self.GetParent().GetParent().GetParent().statusbar
		self.com_files = self.GetParent().GetParent().com_files
		self.imagefile = ImageFile('')						# Class constructed
		self.firstfileopen = True						# image initial size, position, etc. fit to win, otherwise use previous values
		self.cdir = self.GetParent().GetParent().GetParent().cwd
		self.sigmaLevel = 3
		self.brightness = 0
		self.invertMarker = 1		# 1: original, -1: invert contrast
		self.boxsize = 64
		self.idsize = 10

		self.zoombox = ZoomBox(wx.EmptyBitmap(1,1), (0, 0))	# Initial Mock zoombox, not shown
		self.zoombox.shown = False

		#---------- Notes about image formation in the panel ----------#
		# When loading image:
		#	self.img_ori = self.imagefile.img
		#	self.img_ori_invert = self.imagefile.img_invert
		# Prepare image by first rotation, and then invert:
		#	self.img_ori -> rotate -> self.imagefile.img -> invert -> self.imagefile.img_invert
		# Contrast applied with sigma or fine values, and then resize for real display:
		#	-> self.imagefile.img_contrast -> resize -> self.imagefile.bitmap



	#---------- Panel Functions ----------#

	def SetStatus(self):
		self.GetParent().GetParent().SetStatus()

	def OpenFile(self):
		dlg = wx.FileDialog(self, 'Open image file', self.cdir, '', '*', wx.OPEN)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
		else:
			path = ''
		dlg.Destroy()
		if path == '':
			return
		if not os.path.exists(path):
			return
		self.cdir = os.path.dirname(path)
		self.imagefile.path = path

		# Read and load the image file
		try:
			img = Image.open(path)
			self.imagefile.img = img

			basename = os.path.splitext(os.path.basename(path))
			coorf = os.path.dirname(path) + '/SVCO_' + basename[0] + '.dat'		# Load coordinate file, if present
			self.imagefile.xylist = []
			if os.path.exists(coorf):
				self.imagefile.xylist = self.LoadCoor(coorf)
		except IOError:
			print 'Can NOT open ', path
		self.LoadImage()

	def LoadCoor(self, coorf):
		xylist = []
		f = open(coorf)
		for line in f:
			if not line.strip().startswith(';'):
				content = line.split()
				x = int(float(content[2])) - 1
				y = int(float(content[3])) - 1
				xylist.append([x,y])
		f.close()
		return xylist

	def LoadImage(self):
		self.invertMarker = 1		# Autoset the image contrast as original (non-inverted)

		self.imagefile.stat = modpil.Stat(self.imagefile.path)
		self.imagefile.InvertContrast()			# Get inverted image and stat_invert

		self.img_ori = self.imagefile.img
		self.img_ori_invert = self.imagefile.img_invert
		self.sizex_ori, self.sizey_ori = self.img_ori.size
		if self.invertMarker == 1:
			self.imgstat = self.imagefile.stat
		else:
			self.imgstat = self.imagefile.stat_invert

		self.img_contrast = modpil.Contrast_sigma(self.img_ori, self.imgstat, self.sigmaLevel)

		if self.firstfileopen:
			self.FitWin()					# Set all initial settings(map, size, pos, mag)
			self.firstfileopen = False
		else:							# Using previous settings
			self.bitmap_sizex = int(float(self.sizex_ori) * self.mag)
			self.bitmap_sizey = int(float(self.sizey_ori) * self.mag)
			self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmaLevel)		# Set the values of contrast min/max fields
		self.GetParent().GetParent().spin_contrastmin.SetValue(fmin)
		self.GetParent().GetParent().spin_contrastmax.SetValue(fmax)

		self.imagefile.rotang = 0.0
		self.Refresh()					# Draw image
		self.SetStatus()


	def FitWin(self):				# All initial settings when the 1st file is opened
		# Image fit into the window size
		winsizex, winsizey = self.GetSize()
		if float(winsizey)/self.sizey_ori <= float(winsizex)/self.sizex_ori:
			self.bitmap_sizey = winsizey
			self.bitmap_sizex = int(self.bitmap_sizey * (float(self.sizex_ori) / self.sizey_ori))
		else:
			self.bitmap_sizex = winsizex
			self.bitmap_sizey = int(self.bitmap_sizex * (float(self.sizey_ori) / self.sizex_ori))
		self.bitmap_x = int((winsizex - self.bitmap_sizex)/2.0)
		self.bitmap_y = int((winsizey - self.bitmap_sizey)/2.0)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.mag = self.bitmap_sizex / float(self.sizex_ori)
		self.Refresh()
		self.SetStatus()

	def MagApply(self):
		mag = float(self.GetParent().GetParent().text_size.GetValue())
		if mag <= 0 or mag > 2:
			self.GetParent().text_size.SetValue('1.0')
			return
		self.mag = mag

		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)		# Save old size for centering
		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		winsizex, winsizey = self.GetSize()
		centerx = winsizex / 2
		centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.Refresh()
		self.SetStatus()

	def SigmaApply(self):
		item = self.GetGrandParent().com_sigma.GetSelection()
		self.sigmaLevel = self.GetGrandParent().sigma_values[item]
		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast_sigma(self.imagefile.img_invert, self.imagefile.stat_invert, self.sigmaLevel)
			self.imgstat = self.imagefile.stat_invert
		else:
			self.img_contrast = modpil.Contrast_sigma(self.imagefile.img, self.imagefile.stat, self.sigmaLevel)
			self.imgstat = self.imagefile.stat
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.Refresh()

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmaLevel)
		self.GetGrandParent().spin_contrastmin.SetValue(fmin)
		self.GetGrandParent().spin_contrastmax.SetValue(fmax)


	def AutoContrastValue(self, stat, sigmalevel):
		# Set the values of contrast min & max TextCtrls
		truemin = stat[0] - stat[1] * sigmalevel
		truemax = stat[0] + stat[1] * sigmalevel
		imgmin = stat[3]
		imgmax = stat[4]
		imgrange = imgmax - imgmin
		fmin = int(1000 * (truemin - imgmin) / imgrange)
		fmax = int(1000 * (truemax - imgmin) / imgrange)
		return fmin, fmax
		
	def ContrastApply(self):
		imgmin = self.imgstat[3]
		imgmax = self.imgstat[4]
		imgrange = imgmax - imgmin
		truemin = imgmin + imgrange * 0.001 * self.GetGrandParent().spin_contrastmin.GetValue()
		truemax = imgmin + imgrange * 0.001 * self.GetGrandParent().spin_contrastmax.GetValue()
		brightness = self.GetGrandParent().spin_bright.GetValue()
		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast(self.imagefile.img_invert, truemin, truemax, brightness)
			self.imgstat = self.imagefile.stat_invert
		else:
			self.img_contrast = modpil.Contrast(self.imagefile.img, truemin, truemax, brightness)
			self.imgstat = self.imagefile.stat
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.Refresh()

	def InvertApply(self):
		self.invertMarker = self.invertMarker * (-1)

		# Prepare img by first rotation, and then invert
		if self.imagefile.rotang == 0.0:
			self.imagefile.img = self.img_ori
			self.imagefile.img_invert = self.img_ori_invert
		else:
			self.imagefile.img = self.img_ori.rotate(self.imagefile.rotang*(-1.0))
			self.imagefile.img_invert = self.img_ori_invert.rotate(self.imagefile.rotang*(-1.0))

		if self.invertMarker == -1:
			self.img_contrast = modpil.Contrast_sigma(self.imagefile.img_invert, self.imgstat, self.sigmaLevel)
			self.imgstat = self.imagefile.stat_invert
		else:
			self.img_contrast = modpil.Contrast_sigma(self.imagefile.img, self.imgstat, self.sigmaLevel)
			self.imgstat = self.imagefile.stat
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)
		self.Refresh()

		fmin, fmax = self.AutoContrastValue(self.imgstat, self.sigmaLevel)
		self.GetGrandParent().spin_contrastmin.SetValue(fmin)
		self.GetGrandParent().spin_contrastmax.SetValue(fmax)


	#---------- Panel1/2 Draw and Mouse Events ----------#

	def OnPaint(self, event):
		self.SetBackgroundColour(wx.BLACK)
		if self.imagefile.path == '':
			return

        	dc = wx.PaintDC(self)
#		self.PrepareDC(dc)
		memDC = wx.MemoryDC()

		# Draw micrograph
		drawbmp = wx.EmptyBitmap(self.bitmap_sizex, self.bitmap_sizey)
		memDC.SelectObject(drawbmp)
		memDC.Clear()
		memDC.DrawBitmap(self.bitmap, 0, 0)

		# Draw Boxes according to the xylist
		self.displist = self.imagefile.DispList(self.mag, self.boxsize)
		if len(self.displist) > 0:
			memDC.SetPen(wx.Pen(wx.GREEN, 2))
    			memDC.SetBrush(wx.Brush(wx.WHITE, wx.TRANSPARENT))
			memDC.DrawRectangleList(self.displist)

		# Draw particle ID
		if self.idsize > 0 and len(self.imagefile.xylist) > 0:
			font = wx.Font(self.idsize, wx.ROMAN, wx.NORMAL, wx.BOLD)
		        memDC.SetFont(font)
			memDC.SetTextForeground(wx.GREEN)

			i = 0
			for xy in self.imagefile.xylist:
				i += 1
				if self.id == 0:
					idx = int((xy[0]+self.GetGrandParent().panel1.boxsize/2.0)* self.mag)
				else:
					idx = int((xy[0]+self.GetGrandParent().panel2.boxsize/2.0)* self.mag)
				if self.id == 0:
					idy = int((xy[1]-self.GetGrandParent().panel1.boxsize/2.0)* self.mag)
				else:
					idy = int((xy[1]-self.GetGrandParent().panel2.boxsize/2.0)* self.mag)
				memDC.SetPen(wx.Pen(wx.GREEN, 2, wx.SOLID))
				memDC.DrawText(str(i), idx, idy)

		# Draw sub_bitmap zoom
		if self.zoombox.shown:
			self.zoombox.DrawZoomBox(memDC)

		# Real drawing
		dc.Blit(self.bitmap_x, self.bitmap_y, self.bitmap_sizex, self.bitmap_sizey, memDC, 0, 0, wx.COPY, True)
		memDC.SelectObject(wx.NullBitmap)


	def HitTest(self, pt):
		if len(self.imagefile.xylist) == 0:
			return []
		pt = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)	# True coordinate on micrograph
		hitpoints = []
		for i in xrange(len(self.displist)):
			disp = self.displist[i]
			#print disp
			if pt[0] >= disp[0] and pt[0] <= (disp[0] + disp[2]):
				if pt[1] >= disp[1] and pt[1] <= (disp[1] + disp[3]):
					hitpoints.append(i)
		return hitpoints

	def OnLeftDown(self, event):
		if self.imagefile.path == '':
			return

		pt = event.GetPosition()

		pt_img = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)
		if self.zoombox.shown:
			pt_img = self.zoombox.UnZoomXY(pt_img)
		pt = (self.bitmap_x + pt_img[0], self.bitmap_y + pt_img[1])

		hitpoints = self.HitTest(pt)
		if len(hitpoints) > 0:					# if one particle is hit, save ID and the coordinate
			self.hit_leftdown = hitpoints[0]
			self.xylist_hit = []			
			self.xylist_hit.extend(self.imagefile.xylist[self.hit_leftdown])
			self.hitPt = pt					# Saved for others, e.g. 'OnMotion' to move box
		else:
			self.hit_leftdown = -1			# -1: no hit; otherwise, hit a particle	

	def OnLeftUp(self, event):
		if self.imagefile.path == '':
			return

		#----- avoid particle operation for certain 'modelPartSyn' -----#
		modePartSyn = self.GetGrandParent().modePartSyn
		if self.id == 0:
			if modePartSyn == 2:
				return
		else:
			if modePartSyn == 1:
				return
		#-------------------------------------------------------------#

		pt = event.GetPosition()
		pt_img = (pt[0] - self.bitmap_x, pt[1] - self.bitmap_y)
		if self.zoombox.shown:
			pt_img = self.zoombox.UnZoomXY(pt_img)
		pt = (self.bitmap_x + pt_img[0], self.bitmap_y + pt_img[1])

		hitpoints = self.HitTest(pt)			# HitTest for mouse_up
		if event.ShiftDown():				# Delete one particle

			if len(hitpoints) == 1:
				self.imagefile.xylist.pop(hitpoints[0])
				self.Refresh()

				#----- Particle selection Link Mode -----#
				if self.id == 0:
					if modePartSyn == 1 or modePartSyn == 3:
						self.GetGrandParent().panel2.imagefile.xylist.pop(hitpoints[0])
						self.GetGrandParent().panel2.Refresh()
				else:
					if modePartSyn == 2 or modePartSyn == 3:
						self.GetGrandParent().panel1.imagefile.xylist.pop(hitpoints[0])
						self.GetGrandParent().panel1.Refresh()
				#----------------------------------------#
				self.GetGrandParent().RefreshComFiles()
			return

		if len(hitpoints) == 0:
			self.hit_leftup = -1
		elif len(hitpoints) == 1:
			self.hit_leftup = hitpoints[0]
		else:
			self.hit_leftup = -2			# This only happen when a box moved on top of another


		if self.hit_leftdown == -1:				# New particle picked
			if self.hit_leftup == -1:
				newx = int((pt[0] - self.bitmap_x) / self.mag)
				newy = int((pt[1] - self.bitmap_y) / self.mag)
				if newx > 0 and newx < self.sizex_ori and newy > 0 and newy < self.sizey_ori:
					self.imagefile.xylist.append([newx, newy])

				#----- Particle selection Link Mode -----#
				if self.id == 0:
					if modePartSyn == 1 or modePartSyn == 3:
						#v2xy = self.GetGrandParent().V1xytoV2([[newx, newy]])
						if len(self.GetGrandParent().panel1.imagefile.xylist) < 4:
							return
						v2xy = self.GetGrandParent().V1xytoV2_local([newx, newy])
						self.GetGrandParent().panel2.imagefile.xylist.append(v2xy)
						self.GetGrandParent().panel2.Refresh()
				else:
					if modePartSyn == 2 or modePartSyn == 3:
						#v1xy = self.GetGrandParent().V2xytoV1([[newx, newy]])
						if len(self.GetGrandParent().panel2.imagefile.xylist) < 4:
							return
						v1xy = self.GetGrandParent().V2xytoV1_local([newx, newy])
						self.GetGrandParent().panel1.imagefile.xylist.append(v1xy)
						self.GetGrandParent().panel1.Refresh()
				#----------------------------------------#
				self.GetGrandParent().RefreshComFiles()

		else:							# Modify previous particles
			i = self.hit_leftdown
			if self.hit_leftup == -2:			# No change, restore old coordinate
				self.imagefile.xylist[i][0] = self.xylist_hit[0]
				self.imagefile.xylist[i][1] = self.xylist_hit[1]			
			else:						# Change one particle coordinate
				self.imagefile.xylist[i][0] = self.xylist_hit[0] + int((pt[0] - self.hitPt[0]) / self.mag)
				self.imagefile.xylist[i][1] = self.xylist_hit[1] + int((pt[1] - self.hitPt[1]) / self.mag)

				#----- Particle selection Link Mode -----#
				if self.id == 0:
					if modePartSyn == 1 or modePartSyn == 3:
						#v2xy = self.GetGrandParent().V1xytoV2([[newx, newy]])
						if len(self.GetGrandParent().panel1.imagefile.xylist) < 4:
							return
						v2xy = self.GetGrandParent().V1xytoV2_local(self.imagefile.xylist[i])
						self.GetGrandParent().panel2.imagefile.xylist[i] = v2xy
						self.GetGrandParent().panel2.Refresh()
				else:
					if modePartSyn == 2 or modePartSyn == 3:
						#v1xy = self.GetGrandParent().V2xytoV1([[newx, newy]])
						if len(self.GetGrandParent().panel2.imagefile.xylist) < 4:
							return
						v1xy = self.GetGrandParent().V2xytoV1_local(self.imagefile.xylist[i])
						self.GetGrandParent().panel1.imagefile.xylist[i] = v1xy
						self.GetGrandParent().panel1.Refresh()
				#----------------------------------------#

		self.zoombox.shown = False
		self.Refresh()

	def OnRightDown(self, event):
		if self.imagefile.path == '':
			return

		self.dragStartPos = event.GetPosition()
		self.SetCursor(wx.StockCursor(wx.CURSOR_HAND))
		self.zoombox.shown = False				# Right sigle click to remove previous ZoomBox
		self.Refresh()

	def OnRightUp(self, event):
		if self.imagefile.path == '':
			return
		self.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))

	def OnMotion(self, event):
		if self.imagefile.path == '':
			return

		if event.ShiftDown():					# No response for "Shift" (to delete particle)
			return

		pt = event.GetPosition()

		if event.RightIsDown():					# Moving the micrograph
			self.zoombox.shown = False
			diff = pt - self.dragStartPos
			if abs(diff[0]) > 1 or abs(diff[1]) > 1:
				self.bitmap_x += diff[0]
				self.bitmap_y += diff[1]
				self.dragStartPos[0] += diff[0]
				self.dragStartPos[1] += diff[1]
		elif event.LeftIsDown() and self.hit_leftdown != -1:	# Moving the marker (box)
			i = self.hit_leftdown
			# Box movement is not determined by the clicking point, but rather the moving of mouse/box
			self.imagefile.xylist[i][0] = self.xylist_hit[0] + int((pt[0] - self.hitPt[0]) / self.mag)
			self.imagefile.xylist[i][1] = self.xylist_hit[1] + int((pt[1] - self.hitPt[1]) / self.mag)
		else:
			return
		self.Refresh()

		# Mag and Shift Link Mode
		if self.GetGrandParent().modeShLink == 1:
			self.ShLink()


	def OnWheel(self, event):
		if self.imagefile.path == '':
			return

		self.zoombox.shown = False
        	rotation = event.GetWheelRotation()	# -120: rotate down, shrink image; +120: up, enlarge
		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)
		if sizex < 20 or sizey < 20:
			if rotation < 0:
				return			# Can not make any smaller
		if rotation > 0:
			label = 1
		else:
			label = -1

		if event.ControlDown():
			step = 0.01
		else:
			step = 0.05
		self.mag += label*step

		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		# Position of the resized bitmap (Center with mouse or display center)
		if event.ControlDown():
			centerx, centery = event.GetPosition()
		else:
			winsizex, winsizey = self.GetSize()
			centerx = winsizex / 2
			centery = winsizey / 2	

		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey

		self.Refresh()
		self.SetStatus()

		# Mag and Shift Link Mode
		if self.GetGrandParent().modeShLink == 1:
			self.ShLink()


	def OnRightDclick(self, event):
		if self.imagefile.path == '':
			return

		pt = event.GetPosition()
		pt_bitmap = pt - (self.bitmap_x, self.bitmap_y)
		self.zoombox = ZoomBox(self.bitmap, pt_bitmap)
		self.zoombox.shown = True
		self.Refresh()


	def DrawNewImg(self):
		# Refresh panel based on a new mag, sigmaLevel, and invertMarker,
		# called by 'com_files', etc.
		sizex, sizey = wx.Bitmap.GetSize(self.bitmap)

		if self.invertMarker == -1:
			self.imgstat = self.imagefile.stat_invert
			stat = self.imgstat
			truemin = stat[0] - stat[1] * self.sigmaLevel
			truemax = stat[0] + stat[1] * self.sigmaLevel
			self.img_contrast = modpil.Contrast(self.imagefile.img_invert, truemin, truemax, self.brightness)
		else:
			self.imgstat = self.imagefile.stat
			stat = self.imgstat
			truemin = stat[0] - stat[1] * self.sigmaLevel
			truemax = stat[0] + stat[1] * self.sigmaLevel
			self.img_contrast = modpil.Contrast(self.imagefile.img, truemin, truemax, self.brightness)

		self.bitmap_sizex = int(self.mag * self.sizex_ori)
		self.bitmap_sizey = int(self.mag * self.sizey_ori)
		self.bitmap = modpil.ResizeToBmp(self.img_contrast, self.bitmap_sizex, self.bitmap_sizey)

		winsizex, winsizey = self.GetSize()
		centerx = winsizex / 2
		centery = winsizey / 2	
		# Keep the image region at the CENTER at original position
		self.bitmap_x = centerx - (centerx - self.bitmap_x) * self.bitmap_sizex / sizex
		self.bitmap_y = centery - (centery - self.bitmap_y) * self.bitmap_sizey / sizey
		self.Refresh()

	def ShLink(self):
		# synchronize mag and shift between two panels, if 'modeShLink' is 1
		if self.id == 0:	# from panel1 to panel2
			self.GetGrandParent().ShLink(self.GetGrandParent().panel1, self.GetGrandParent().panel2)
		else:			# from panel2 to panel1
			self.GetGrandParent().ShLink(self.GetGrandParent().panel2, self.GetGrandParent().panel1)

	def PartSyn(self):
		modePartSyn = self.GetGrandParent().modePartSyn
		if modePartSyn == 0:		# no syn
			return
		elif modePartSyn == 1:		# from v1 to v2
			if self.id == 0:
				self.GetGrandParent().PartSyn(self.GetGrandParent().panel1, self.GetGrandParent().panel2)
		elif modePartSyn == 2:		# from v2 to v1
			if self.id == 1:
				self.GetGrandParent().PartSyn(self.GetGrandParent().panel2, self.GetGrandParent().panel1)
		else:
			if self.id == 0:	# v1 v2 interlinked
				self.GetGrandParent().PartSyn(self.GetGrandParent().panel1, self.GetGrandParent().panel2)
			else:
				self.GetGrandParent().PartSyn(self.GetGrandParent().panel2, self.GetGrandParent().panel1)


# -----------------------------------------------------------------------------------

class MyApp(wx.App):
    	def OnInit(self):
        	frame = SamViewer(None, -1, '')
        	frame.Show(True)
	        self.SetTopWindow(frame)
        	return True

app = MyApp(0)
app.MainLoop()
