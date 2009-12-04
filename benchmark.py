#!/usr/bin/env python

'''Different branches in this git repository represent
   different approaches of speeding up pyglet's video decoding.
   This script runs tools/profile_video.py with a number of test videos in each
   branch and collects the results.
   Depends on ffmpeg and awk binaries to be installed.
'''
import os

ignore_branches = "master".split()
test_video_directory = os.path.expanduser("~/pyglet_test_videos")
ignore_videos = ".DS_Store".split()
framecount=50

branches = os.popen("git branch").readlines()
current_branch = [x[1:].strip() for x in branches if x[0]=="*"][0]
branches = [x[1:].strip() for x in branches]
branches = [x for x in branches if x not in ignore_branches]

videos = os.listdir(test_video_directory)
videos = [x for x in videos if x not in ignore_videos]

def switch_branch(branch):
     result = os.popen("git checkout %s"% branch).close()
     if result is not None:
         print "failed to switch to branch", branch
         sys.exit(1)

def video_info(path_to_video):
    cmdline= r"""ffmpeg -i %s 2>&1|awk -F", |: " '/Video:/{print $3, $4}'""" % fullpath
    p = os.popen(cmdline)
    result = p.readlines()[0].strip()
    exitcode = p.close()
    if exitcode is not None:
        raise Error()
    return result

def profile(path_to_video):
    p = os.popen("python tools/profile_video.py --frames=%d %s" % (framecount, path_to_video))
    result = p.readlines()[0].rstrip()
    exitcode = p.close()
    if exitcode is not None:
        raise Error()
    return result

for branch in branches:
    switch_branch(branch)
    for video in videos:
        fullpath = test_video_directory + os.sep + video
        info = video_info(fullpath)
        result = profile(fullpath)
        print "%-20s" % info, result
        
if branch != current_branch:
    result = os.popen("git checkout %s"% current_branch).close()