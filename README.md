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

# Quick Start

```
python src/main.py --basedir /home/zhy/datasets/kitti/ --date 2011_09_26 --drive 0022 --n_skip 10 --n_frames 701
```

The folder `~/datasets/kitti/` should be arranged as:
```
~/datasets/kitti/2011_09_26
└── 2011_09_26_drive_0022_sync
    ├── image_00
    │   └── data
    ├── image_01
    │   └── data
    ├── image_02
    │   └── data
    ├── image_03
    │   └── data
    ├── oxts
    │   └── data
    ├── proj_depth
    │   └── groundtruth
    │       ├── image_02
    │       └── image_03
    └── velodyne_points
        └── data
    ├── calib_cam_to_cam.txt
    ├── calib_imu_to_velo.txt
    └── calib_velo_to_cam.txt
```

The folder `proj_depth` is from annotated depth map.

# Usage:

Download the raw + synchronized KITTI data from [here](http://www.cvlibs.net/datasets/kitti/raw_data.php) and the annotated depth map data set from [here](http://www.cvlibs.net/datasets/kitti/eval_depth_all.php).

Run Visual-Inertial Odometry for e.g. date 2011_09_26 and drive 0022, skipping every 10th frame and using the first 701 frames available using the following command:

```sh
#!bash
$ python src/main.py --basedir /path/to/kitti/raw/data --date 2011_09_26 --drive 0022 --n_skip 10 --n_frames 701
```

![VIO vs IMU-only vs Ground Truth](path.png)
python src/main.py --basedir /home/zhy/datasets/kitti/ --date 2011_09_26 --drive 0022 --n_skip 10 --n_frames 701