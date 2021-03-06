#!/usr/bin/env python3
# Author: Piero Toffanin
# License: AGPLv3

import airsim
import numpy as np
import rasterio
import argparse
import json
import os
import math
from utils import save_jpg, GeoToLocalTransformer, get_utm_proj, to_epsg, calculate_overlap_offset
from camera import Camera, LOOK_DOWN

parser = argparse.ArgumentParser(description='Generate photos and elevation models from Microsoft AirSim')
parser.add_argument('host',
                type=str,
                default='localhost',
                help='Hostname of the computer where AirSim is running. Default:  %(default)s')
parser.add_argument('--survey',
                type=str,
                default=None,
                help='Axis-aligned area to survey (as a JSON array in local coordinates: [minx, miny, maxx, maxy]). Default: entire world boundaries.')
parser.add_argument('--altitude',
                type=float,
                default=80,
                help='Survey altitude (meters). Default: %(default)s')
parser.add_argument('--frontlap',
                type=float,
                default=83,
                help='Image frontlap percentage. Default: %(default)s%')
parser.add_argument('--sidelap',
                type=float,
                default=75,
                help='Image sidelap percentage. Default: %(default)s%')
parser.add_argument('--dsm',
                action="store_true",
                default=False,
                help="Generate a DSM of the survey area.")
parser.add_argument('--ortho-width',
                default=12.8,
                help="AirSim's camera ortho width value (MUST match the simulation settings). Default: %(default)s")
parser.add_argument('--output-dir',
                type=str,
                default=".",
                help="Directory where to output results. Default: %(default)s")
parser.add_argument('--flash-survey',
                action="store_true",
                default=False,
                help="Plot in AirSim the survey's extent and exit.")
parser.add_argument('--world-z-origin',
                type=float,
                default=4.85,
                help='World Z origin value in meters. This is the elevation value from the DSM at (0, 0, --local-z-origin). Default: %(default)s%')
parser.add_argument('--local-z-origin',
                type=float,
                default=1.15,
                help='Local Z origin value in meters. This is the elevation value in local coordinates for (0, 0, --world-z-origin). Default: %(default)s%')

args = parser.parse_args()

print("Connecting to AirSim (%s) ..." % args.host)
client = airsim.VehicleClient(ip=args.host)
try:
    client.confirmConnection()
    print("Connected!")
except Exception as e:
    print("Connection failed (is AirSim running?)")
    exit(1)

# Reset vehicle position
pose = airsim.Pose(airsim.Vector3r(0, 0, 0), LOOK_DOWN)
client.simSetVehiclePose(pose, ignore_collision=True)

geo_min, geo_max = client.simGetWorldExtents()
utm_proj = get_utm_proj(geo_min.longitude, geo_min.latitude)
print("")
print("Geographical projection: %s" % (utm_proj))

g2lt = GeoToLocalTransformer(utm_proj)

print("Geographical extent (UTM)... ", end="")
boundaries = [g2lt.transform(geo_min.longitude, geo_min.latitude, geo_min.altitude),
                g2lt.transform(geo_max.longitude, geo_max.latitude, geo_max.altitude)]
print(boundaries)

area_height = boundaries[1][0] - boundaries[0][0]
area_width = boundaries[1][1] - boundaries[0][1]

print("N/S span: %.2fm" % area_height)
print("E/W span: %.2fm" % area_width)
print("Area: %.2f m^2" % (area_width * area_height))

print("Geographical center (UTM)... ", end="")
geo_center = [boundaries[0][0] + area_width / 2.0, boundaries[0][1] + area_height / 2.0, boundaries[0][2]]
print(geo_center)

survey_boundaries = [
    (boundaries[0][0] - geo_center[0], boundaries[0][1] - geo_center[1]),
    (boundaries[1][0] - geo_center[0], boundaries[1][1] - geo_center[1]),
]

print("Survey boundaries (m): %s" % survey_boundaries)

if args.survey:
    survey_boundaries = json.loads(args.survey)
    print("User-defined survey boundaries (m): %s" % survey_boundaries)
else:
    print("Surveying entire world")

minx, miny, maxx, maxy = (survey_boundaries[0][0], survey_boundaries[0][1], survey_boundaries[1][0], survey_boundaries[1][1])

if args.flash_survey:
    plot_z = -5
    client.simPlotLineList([airsim.Vector3r(minx, miny, plot_z),
                            airsim.Vector3r(maxx, miny, plot_z),
                            airsim.Vector3r(maxx, miny, plot_z),
                            airsim.Vector3r(maxx, maxy, plot_z),
                            airsim.Vector3r(maxx, maxy, plot_z),
                            airsim.Vector3r(minx, maxy, plot_z),
                            airsim.Vector3r(minx, maxy, plot_z),
                            airsim.Vector3r(minx, miny, plot_z),
                            ], color_rgba=[0.0, 1.0, 0.0, 1.0], thickness=200.0, duration=10, is_persistent=False)
    print("Survey area flashed")
    exit(0)

