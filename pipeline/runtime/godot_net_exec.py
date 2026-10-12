#!/usr/bin/env python3
"""Child of unshare -Urn; all Godot descendants share this isolated test network."""
import os,subprocess,sys
subprocess.run(['/usr/sbin/ip','link','set','lo','up'],check=True,timeout=10)
os.environ['DIRECT82_IN_NETNS']='1'
os.execv(sys.argv[1],sys.argv[1:])
