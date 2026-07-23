# YOLO Object Detection: Built-in, Open-Vocabulary, and Custom Models

The **DetectionYolo** node runs real object detection (ultralytics YOLO — the
same engine the robot's examples use) on any wired `frame_stream`. This guide
covers the three ways to make it recognize what you care about:

1. **Built-in COCO models** — 80 everyday objects, zero setup.
2. **YOLO-World (open-vocabulary)** — detect arbitrary objects by *naming* them,
   no training.
3. **Custom models** — train your own detector for objects nothing else knows.

## Why a plain cube reads as "umbrella"

The default `yolov8n.pt` is trained on **COCO**, which has exactly 80 fixed
classes (person, bottle, laptop, umbrella…). A cube is not one of them, and YOLO
must assign every box it emits to one of its 80 labels — so it forces the nearest
visual match and lands on something like "umbrella" (COCO class 25). A bigger
COCO model (`yolo11m.pt`) is more *accurate* on the 80 classes but still cannot
output "cube": the class simply isn't in its vocabulary. To detect a cube you
need either YOLO-World or a custom model.

## 1. Built-in COCO models

Pick one from the node's **Model** dropdown. All auto-download on first use and
run on GPU when torch sees CUDA:

| Model | Size | Use when |
|-------|------|----------|
| `yolov8n.pt`, `yolo11n.pt` | nano | fastest, least accurate (the default) |
| `yolov8s.pt`, `yolo11s.pt` | small | a good speed/accuracy balance |
| `yolov8m.pt`, `yolo11m.pt` | medium | best accuracy on the 80 COCO objects |

Raise **conf** (e.g. 0.5–0.6) to drop weak, forced guesses like the cube→umbrella
mislabel.

## 2. YOLO-World — name what to find, no training

YOLO-World is **open-vocabulary**: it detects the classes you type instead of a
fixed list. Select a world weight from the **Model** dropdown:

- `yolov8s-world.pt` — fastest
- `yolov8m-world.pt` — balanced
- `yolov8x-worldv2.pt` — most accurate

A **Classes** and a **Confidence** field appear on the node when a world model is
selected. Type a comma-separated list of what to detect, for example:

```
box, red cube, coffee mug, robot gripper
```

Leave it empty to use the model's default vocabulary. Under the hood the node
calls YOLO-World's `set_classes()` with your list, so detections are limited to —
and named by — exactly those phrases.

**Two rules make or break YOLO-World — get these wrong and it detects nothing:**

1. **Use concrete nouns, not abstract shapes.** YOLO-World matches text against
   CLIP's *visual* embeddings. Everyday-object words score high; abstract
   geometry words score ~0. In testing on a photo of a box, the prompt `cube`
   scored **0.00** (never detected at any threshold), while `box` scored **0.19**.
   So describe the *thing*, not its shape: use `box`, `cardboard box`,
   `wooden block`, `rubik's cube`, `red cube` — not bare `cube`.

2. **Lower the confidence.** Open-vocab scores are much lower than COCO's. Custom
   classes often land at **0.1–0.3**, so the standard `0.35` hides them. The node
   auto-drops conf to **0.1** when you pick a world model; go as low as
   **0.05** if you still see nothing, and raise it if you get false boxes.

Other tips:
- Short noun phrases work best ("yellow banana", "power drill").
- More classes = slightly slower; keep the list to what you actually need.
- The Classes field saves as you type — no need to click away before running.

## 3. Train a custom model

Train your own YOLO detector when you need the highest accuracy on specific
objects (a particular part, tool, or product) or classes no pretrained model
knows. This runs entirely in ultralytics; Blacknode just loads the resulting
weight.

### Step 1 — Collect and label images

- **Collect** 50–300 images per class, covering the angles, lighting, distances,
  and backgrounds the robot will actually see. Frames captured from the robot's
  own camera generalize best. You can grab them from a Camera node's snapshot
  endpoint (`http://…/snapshot.jpg`).
- **Label** the objects with bounding boxes. Good tools:
  - [Roboflow](https://roboflow.com) — browser-based, exports YOLO format directly.
  - [CVAT](https://www.cvat.ai) — self-hostable.
  - [labelImg](https://github.com/HumanSignal/labelImg) — simple local tool.

### Step 2 — Arrange the dataset (YOLO format)

```
my_dataset/
  images/
    train/  img001.jpg …
    val/    img050.jpg …
  labels/
    train/  img001.txt …   # one line per box: <class_id> cx cy w h  (normalized 0–1)
    val/    img050.txt …
  data.yaml
```

`data.yaml` names the classes (the order defines each class id):

```yaml
path: ./my_dataset
train: images/train
val: images/val
names:
  0: cube
  1: red_box
  2: gripper
```

### Step 3 — Train

Install ultralytics and train from a small pretrained checkpoint (transfer
learning needs far fewer images than training from scratch):

```bash
pip install ultralytics

# Fine-tune YOLO11-nano on your data. Bump imgsz/epochs and use a larger base
# (yolo11s.pt / yolo11m.pt) for more accuracy at the cost of speed.
yolo detect train model=yolo11n.pt data=my_dataset/data.yaml epochs=100 imgsz=640
```

Training writes the best weight to
`runs/detect/train/weights/best.pt`. Validate it:

```bash
yolo detect val   model=runs/detect/train/weights/best.pt data=my_dataset/data.yaml
yolo detect predict model=runs/detect/train/weights/best.pt source=some_test_image.jpg
```

No GPU handy? Train free on Google Colab, or use Roboflow's hosted training, then
download `best.pt`.

### Step 4 — Use it in Blacknode

Copy the weight into the models folder (create it if needed) and give it a clear
name:

```
.blacknode/models/cube-detector.pt
```

In the **DetectionYolo** node, open the **Model** dropdown — the file appears
under **Custom (.blacknode/models)**. Pick it and cook the node. The node reads
the class names baked into your weight, so boxes are labeled with *your* names
(`cube`, `gripper`), not COCO's. `.onnx` and `.engine` (TensorRT) exports work
too and are faster on the Jetson.

## On the robot

The robot's camera (its RGB stream, served over the network) becomes a
`frame_stream` just like a local webcam: wire it into DetectionYolo and the same
model choices apply. For on-device speed on a Jetson, export your weight to
TensorRT (`yolo export model=best.pt format=engine`) and drop the `.engine` into
`.blacknode/models`.

## Which should I use?

| Goal | Choice |
|------|--------|
| 80 everyday objects, accurately | `yolo11m.pt`, conf ≥ 0.5 |
| A specific object *now*, no dataset | YOLO-World + type it in **Classes** |
| Highest accuracy on your own objects | Train a custom `.pt` → `.blacknode/models` |
