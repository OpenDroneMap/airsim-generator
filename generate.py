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
from utils import save_jpg, GeoToLocalTransformer, get_utm_proj, calculate_overlap_offset
from camera import Camera

parser = argparse.ArgumentParser(description='Generate photos and elevation models from Microsoft AirSim')
parser.add_argument('host',
                type=str,
                default='localhost',
                help='Hostname of the computer where AirSim is running. Default:  %(default)s')
parser.add_argument('--survey',
                type=str,
                default=None,
                help='Axis-aligned area to survey (as a JSON array in world coordinates: [minx, miny, maxx, maxy]). Default: entire world boundaries.')
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
parser.add_argument('--output-dir',
                type=str,
                default=".",
                help="Directory where to output results. Default: %(default)s")


args = parser.parse_args()
#gps_origin = json.loads(args.gps_origin)


print("Connecting to AirSim (%s) ..." % args.host)
client = airsim.VehicleClient(ip=args.host)
try:
    client.confirmConnection()
    print("Connected!")
except Exception as e:
    print("Connection failed (is AirSim running?)")
    exit(1)


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

# [(minx, miny), (maxx, maxy)]
local_boundaries = [
    (boundaries[0][0] - geo_center[0], boundaries[0][1] - geo_center[1]),
    (boundaries[1][0] - geo_center[0], boundaries[1][1] - geo_center[1]),
]

print("Local boundaries (m): %s" % local_boundaries)

c = Camera(client, geo_center, airsim.ImageType.Scene, utm_proj)

print("Fetching image size...", end="")
# img_width, img_height = c.get_image_size()
img_width = 4000
img_height = 2250
print("%sx%spx" % (img_width, img_height))

offset_x, offset_y = calculate_overlap_offset(img_width, img_height, args.altitude, args.frontlap / 100.0, args.sidelap / 100.0)
print("Front overlap (%.0f%%): %.2fm" % (args.frontlap, offset_x))
print("Side overlap (%.0f%%): %.2fm" % (args.sidelap, offset_y))
c.move_by(local_boundaries[0][0], local_boundaries[0][1], -args.altitude) # Go to altitude, move to bottom-left corner

num_photos_x = math.ceil((local_boundaries[1][0] - local_boundaries[0][0]) / offset_x)
num_photos_y = math.ceil((local_boundaries[1][1] - local_boundaries[0][1]) / offset_y)
x_direction = 1

print("Number of photos: %s" % (num_photos_x * num_photos_y))
for y in range(0, num_photos_y):
    for x in range(0, num_photos_x):
        c.move_by(offset_x * x_direction, 0)
        c.capture(os.path.join(args.output_dir, 'perspective%04d.jpg' % x))

        if x == 4:
            exit(1)

    c.move_by(0, offset_y)
    x_direction *= -1

# c.move_by(-20, 20, 0)
# responses = client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.DepthPlanar, pixels_as_float=True, compress=True)])
# response = responses[0]

# data = np.array(response.image_data_float).reshape((response.width, response.height))

# profile = {
#     'driver': 'GTiff',
#     'height': data.shape[0], 
#     'width': data.shape[1],
#     'count': 1, 
#     'dtype': str(data.dtype)
# }
# with rasterio.open("dsm.tif", "w", **profile) as f:
#     f.write(data, 1)

# print("OK")