"""
Import 7-scenes dataset to kapture format for DUSt3R visloc evaluation.

Following DUSt3R's expected format:
- mapping/sensors/records_data/seq-XX/frame-XXXXXX.color.png
- mapping/sensors/records_data/seq-XX/frame-XXXXXX.depth.reg (16-bit depth in mm)
- query/sensors/records_data/seq-XX/frame-XXXXXX.color.png
"""

import os
import shutil
import numpy as np
from PIL import Image
from pathlib import Path

def convert_depth_to_reg(depth_png_path: str, output_reg_path: str):
    """
    Convert 7-scenes depth.png to kapture .depth.reg format.
    7-scenes depth.png is 16-bit PNG with depth in millimeters.
    kapture .depth.reg is raw binary float32 (no header, just raw data).
    """
    depth_img = Image.open(depth_png_path)
    depth_array = np.array(depth_img, dtype=np.uint16)
    
    # Convert to float32 depth in meters
    depth_m = depth_array.astype(np.float32) / 1000.0
    
    # Save as raw binary (kapture depth_map_from_file expects just raw float32 data)
    depth_m.tofile(output_reg_path)

def create_kapture_structure(scene_path: str):
    """Create kapture directory structure for 7-scenes."""
    scene_path = Path(scene_path)
    
    # Read split files
    train_split_file = scene_path / "TrainSplit.txt"
    test_split_file = scene_path / "TestSplit.txt"
    
    with open(train_split_file, 'r') as f:
        train_seqs = [line.strip() for line in f if line.strip().startswith('sequence')]
    
    with open(test_split_file, 'r') as f:
        test_seqs = [line.strip() for line in f if line.strip().startswith('sequence')]
    
    print(f"Train sequences (mapping): {train_seqs}")
    print(f"Test sequences (query): {test_seqs}")
    
    # Create directories
    mapping_path = scene_path / "mapping"
    query_path = scene_path / "query"
    
    for path in [mapping_path, query_path]:
        (path / "sensors" / "records_data").mkdir(parents=True, exist_ok=True)
    
    # Intrinsics for 7-scenes (from original dataset)
    # SIMPLE_PINHOLE: fx=fy=525, cx=320, cy=240, W=640, H=480
    fx, fy, cx, cy = 525.0, 525.0, 320.0, 240.0
    W, H = 640, 480
    
    # Process mapping sequences (train)
    process_split(scene_path, mapping_path, train_seqs, fx, fy, cx, cy, W, H, include_depth=True)
    
    # Process query sequences (test)  
    process_split(scene_path, query_path, test_seqs, fx, fy, cx, cy, W, H, include_depth=False)
    
    print("\nDone! Kapture structure created.")
    print(f"Mapping: {mapping_path}")
    print(f"Query: {query_path}")

