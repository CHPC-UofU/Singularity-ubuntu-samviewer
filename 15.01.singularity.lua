-- -*- lua -*-
-- Written by MC on 3/28/2017
help(
[[
This module sets up SamViewer 15.01 container running Ubuntu 16.06.

]])

load("singularity")
local PVPATH="/uufs/chpc.utah.edu/sys/installdir/samviewer/15.01-singularity"

--set_alias("startparaview","singularity shell -s /bin/bash -B /scratch,/uufs/chpc.utah.edu " .. PVPATH .. "/ubuntu_paraview.img")
--set_alias("paraview","singularity exec -B /scratch,/uufs/chpc.utah.edu " .. PVPATH .. "/ubuntu_biobakery.img paraview")

-- singularity environment variables to bind the paths and set shell
setenv("SINGULARITY_BINDPATH","/scratch,/uufs/chpc.utah.edu")
setenv("SINGULARITY_SHELL","/bin/bash")
-- shell function to provide "alias" to the seqlink commands, as plain aliases don't get exported to bash non-interactive shells by default
set_shell_function("sv",'singularity exec' .. PVPATH .. '/ubuntu_samviewer.img sv "$@"',"singularity exec " .. PVPATH .. "/ubuntu_samviewer.img sv $*")
-- to export the shell function to a subshell
if (myShellName() == "bash") then
 execute{cmd="export -f sv",modeA={"load"}}
end

whatis("Name        : SamViewer")
whatis("Version     : 15.01")
whatis("Category    : 2D image display and analysis program, specifically designed for single-particle EM")
whatis("URL         : http://liao.hms.harvard.edu/samviewer")
