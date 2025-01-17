import numpy as np
import VisualInertialOdometry as vio
import pykitti
import argparse
import SuperPointPretrainedNetwork.demo_superpoint as sp
import cv2
import os
from scipy.spatial.transform import Rotation as R

import gtsam
from gtsam.symbol_shorthand import B, V, X, L

import matplotlib.pyplot as plt
#plt.rc('text', usetex=True)
plt.rc('font', size=16)

def get_theta(rotation):
    return R.from_matrix(rotation).as_euler('xyz')

def get_vision_data(tracker):
    """ Get keypoint-data pairs from the tracks. 
    """
    # Store the number of points per camera.
    pts_mem = tracker.all_pts
    N = len(pts_mem) # Number of cameras/images.
    # Get offset ids needed to reference into pts_mem.
    offsets = tracker.get_offsets()
    # Iterate through each track and get the data from the current image.
    vision_data = -1 * np.ones((tracker.tracks.shape[0], N, 2), dtype=int)
    for j, track in enumerate(tracker.tracks):
      for i in range(N-1):
        if track[i+3] == -1: # track[i+2] == -1 or 
          continue
        offset2 = offsets[i+1]
        idx2 = int(track[i+3]-offset2)
        pt2 = pts_mem[i+1][:2, idx2]
        vision_data[j, i] = np.array([int(round(pt2[0])), int(round(pt2[1]))])
    return vision_data