def process_split(scene_path: Path, output_path: Path, sequences: list, 
                  fx: float, fy: float, cx: float, cy: float, W: int, H: int,
                  include_depth: bool = False):
    """Process a split (mapping or query) of the dataset."""
    
    sensors_path = output_path / "sensors"
    records_data_path = sensors_path / "records_data"
    
    # Create sensor file
    sensors_txt = sensors_path / "sensors.txt"
    with open(sensors_txt, 'w') as f:
        f.write("# kapture format: 1.1\n")
        f.write("# sensor_id, name, sensor_type, [sensor_params]+\n")
        f.write(f"kinect_rgb, kinect_rgb, camera, SIMPLE_PINHOLE, {W}, {H}, {fx}, {cx}, {cy}\n")
        if include_depth:
            f.write(f"kinect_depth, kinect_depth, depth, SIMPLE_PINHOLE, {W}, {H}, {fx}, {cx}, {cy}\n")
    
    # Create rigs file (kinect rig)
    rigs_txt = sensors_path / "rigs.txt"
    with open(rigs_txt, 'w') as f:
        f.write("# kapture format: 1.1\n")
        f.write("# rig_id, sensor_id, qw, qx, qy, qz, tx, ty, tz\n")
        f.write("kinect, kinect_rgb, 1, 0, 0, 0, 0, 0, 0\n")
        if include_depth:
            f.write("kinect, kinect_depth, 1, 0, 0, 0, 0, 0, 0\n")
    
    # Collect all frames
    records_camera = []
    records_depth = []
    trajectories = []
    
    timestamp = 1000
    
    for seq_name in sequences:
        # Convert sequence1 -> seq-01
        seq_num = int(seq_name.replace('sequence', ''))
        seq_folder = f"seq-{seq_num:02d}"
        
        seq_path = scene_path / seq_folder
        if not seq_path.exists():
            print(f"Warning: {seq_path} not found, skipping")
            continue
        
        # Create output seq folder
        out_seq_path = records_data_path / seq_folder
        out_seq_path.mkdir(parents=True, exist_ok=True)
        
        # Find all frames
        frame_files = sorted(seq_path.glob("frame-*.color.png"))
        
        for frame_file in frame_files:
            frame_name = frame_file.stem.replace('.color', '')  # frame-000000
            
            # Copy color image
            color_src = frame_file
            color_dst = out_seq_path / f"{frame_name}.color.png"
            if not color_dst.exists():
                shutil.copy2(color_src, color_dst)
            
            # Record in records_camera
            image_path = f"{seq_folder}/{frame_name}.color.png"
            records_camera.append(f"{timestamp}, kinect_rgb, {image_path}")
            
            # Process depth if needed (for mapping)
            if include_depth:
                depth_src = seq_path / f"{frame_name}.depth.png"
                if depth_src.exists():
                    depth_dst = out_seq_path / f"{frame_name}.depth.reg"
                    if not depth_dst.exists():
                        convert_depth_to_reg(str(depth_src), str(depth_dst))
                    depth_path = f"{seq_folder}/{frame_name}.depth.reg"
                    records_depth.append(f"{timestamp}, kinect_depth, {depth_path}")
            
            # Read pose
            pose_file = seq_path / f"{frame_name}.pose.txt"
            if pose_file.exists():
                pose_matrix = np.loadtxt(pose_file)
                # pose_matrix is camera-to-world (cam2world)
                # kapture trajectories.txt stores world-to-camera (world2cam)
                # so we need to invert the pose
                world_to_cam = np.linalg.inv(pose_matrix)
                
                R = world_to_cam[:3, :3]
                t = world_to_cam[:3, 3]
                
                # Convert rotation matrix to quaternion (wxyz)
                qw, qx, qy, qz = rotation_matrix_to_quaternion(R)
                tx, ty, tz = t
                
                trajectories.append(f"    {timestamp}, kinect, {qw}, {qx}, {qy}, {qz}, {tx}, {ty}, {tz}")
            
            timestamp += 1
    
    # Write records_camera.txt
    records_camera_txt = sensors_path / "records_camera.txt"
    with open(records_camera_txt, 'w') as f:
        f.write("# kapture format: 1.1\n")
        f.write("# timestamp, device_id, image_path\n")
        for line in records_camera:
            f.write(line + "\n")
    
    # Write records_depth.txt if needed
    if include_depth and records_depth:
        records_depth_txt = sensors_path / "records_depth.txt"
        with open(records_depth_txt, 'w') as f:
            f.write("# kapture format: 1.1\n")
            f.write("# timestamp, device_id, depth_path\n")
            for line in records_depth:
                f.write(line + "\n")
    
    # Write trajectories.txt
    trajectories_txt = sensors_path / "trajectories.txt"
    with open(trajectories_txt, 'w') as f:
        f.write("# kapture format: 1.1\n")
        f.write("# timestamp, device_id, qw, qx, qy, qz, tx, ty, tz\n")
        for line in trajectories:
            f.write(line + "\n")
    
    print(f"Processed {len(records_camera)} frames for {output_path.name}")

def rotation_matrix_to_quaternion(R):
    """Convert a rotation matrix to quaternion (w, x, y, z)."""
    trace = np.trace(R)
    
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    
    return w, x, y, z

if __name__ == "__main__":
    scene_path = r"C:\Users\SoLoMoN\Documents\GitHub\Lightweight-Feedforward-3D-Reconstruction-work\datasets\7-scenes\heads"
    create_kapture_structure(scene_path)
