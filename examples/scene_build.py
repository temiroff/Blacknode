"""Scene assembly: load two meshes, transform them, merge into scene root."""
import json
import blacknode as bn

g = bn.Graph()

root  = g.node("SceneRoot")
cube  = g.node("MeshLoad", path="assets/cube.obj")
sphere = g.node("MeshLoad", path="assets/sphere.obj")

cube_xf   = g.node("Transform", translate=[2, 0, 0])
sphere_xf = g.node("Transform", translate=[-2, 0, 0], scale=[0.5, 0.5, 0.5])

merge1 = g.node("MergeScene")
merge2 = g.node("MergeScene")

cube.out("mesh")       >> cube_xf.inp("object")
sphere.out("mesh")     >> sphere_xf.inp("object")

root.out("scene")      >> merge1.inp("parent")
cube_xf.out("object")  >> merge1.inp("child")

merge1.out("scene")    >> merge2.inp("parent")
sphere_xf.out("object") >> merge2.inp("child")

scene = g.cook(merge2, "scene")
print(json.dumps(scene, indent=2))
