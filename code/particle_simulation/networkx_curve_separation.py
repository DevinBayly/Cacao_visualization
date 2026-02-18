#!/usr/bin/env python
# coding: utf-8

# # polyline conversion
# This section is all about turning the poly lines file into a array of json/dict elements that we can feed into the later steps

# In[2]:


import json


# In[3]:


import networkx as nx


# In[4]:


import itertools


# In[5]:


from pathlib import Path


# In[6]:




# In[7]:


# this section helps us read the data in when it's not in polylines yet
# just add all the vertices to the graph according to their connections and then we will generate all the "full paths" that go from root to leafs
from plyfile import PlyData 


# In[8]:


hand_drawn = PlyData.read("test.ply")


# In[9]:


hand_drawn


# In[10]:


[e for e in hand_drawn["edge"][0]]


# In[11]:


hand_drawn["edge"].count


# In[12]:


g = nx.Graph()
n=1
mp = {}
for edgei in range(hand_drawn["edge"].count):
    vertices = hand_drawn["edge"][edgei]
    for vi in vertices:
        point= hand_drawn["vertex"][vi]
        key = str(dict(x=point[0],y=point[1],z=point[2]))
        if mp.get(key,-1) !=-1:
            continue
        mp[key] =n
        n+=1


# In[13]:


Path("all_data.json").write_text(json.dumps([json.loads(k.replace("'",'"')) for k in mp.keys()]))


# In[14]:


for edgei in range(hand_drawn["edge"].count):
    vertices = hand_drawn["edge"][edgei]
    start = hand_drawn["vertex"][vertices[0]]
    end = hand_drawn["vertex"][vertices[1]]
    sdict = dict(x=start[0],y=start[1],z=start[2])
    edict = dict(x=end[0],y=end[1],z=end[2])
    s_id = vertices[0]
    e_id = vertices[1]

   
    g.add_nodes_from([(int(s_id),sdict),(int(e_id),edict)])
    g.add_edge(s_id,e_id)
        


# In[15]:


print("connected components",nx.number_connected_components(g))


# In[16]:


for c in nx.connected_components(g):
    print(c)


# In[17]:


type(c)


# In[18]:


len(g.edges)




# In[21]:


components = nx.connected_components(g)


# In[26]:


