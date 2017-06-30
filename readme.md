Ubuntu 16 container with Python 2, xorg and Samviewer

This is to run SamViewer, http://liao.hms.harvard.edu/samviewer

Apart from base Python, we also need dependencies for SamViewer (wxPython, PIL and python-imaging - older incarnation of PIL), and xorg to run the X.

Installation of SamViewer is quite trivial.

Trickier was inclusion of SAMUEL - additional python tools that the user needs. This was done by bringing the tar file that the user supplied into the container, untarring it and then adding the path to the untarred directories to PATH and LD_LIBRARY_PATH. Then we made an alias in the module called "sam" which executes the container expecting argument(s), first of which is the name of the python script to be run.