if __name__ == '__main__':
    # Input arguments
    parser = argparse.ArgumentParser(description='Visual Inertial Odometry of KITTI dataset.')
    parser.add_argument('--basedir', dest='basedir', type=str)
    parser.add_argument('--date', dest='date', type=str)
    parser.add_argument('--drive', dest='drive', type=str)
    parser.add_argument('--n_skip', dest='n_skip', type=int, default=1)
    parser.add_argument('--n_frames', dest='n_frames', type=int, default=None)
    args = parser.parse_args()

    fig, axs = plt.subplots(1, figsize=(12, 8), facecolor='w', edgecolor='k')
    plt.subplots_adjust(right=0.95, left=0.1, bottom=0.17)

    viz_tracking = True

    """ 
    Load KITTI raw data
    """

    data = pykitti.raw(args.basedir, args.date, args.drive)

    # Number of frames
    if args.n_frames is None:
        n_frames = len(data.timestamps)
    else:
        n_frames = args.n_frames

    # Time in seconds
    time = np.array([(data.timestamps[k] - data.timestamps[0]).total_seconds() for k in range(n_frames)])

    # Time step
    delta_t = np.diff(time)

    # Velocity
    measured_vel = np.array([[data.oxts[k][0].vf, data.oxts[k][0].vl, data.oxts[k][0].vu] for k in range(n_frames)])

    # Acceleration
    measured_acc = np.array([[data.oxts[k][0].af, data.oxts[k][0].al, data.oxts[k][0].au] for k in range(n_frames)])

    # Angular velocity
    measured_omega = np.array([[data.oxts[k][0].wf, data.oxts[k][0].wl, data.oxts[k][0].wu] for k in range(n_frames)])

    # Poses
    measured_poses = np.array([data.oxts[k][1] for k in range(n_frames)])
    measured_poses = np.linalg.inv(measured_poses[0]) @ measured_poses

    """
    Load depth data
    """
    depth_data_path = os.path.join(args.basedir, args.date, '2011_09_26_drive_' + args.drive + '_sync/proj_depth/groundtruth/image_02')
    depth = []

    # Load in the images
    for filepath in sorted(os.listdir(depth_data_path)):
        if filepath[0] == '.':
            continue
        depth.append(cv2.imread(os.path.join(depth_data_path, filepath)))

    """
    Run superpoint to get keypoints
    """
    print('==> Loading pre-trained network.')
    # This class runs the SuperPoint network and processes its outputs.
    # Inputs from list of default options in superpoint_demo.py.
    fe = sp.SuperPointFrontend(weights_path='src/SuperPointPretrainedNetwork/superpoint_v1.pth',
                            nms_dist=4,
                            conf_thresh=0.15,  # 0.015
                            nn_thresh=0.9,
                            cuda=True)
    print('==> Successfully loaded pre-trained network.')

    # This class helps merge consecutive point matches into tracks.
    max_length = n_frames // args.n_skip + 1
    tracker = sp.PointTracker(max_length=max_length, nn_thresh=fe.nn_thresh)

    print('==> Running SuperPoint')
    idx = range(0, n_frames, args.n_skip)
    for i in idx:
        img = data.get_cam1(i) # only get image from cam0
        img_np = np.array(img).astype('float32') / 255.0
        pts, desc, _ = fe.run(img_np)
        tracker.update(pts, desc)
        
        # visualize the tracking
        if viz_tracking:
            tracks = tracker.get_tracks(2)
            tracks[:, 1] /= float(0.9)
            out1 = (np.dstack((img_np, img_np, img_np)) * 255.).astype('uint8')
            tracker.draw_tracks(out1, tracks)
            cv2.imshow("out1", out1)
            cv2.waitKey(1)

    print('==> Extracting keypoint tracks')
    vision_data = get_vision_data(tracker)

    """
    GTSAM parameters
    """
    print('==> Adding IMU factors to graph')

    g = 9.81

    # IMU preintegration parameters
    # Default Params for a Z-up navigation frame, such as ENU: gravity points along negative Z-axis
    IMU_PARAMS = gtsam.PreintegrationParams.MakeSharedU(g)
    I = np.eye(3)
    IMU_PARAMS.setAccelerometerCovariance(I * 0.2)
    IMU_PARAMS.setGyroscopeCovariance(I * 0.2)
    IMU_PARAMS.setIntegrationCovariance(I * 0.2)

    BIAS_COVARIANCE = gtsam.noiseModel.Isotropic.Variance(6, 0.4)

    """
    Solve IMU-only graph
    """
    params = gtsam.LevenbergMarquardtParams()
    params.setMaxIterations(1000)
    params.setVerbosity('ERROR')
    params.setVerbosityLM('SUMMARY')

    print('==> Solving IMU-only graph')
    imu_only = vio.VisualInertialOdometryGraph(IMU_PARAMS=IMU_PARAMS, BIAS_COVARIANCE=BIAS_COVARIANCE)
    imu_only.add_imu_measurements(measured_poses, measured_acc, measured_omega, measured_vel, delta_t, args.n_skip)
    result_imu = imu_only.estimate(params)

    """
    Solve VIO graph
    """
    params = gtsam.LevenbergMarquardtParams()
    params.setMaxIterations(1000)
    params.setlambdaUpperBound(1.e+6)
    params.setlambdaLowerBound(0.1)
    params.setDiagonalDamping(1000)
    params.setVerbosity('ERROR')
    params.setVerbosityLM('SUMMARY')
    params.setRelativeErrorTol(1.e-9)
    params.setAbsoluteErrorTol(1.e-9)

    print('==> Solving VIO graph')
    vio_full = vio.VisualInertialOdometryGraph(IMU_PARAMS=IMU_PARAMS, BIAS_COVARIANCE=BIAS_COVARIANCE)
    vio_full.add_imu_measurements(measured_poses, measured_acc, measured_omega, measured_vel, delta_t, args.n_skip)
    vio_full.add_keypoints(vision_data, measured_poses, args.n_skip, depth, axs)

    result_full = vio_full.estimate(SOLVER_PARAMS=params)

    """
    Visualize results
    """
    print('==> Plotting results')

    x_gt = measured_poses[:,0,3]
    y_gt = measured_poses[:,1,3]
    theta_gt = np.array([get_theta(measured_poses[k,:3,:3])[2] for k in range(n_frames)])

    x_init = np.array([vio_full.initial_estimate.atPose3(X(k)).translation()[0] for k in range(n_frames//args.n_skip)]) 
    y_init = np.array([vio_full.initial_estimate.atPose3(X(k)).translation()[1] for k in range(n_frames//args.n_skip)]) 
    theta_init = np.array([get_theta(vio_full.initial_estimate.atPose3(X(k)).rotation().matrix())[2] for k in range(n_frames//args.n_skip)]) 

    x_est_full = np.array([result_full.atPose3(X(k)).translation()[0] for k in range(n_frames//args.n_skip)]) 
    y_est_full = np.array([result_full.atPose3(X(k)).translation()[1] for k in range(n_frames//args.n_skip)]) 
    theta_est_full = np.array([get_theta(result_full.atPose3(X(k)).rotation().matrix())[2] for k in range(n_frames//args.n_skip)]) 

    x_est_imu = np.array([result_imu.atPose3(X(k)).translation()[0] for k in range(n_frames//args.n_skip)]) 
    y_est_imu = np.array([result_imu.atPose3(X(k)).translation()[1] for k in range(n_frames//args.n_skip)]) 
    theta_est_imu = np.array([get_theta(result_imu.atPose3(X(k)).rotation().matrix())[2] for k in range(n_frames//args.n_skip)]) 

    axs.plot(x_gt, y_gt, color='k', label='GT')
    axs.plot(x_init, y_init, 'x-', color='m', label='Initial')
    axs.plot(x_est_imu, y_est_imu, 'o-', color='r', label='IMU')
    axs.plot(x_est_full, y_est_full, 'o-', color='b', label='VIO')
    axs.set_xlabel('$x\ (m)$')
    axs.set_ylabel('$y\ (m)$')
    axs.set_aspect('equal', 'box')
    plt.grid(True)

    plt.legend()
    plt.savefig('path.eps')

    # Plot pose as time series
    fig, axs = plt.subplots(3, figsize=(8, 8), facecolor='w', edgecolor='k')
    plt.subplots_adjust(right=0.95, left=0.15, bottom=0.17, hspace=0.5)

    # Plot x
    axs[0].grid(True)
    axs[0].plot(time, x_gt, color='k', label='GT')
    axs[0].plot(time[:n_frames-1:args.n_skip], x_init, color='m', label='Initial')
    axs[0].plot(time[:n_frames-1:args.n_skip], x_est_imu, color='r', label='IMU')
    axs[0].plot(time[:n_frames-1:args.n_skip], x_est_full, color='b', label='VIO')
    axs[0].set_xlabel('$t\ (s)$')
    axs[0].set_ylabel('$x\ (m)$')

    # Plot y
    axs[1].grid(True)
    axs[1].plot(time, y_gt, color='k', label='GT')
    axs[1].plot(time[:n_frames-1:args.n_skip], y_init, color='m', label='Initial')
    axs[1].plot(time[:n_frames-1:args.n_skip], y_est_imu, color='r', label='IMU')
    axs[1].plot(time[:n_frames-1:args.n_skip], y_est_full, color='b', label='VIO')
    axs[1].set_xlabel('$t\ (s)$')
    axs[1].set_ylabel('$y\ (m)$')

    # Plot theta
    axs[2].grid(True)
    axs[2].plot(time, theta_gt, color='k', label='GT')
    axs[2].plot(time[:n_frames-1:args.n_skip], theta_init, color='m', label='Initial')
    axs[2].plot(time[:n_frames-1:args.n_skip], theta_est_imu, color='r', label='IMU')
    axs[2].plot(time[:n_frames-1:args.n_skip], theta_est_full, color='b', label='VIO')
    axs[2].set_xlabel('$t\ (s)$')
    axs[2].set_ylabel('$\\theta\ (rad)$')
    
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.savefig('poses.eps')

    # Plot pose as time series
    fig, axs = plt.subplots(3, figsize=(8, 8), facecolor='w', edgecolor='k')
    plt.subplots_adjust(right=0.95, left=0.15, bottom=0.17, hspace=0.5)
    # Plot x
    axs[0].grid(True)
    axs[0].plot(time[:n_frames-1:args.n_skip], np.abs(x_gt[:n_frames-1:args.n_skip] - x_init), color='m', label='Initial')
    axs[0].plot(time[:n_frames-1:args.n_skip], np.abs(x_gt[:n_frames-1:args.n_skip] - x_est_imu), color='r', label='IMU')
    axs[0].plot(time[:n_frames-1:args.n_skip], np.abs(x_gt[:n_frames-1:args.n_skip] - x_est_full), color='b', label='VIO')
    axs[0].set_xlabel('$t\ (s)$')
    axs[0].set_ylabel('$e_x\ (m)$')

    # Plot y
    axs[1].grid(True)
    axs[1].plot(time[:n_frames-1:args.n_skip], np.abs(y_gt[:n_frames-1:args.n_skip] - y_init), color='m', label='Initial')
    axs[1].plot(time[:n_frames-1:args.n_skip], np.abs(y_gt[:n_frames-1:args.n_skip] - y_est_imu), color='r', label='IMU')
    axs[1].plot(time[:n_frames-1:args.n_skip], np.abs(y_gt[:n_frames-1:args.n_skip] - y_est_full), color='b', label='VIO')
    axs[1].set_xlabel('$t\ (s)$')
    axs[1].set_ylabel('$e_y\ (m)$')

    # Plot theta
    axs[2].grid(True)
    axs[2].plot(time[:n_frames-1:args.n_skip], np.abs(theta_gt[:n_frames-1:args.n_skip] - theta_init), color='m', label='Initial')
    axs[2].plot(time[:n_frames-1:args.n_skip], np.abs(theta_gt[:n_frames-1:args.n_skip] - theta_est_imu), color='r', label='IMU')
    axs[2].plot(time[:n_frames-1:args.n_skip], np.abs(theta_gt[:n_frames-1:args.n_skip] - theta_est_full), color='b', label='VIO')
    axs[2].set_xlabel('$t\ (s)$')
    axs[2].set_ylabel('$e_{\\theta}\ (rad)$')
    
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.savefig('errors.eps')

    plt.show()




