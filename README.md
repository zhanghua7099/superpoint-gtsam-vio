# superpoint-gtsam-vio
Visual Inertial Odometry using SuperPoint and GTSAM

# Installation:

After cloning the repo:
```sh
#!bash
$ git submodule update --init --recursive
$ python3 -m venv env
$ source env/bin/activate
$ pip install -r requirements.txt
```

# Usage:

Download the raw + synchronized KITTI data from [here](http://www.cvlibs.net/datasets/kitti/raw_data.php) and the annotated depth map data set from [here](http://www.cvlibs.net/datasets/kitti/eval_depth_all.php).

Run Visual-Inertial Odometry for e.g. date 2011_09_26 and drive 0022, skipping every 10th frame and using the first 701 frames available using the following command:

```sh
#!bash
$ python src/main.py --basedir /path/to/kitti/raw/data --date 2011_09_26 --drive 0022 --n_skip 10 --n_frames 701
```

![VIO vs IMU-only vs Ground Truth](path.png)
python src/main.py --basedir /home/zhy/datasets/kitti/ --date 2011_09_26 --drive 0022 --n_skip 10 --n_frames 701