components_and_timesteps =[]
for component in components:
    print()
    # we need to look for all the points that only have one connection to another, these will be the tips of the tree (roots, and leaves)
    yvals = []
    for n in component:
        if g.degree(n) ==1:
            # attrs = nx.get_node_attributes(g,"y")
            # note that sometimes this above part needs to be added so the paths start at the right place
            attrs = nx.get_node_attributes(g,"z")
            yvals.append([n,attrs[n]]) # add the node identifier n and the y coordinate to a yvals list
    
    #this will return only the y value when we sort the list
    def sorted(x):
        return x[1]
    
    # sort based on the y value element for each
    yvals.sort(key=sorted)
    
    yvals
    
    # get the nodes below -1 y, they are the roots of the tree
    # NOTE when working with different 3d models this logic may need to change
    # generate shortest paths from them
    # add all of them to a list
    roots = [e[0] for e in yvals[:1]]
    roots
    
    # print("roots",roots)
    # the rest of the ids are the tips of the leaves
    tips = [e[0] for e in yvals[1:]]
    tips
    
    # print("tips",tips)
    
    
    
    import tqdm
    
    
    
    # Here's the most important part from this section
    # we are using the shortest_path method to calculate the paths between roots and leaves
    paths = []
    pairings = [[r,t] for r in roots for t in tips]
    for r,t in tqdm.tqdm(pairings):
        simple_paths = nx.shortest_path(g,r,t)
        # add to a structure that we can write out later, and use for .obj generation
        paths.append({"source":int(r),"target":int(t),"paths":[(int(s),int(e)) for s,e in itertools.pairwise(simple_paths)]})
        # break # if we want to test we can uncomment this and only run one iteration
    
    # grab the attribute lists
    x_attr = nx.get_node_attributes(g,"x")
    y_attr = nx.get_node_attributes(g,"y")
    z_attr = nx.get_node_attributes(g,"z")
    
    # make a collection for the specific paths
    vert_paths=[]
    for p in paths:
        text = ""
        # this helps us only have one reference to the 3d coordinates per node id
        vert_row_map ={}
        # this is the node index we will track this so we can write out the vertices in the right order later
        n=0
        # iterate over the paths for each starting root
        # note these are the pairs of coordinates show above, they are the start and end point of a edge in the graph
        for nodes in p["paths"]:
            
            # for each node in the pair 
            for node_id in nodes:
                key = node_id
                # if this node id doesnt have coords in the map add them
                # is line returns -1 it means that node isn't in the map yet
                # if it is in the map we run into the continue part of the conditional
                if vert_row_map.get(key,-1) !=-1:
                    continue
                x = x_attr[node_id]
                y = y_attr[node_id]
                z = z_attr[node_id]
                # make sure we can access the index of the node in the path in the value as well so we can write it out in order as .obj
                vert_row_map[key] =[n,x,y,z]
                # add one to the node index counter
                n+=1
        # add the path to the vertex paths
        vert_paths.append(vert_row_map)
    print("vertex_paths",vert_paths)
    # make a obj writer for each curve in the file that connects a root with a leaf
    
    # can use i to map between the two lists vert_paths, and paths since they have the same order
    # for i,p in enumerate(paths):
    #     lines = ""
    #     verts = ""
    
    #     # lets write the vertex rows of the file first
    #     # get the collection of x,y,z points for this path and the order they should be written to the file
    #     vmap = vert_paths[i]
    #     for k,v in vmap.items():
    #         # note we use 1: to skip the first value in the list because that is the n value and we want to only have x,y,z in the row separated by ' '
    #         verts +=f"\nv {' '.join([str(e) for e in v[1:]])}"
    
    #     # now we will write the lines
    #     for start_id,end_id in p["paths"]:
    #         # use the vert_path_ map to get the right edge line values
    #         start_id_mapped = vmap[start_id][0]
    #         end_id_mapped = vmap[end_id][0]
    #         lines +=f"\nl {start_id_mapped} {end_id_mapped}"
    #     Path(f"test_verts_{i}.obj").write_text(verts+lines)
    
    
    
    # !rm test*.obj
    
    ## making simulation files
    
    # Here we will begin by outputting json files that can be visualized on the web
    
    # Then we will work on writing data out as animating files that work in blender
    
    # start by making sort of a test file
    import numpy as np
    
    import json
    from pathlib import Path 
    
    # # this makes a random data array where we have 100 time steps
    # # each time step is like a table of 500 rows with 3 columns x,y,z
    # timearr = np.random.random((100,500,3))
    
    # # write this out to json
    # Path("test.json").write_text(json.dumps([[{"x":e[0],"y":e[1],"z":e[2]} for e in arr ] for arr in timearr ]))
    
    # make particles start at the beginning of one of the paths, and then with each time step they move to a new part on the path
    
    x_attr = nx.get_node_attributes(g,"x")
    y_attr = nx.get_node_attributes(g,"y")
    z_attr = nx.get_node_attributes(g,"z")
    # this can hold all the paths that the points go after we iterate over them in time
    
    # the only way I could think to do this was first make tracks or a list of the x,y,z points that a particle is as it goes along a path
    
    
    tracks=[]
    # iterate over the paths
    for path in paths:
        # get the pairs in a path
        point_pairs = path["paths"]
    
        # this will be the route a single point has to take, 
        # we can think of it as the steps in 3d space a particle traveling the path will take over time
        position_times = []
    
        # again start and end are node indices in the graph, just integer values
        for start,end in point_pairs:
    
            # we only need the start because the end will be a start in the next interation
            x = x_attr[start]
            y = y_attr[start]
            z = z_attr[start]
            # add the data as a dictionary element
            # this is easy to work with and convert to tables or arrays later
            position_times.append(dict(x=x,y=y,z=z))
        tracks.append(position_times)    
    
    # now we will iterate and collect the positions of each point at each time 
    time_steps =[]
    # i is sort of the time step (also the index into the position collections held in each track)
    for i in range(158):
        # make somewhere we cna store the positions for this tiem
        positions =[]
        # iterate over the tracks
        for track in tracks:
            # make sure our current time isn't greater than the track has entries for
            if i < len(track):
                # if we have an entry, write it out
                positions.append(track[i])
        # add this collection of all the positions on all the branches to a time_step
        time_steps.append(positions)
    
    
    # write this out for visualization prototyping
    # Path("test.json").write_text(json.dumps([[{"x":float(e["x"]),"y":float(e["y"]),"z":float(e["z"])} for e in arr ] for arr in time_steps ]))
    
    
    ## making the USD files
    # Here we convert our working simulation data to a format we can bring into blender automatically
    
    
    import random
    
    import numpy as np
    
    # Akshat TODO, read in the velocity data as pd dataframe
    # pick a single column from the depths,
    # normalize it
    import matplotlib.pyplot as plt
    import pandas as pd
    df = pd.read_csv("sap_flow.csv")
    
    df["date"] =pd.to_datetime(df['Datetime'], format='%m/%d/%Y %H:%M')
    
    mid_speeds = df["Vc_15mm_cm/hr"]
    mid_speeds
    
    
    
    # note, look for another way to use the pandas series but with reindexing , unfortunately reset_index turns it into a whole dataframe again
    # want to make the steps relative to a 2mm unit or .2 cm
    # so we divide by .2 and that tells us the number of float steps, and then we floor the values
    stepped = np.array((mid_speeds).dropna().astype("int16"))
    
    stepped
    
    mid_speeds
    
    # plt.plot(np.arange(stepped.shape[0]),stepped)
    
    df.columns
    
    from pathlib import Path
    
    Path("mid_data.json").write_text(df[['Vc_15mm_cm/hr',"date"]].to_json())
    
    track
    
    track_df = pd.DataFrame([{"x":e["x"],"y":e["y"],"z":e["z"],"track":i} for i,t in enumerate(tracks) for e in t])
    
    track_df
    
    coord_df = track_df[["x","y","z"]]
    
    min_dim = coord_df.min(axis=0
                          )
    min_dim
    
    zero_centered = coord_df - min_dim
    
    max_dim = coord_df.max(axis=0)
    max_dim
    
    extents = max_dim - min_dim
    
    extents
    
    np.linalg.norm(extents)
    
    zero_centered
    
    normalized = zero_centered/np.linalg.norm(extents)
    
    normalized
    
    normalized["norm"] = np.linalg.norm(normalized[["x","y","z"]],axis=1)
    
    
    
    normalized
    
    # normalized.plot(y="x",use_index=True)
    # normalized.plot(y="y",use_index=True)
    # normalized.plot(y="z",use_index=True)
    # normalized.plot(y="norm",use_index =True)
    
    # now find multiple that makes y go to 369 which is the total in cm that a tree gets
    # measured 8in section is 20.32 cm
    # cm_scalar = 20.32/normalized.y.max()
    cm_scalar = 1000
    
    cm_scalar
    
    scaled_df = normalized[["x","y","z"]] * cm_scalar
    
    scaled_df["step_distance"] = np.linalg.norm(scaled_df - scaled_df.shift(-1),axis=1)
    
    # bring the track labels back in
    scaled_df["track"]= track_df["track"]
    
    # checking to see how the natural jumps in the path measure in terms of cm
    # scaled_df[scaled_df.track ==4][:-1].plot(y="step_distance",use_index=True)
    
    # iterate over the tracks and on each make sure we have a point for each cm increment
    
    # working out the size of unit I should move by
    # df["Vc_15mm_cm/hr"].abs()[df["Vc_15mm_cm/hr"].abs() <1].plot.hist(bins=100)
    
    # going down to about .2 mm seems appropriate because that's about the size of an ant, and we could imagine a very close view that needs to see that the motion never really stops
    
    all_points = scaled_df.to_dict("records")
    
    groups = []
    track =[]
    starting_track = all_points[0]["track"]
    for point in all_points:
        current_track = point["track"]
        if current_track==starting_track:
            track.append(point)
        else:
            groups.append(track)
            track = [point]
            starting_track = current_track
    # don't forget the last track
    groups.append(track)
    groups[0]
    
    subdivided_groups = []
    for track in tqdm.tqdm(groups):
        # compare to the outer length
        # skip the last point
        subdivided = []
        points =[]
        for i,p in enumerate(track[:-1]):
            next_p = track[i+1]
            # make array vectors from the points
            arp = np.array([p["x"],p["y"],p["z"]])
            points.append(arp)
            arnp = np.array([next_p["x"],next_p["y"],next_p["z"]])
            # subtrack p from next_p make delta
            delta = arnp - arp
            # get delta magnitude use this in loop to determine ending criteria
            mag = np.linalg.norm(delta)
            # normalize the delta
            norm = delta/mag
            # scale it by .2 making scaled_norm
            scaled = norm*.2
            current = scaled
            current_mag = np.linalg.norm(current)
            increment = 1
            # make sure to get the starting point
            subdivided.append(arp)
                # check the resulting multiple of scaled norm against delta mag
            
            while current_mag < mag:
                # slowly make the vector we add to the starting p making bigger in steps of .2
                current = norm * .2*increment
                current_mag = np.linalg.norm(current)
                subdivided_point = arp + current
                increment +=1
                subdivided.append(subdivided_point)
            
            # stop at the end and 
        subdivided_groups.append(subdivided)
        # perhaps just add the final point in the data at the end or we can leave it off because that'll just be a 2mm shorter path
    
    points = np.array(points)
    
    import matplotlib.pyplot as plt
    
    subdivided = np.array(subdivided)
    
    tracks = [[{"x":e[0],"y":e[1],"z":e[2]} for e in track] for track in subdivided_groups]
    # convert back to dictionary format
    
    
    # so we need to increase the number of time steps to be as long as the csv data is
    # in terms of veocity we might need to find a way to relate the scale of the model with number of steps along a path
    # worry about that later
    
    # need a way to think about the code from a "particle" perspective
    # it would have a path it's on
    # it would have a velocity (how many steps to move on the path)  
    # 
    
    # make the particle pick a path/track to start with using random choice 
    timesteps= []
    particles = []
    def create_particle(tracks):
        track = random.choice(tracks)
        # NOTE this is probably something we want to base on the min and max values of the size of the tree, too much noise totally distorts the tree
        noise = np.random.random((3))/50
        return dict(
            track = track,
            # keep understandign of length of track
            track_length = len(track),
            starting_position = track[0],
            current_position = track[0],
            offset=noise,
            # note that we can track next position and then interpolate also
            index = 0
        )
    
    # make a "move particles" function
    # this function also potentially removes elements from the p_list
    # will return a new list
    def move_particles(p_list,series,simulation_step_index):
        new_list =[] 
        for particle in p_list:
            index = particle["index"]
            track =particle["track"]
            track_length = particle["track_length"]
            # if we can continue, particle hasn't fallen off the track
            # Akshat TODO, change the parts of the code that depend index +1 to be index+ some velocity mapped step [1,10]
            
            step_size = series[simulation_step_index]
            if index+step_size < track_length-1:
                # this is where we will think about stepping more than one index place through the track when velocity is higher
                # use the sca
                # Akshat TODO, change the parts of the code that depend index +1 to be index+ some velocity mapped step [1,10]
                
                next_index = index +step_size
                particle["current_position"] = track[next_index]
                particle["index"] = next_index
                # if we wanted to interpolate here's where we would get the next and then use some sort of parametric form
                new_list.append(particle)
        return new_list
    
        
    def add_particles(p_list,number_to_add,tracks):
        new_particles = [create_particle(tracks) for i in range(number_to_add)]
        p_list.extend(new_particles)
        return p_list
    
    
    # make a "take snapshot" function that gets all positions and writes them out to the 
    def take_snapshot(tsteps,p_list):
        # injecting a little bit of noise
        tsteps.append([
            {
                "x": p["current_position"]["x"] + p["offset"][0], # could add more forces if we wanted to make more dynamic,
                "y":p["current_position"]["y"] + p["offset"][1],
                "z":p["current_position"]["z"] + p["offset"][2]
                
            }
            for p in p_list
        ])
    
    # simulation_steps = stepped.shape[0]//4
    simulation_steps = 10
    number_particles_to_start = 5
    number_to_add_per_step=1
    particles = add_particles(particles,number_particles_to_start,tracks)
    for time_index in tqdm.tqdm(range(simulation_steps)):
        # move the particles
        moved_particles = move_particles(particles,stepped,time_index)
        particles = moved_particles
        # add new ones
        added_particles = add_particles(particles,number_to_add_per_step,tracks)
        particles = added_particles
        # snapshot
        take_snapshot(timesteps,particles)
    components_and_timesteps.append([e for e in timesteps])
    print("timesteps",timesteps)