if args.dsm:
    c = Camera(client, geo_center, airsim.ImageType.DepthPlanar, utm_proj, args.world_z_origin, args.local_z_origin)
else:
    c = Camera(client, geo_center, airsim.ImageType.Scene, utm_proj, args.world_z_origin, args.local_z_origin)

print("Fetching image size... ", end="", flush=True)
img_width, img_height = c.get_image_size()
#img_width = 256
#img_height = 256
print("%sx%spx" % (img_width, img_height))
if img_width != img_height and args.dsm:
    raise "Image width and height must match in DSM mode"

if args.dsm:
    # Calculate number of tiles

    num_tiles_x = math.ceil((maxx - minx) / args.ortho_width)
    num_tiles_y = math.ceil((maxy - miny) / args.ortho_width)

    print("Number tiles X: %s" % num_tiles_x)
    print("Number tiles Y: %s" % num_tiles_y)

    # Top/left corner
    start_x = maxx + (num_tiles_x * args.ortho_width - (maxx - minx))
    start_y = miny

    # Convert to UTM
    offset_x_utm = geo_center[0] + miny
    offset_y_utm = geo_center[1] + minx + num_tiles_x * args.ortho_width

    res = args.ortho_width / img_width

    # Allocate image
    profile = {
        'driver': 'GTiff',
        'height': img_height * num_tiles_x, 
        'width': img_width * num_tiles_y,
        'count': 1, 
        'dtype': rasterio.dtypes.float32,
        'crs': {'init': 'epsg:%s' % to_epsg(utm_proj)},
        'transform': rasterio.Affine(res, 0.0, offset_x_utm,
                                     0.0, -res, offset_y_utm)
    }

    print("Output image size: %sx%spx" % (profile['width'], profile['height']))

    pad_x = num_tiles_x * args.ortho_width - (maxx - minx)
    #pad_y = num_tiles_y * args.ortho_width - (maxy - miny)
    

    pose = airsim.Pose(airsim.Vector3r(start_x - args.ortho_width / 2.0, 
                                       start_y + args.ortho_width / 2.0, 
                                       -args.altitude * 2), LOOK_DOWN)

    # Make empty request to flush depth values (?)
    # We get strange tiles if we don't do this at the beginning
    client.simSetVehiclePose(pose, ignore_collision=True)
    response = client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.DepthPlanar, pixels_as_float=True, compress=True)])[0]
                
    outfile = os.path.join(args.output_dir, "ground_truth_dsm.tif")
    with rasterio.open(outfile, "w", **profile) as f:
        for y in range(0, num_tiles_y):
            for x in range(0, num_tiles_x):
                if x > 0:
                    pose.position.x_val -= args.ortho_width
                
                client.simSetVehiclePose(pose, ignore_collision=True)

                response = client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.DepthPlanar, pixels_as_float=True, compress=True)])[0]
                data = np.array(response.image_data_float).reshape((response.width, response.height))
                w = rasterio.windows.Window(y * img_height, x * img_width, img_width, img_height)
                print(w)
                f.write(data, window=w, indexes=1)
                #exit(1)

            pose.position.x_val = start_x  - args.ortho_width / 2.0
            pose.position.y_val += args.ortho_width

    print("Wrote %s" % outfile)
else:
    offset_x, offset_y = calculate_overlap_offset(img_width, img_height, args.altitude, args.frontlap / 100.0, args.sidelap / 100.0)
    print("Front overlap (%.0f%%): %.2fm" % (args.frontlap, offset_x))
    print("Side overlap (%.0f%%): %.2fm" % (args.sidelap, offset_y))
    c.move_by(minx, miny, -args.altitude) # Go to altitude, move to bottom-left corner

    num_photos_x = math.ceil((maxx - minx) / offset_x)
    num_photos_y = math.ceil((maxy - miny) / offset_y)
    x_direction = 1

    print("Number of photos: %s" % (num_photos_x * num_photos_y))
    i = 0
    for y in range(0, num_photos_y):
        for x in range(0, num_photos_x):
            if x > 0:
                c.move_by(offset_x * x_direction, 0)
            print(c.capture(os.path.join(args.output_dir, 'perspective%04d.jpg' % i)))
            i += 1

        c.move_by(0, offset_y)
        x_direction *= -1
