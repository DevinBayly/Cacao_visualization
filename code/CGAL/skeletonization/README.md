Example of skeletonization

Download and setup CGAL https://doc.cgal.org/latest/Manual/general_intro.html

Once you've downloaded and extracted a release tar.gz navigate to the examples/Skeletonization (That folder has a ton of examples of the process that were borrowed to make this work)

Copy the CMakeLists.txt from this repo into that folder

Run the following command `cmake -DCMAKE_PREFIX_PATH=../../ -DCMAKE_BUILD_TYPE=Release .`

then make the following programs with `make obj_off simple_mcfskel_example -j4`

after this you will convert the existing cleaned up obj tree to OFF model format
`obj_off tree_pre_skeleton_cleaner.obj tree.off`

Then trace the skeleton of the object
`simple_mcfskel_example tree.off`

Then we will reconstruct a file we can bring into blender using this python snippet
```
from pathlib import Path
# read the polylines, each line in this file is a sequence of 3d coords for a line
poly_lines = Path("skel-poly.polylines.txt").read_text()
# prepare some strings to store information for writing out
obj_code = ""
# this will be the offset value that we use to index the correct lines, when we loop over the vertices of a different line, we must add to the vert segment index a number representing all the previous vertices we've already written to the file
line_buffer = 0
lines = ""

# iterate over the lines in the file
for line in poly_lines.split("\n"):
    #skip the empty at the end of the file
    if line!="":
        #get the parts of the line
        parts = line.split(" ")
        print(parts)
        # first part is the number of line segments, strip any white space
        segs = int(parts[0].strip())
        # the rest are the coordinates
        coords = parts[1:]
        # store the coordinates in groups of 3
        verts = [coords[start:start+3] for start in range(0,len(coords),3)]
        print(verts)
        print()

        # iterate over the vertex groups, write the information in obj format 
        for i,v in enumerate(verts):
            # join the vertex floating point strings with a space between them prefixed by "v" at the front of the line
            obj_code+=f'\nv {" ".join(v)}'
            # check if we have reached the end of the list
            if i+2 > len(verts):
                break
            # we have to add 1 since obj files use 1 based counting
            # we also add the line buffer since the index refers to the whole vertex list, not just the index within the particular segment we are iterating over
            lines += f"\nl {i+1+line_buffer} {i+2+line_buffer}"
    
        print(segs)
        # offset the line buffer amount when we finish a segment
        line_buffer+=segs

# write out the file
Path("out_tree.obj").write_text(obj_code+lines)
```

bringing into blender


