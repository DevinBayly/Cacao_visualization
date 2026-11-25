# Simulating particles

moving points to their correct locations along the tree wasn't easy in blender so we are going to do this on our own.

This requires a few other steps
* construct a graph representation of the skeleton's polylines
* starting from nodes determined to be roots, find all the paths to the leaves 
* spawn particles at a beginning location (roots)
* move them along the paths step by stsep

This is currently the least complex variation of the particle movement, and doesn't immediately include using the data, but that will come next!


Really just read [this notebook file](./networkx_curve_separation.ipynb), it has all the sections laid out


## Other files used in this folder

`cors_vis_server.py` is a script that lets us boot up a server that will make requesting resources from our local machine a possibility. This is normally not possible because of the Cross Origin Restriction policy. It is helpful for preliminary visualization tools like https://observablehq.com/d/8eee70effa23dada (there's some content at the bottom that requires this server to be running and have a file called `test.json` that gets created by the jupyter notebook code)