# at the end make the output match the way the usdc write out pattern works
# have an array of time steps
# each time step has collection of point positions


# In[24]:


len(components_and_timesteps[0])


# In[25]:


# this cell does a lot of work
from pxr import Usd,UsdGeom,Vt,Sdf
from pathlib import Path
import numpy as np
import argparse
# name our output file


import pandas as pd


# see if we can delete the previous stage, maeks it easier to work with cell iteratively
try:
    print(stage)
    del stage
except:
    pass
name="test_box"
# create the variable we add points to, it's called a stage in usd
stage = Usd.Stage.CreateNew(f"{name}.usdc")
pts = UsdGeom.Points.Define(stage,"/mypoints")

import numpy as np

# get attributes we can write to
points = pts.GetPointsAttr()
widths = pts.GetWidthsAttr()
total_time = simulation_steps
# establish the length of the timeseries
stage.SetStartTimeCode(0)
stage.SetEndTimeCode(simulation_steps)

# loop over our timesteps
for i in range(simulation_steps):
    all_json_points =[]
    for comp_timestep in components_and_timesteps:
        all_json_points += comp_timestep[i]
    # if we end up attaching data to each poitn we will use these names
    # names = arr.dtype.names[3:]
    # pvars={}
    # arr[:,1], arr[:,2]


    # convert from list of dicts to a table, then to an array
    df = pd.DataFrame(all_json_points)
    arr = df.to_numpy()



    # write the array data to the attribute
    # print(arr)
    points.Set(time=i,value=Vt.Vec3fArray.FromNumpy(np.array([arr[:,0],arr[:,1],arr[:,2]]).T))


    # again we will use this later when we attach data to the points

    # for name in names:
    #   # skip the "_" prefaced names that stand for offset balancing in pcd binary
    #     if "skip" in name:
    #       continue
        # pvar = UsdGeom.PrimvarsAPI(pts).CreatePrimvar(name,Sdf.ValueTypeNames.FloatArray,"vertex")
        # pvar.Set(time=i,value= Vt.FloatArray(arr[name].astype("float64")))
        # pvars[name] = pvar
    

    

print("saving")
stage.Save()


# In[494]:


len(timesteps)


# In[ ]:


json.dumps(timesteps)

