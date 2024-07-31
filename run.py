import argparse
import cv2
import glob
import matplotlib
import numpy as np
import os
import torch
from depth_anything_v2.dpt import DepthAnythingV2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Depth Anything V2')
    
    parser.add_argument('--img-path', type=str, default='inputpics')
    parser.add_argument('--input-size', type=int, default=518)
    parser.add_argument('--outdir', type=str, default='outputpics')
    parser.add_argument('--encoder', type=str, default='vitl', choices=['vits', 'vitb', 'vitl', 'vitg'])
    parser.add_argument('--pred-only', dest='pred_only', action='store_true', help='only display the prediction')
    parser.add_argument('--color', dest='color', action='store_true', help='apply colorful palette')
    parser.add_argument("--precision", type=str, default='fp16', choices= ['fp32', 'fp16'])
    
    args = parser.parse_args()
    
    DEVICE = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    
    model_configs = {
        'vits': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
        'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
        'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
        'vitg': {'encoder': 'vitg', 'features': 384, 'out_channels': [1536, 1536, 1536, 1536]}
    }
    
    depth_anything = DepthAnythingV2(**model_configs[args.encoder])
    depth_anything.load_state_dict(torch.load(f'checkpoints/depth_anything_v2_{args.encoder}.pth', map_location='cpu'))
    depth_anything = depth_anything.to(DEVICE).eval()

    if args.precision == 'fp16':
        depth_anything = depth_anything.half()
    else:
        args.precision = 'fp32'
        depth_anything = depth_anything.float()
    
    if os.path.isfile(args.img_path):
        if args.img_path.endswith('txt'):
            with open(args.img_path, 'r') as f:
                filenames = f.read().splitlines()
        else:
            filenames = [args.img_path]
    else:
        filenames = glob.glob(os.path.join(args.img_path, '**/*'), recursive=True)
    
    os.makedirs(args.outdir, exist_ok=True)
    
    cmap = matplotlib.colormaps.get_cmap('Spectral_r')
    
    for k, filename in enumerate(filenames):
        print(f'Progress {k+1}/{len(filenames)}: {filename}')
        
        raw_image = cv2.imread(filename)

        ### -------------------
        # --input_size is irrelevant and should rather be derived automatically from the input image
        # it's easier that way and less error-prone from the user's perspective
        # The size must be a multiple of 14 hence why we will use the same logic as in the run_video.py script
        ### -------------------

        raw_image_height = raw_image.shape[0]
        raw_image_width = raw_image.shape[1]
        aspect_ratio = raw_image_width / raw_image_height

        new_iamge_height = round(raw_image_height / 14) * 14
        new_image_width = round(raw_image_width * aspect_ratio / 14) * 14

        print(f'Aspect ratio: {aspect_ratio}, New Height and Width: {new_iamge_height}x{new_image_width}')

        depth = depth_anything.infer_image(raw_image, precision=args.precision, newHeight=new_iamge_height, newWidth=new_image_width)
        
        depth = (depth - depth.min()) / (depth.max() - depth.min()) * 65536.0
        depth = depth.cpu().numpy().astype(np.uint16)
        
        if args.color:
            depth = (cmap(depth)[:, :, :3] * 65536)[:, :, ::-1]
        else:
            depth = np.repeat(depth[..., np.newaxis], 3, axis=-1)
            
        topimage = raw_image.astype(np.uint16) * 255
        bottomimage = depth
        
        if args.pred_only:
            cv2.imwrite(os.path.join(args.outdir, os.path.splitext(os.path.basename(filename))[0] + '.png'), depth)
        else:
            #split_region = np.ones((raw_image.shape[0], 50, 3), dtype=np.uint16) * 65536
            combined_result = cv2.vconcat([topimage, bottomimage])
            
            cv2.imwrite(os.path.join(args.outdir, os.path.splitext(os.path.basename(filename))[0] + '.png'), combined_result)
