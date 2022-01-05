#!/usr/bin/env python3
# Author: Piero Toffanin
# License: AGPLv3

import airsim
import numpy as np
import rasterio
import argparse
import json
import os
from utils import save_jpg, GeoToLocalTransformer, get_utm_proj
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
                default=40,
                help='Survey altitude (meters). Default: %(default)s')
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

area_width = boundaries[1][0] - boundaries[0][0]
area_height = boundaries[1][1] - boundaries[0][1]

print("X span: %.2fm" % area_width)
print("Y span: %.2fm" % area_height)
print("Area: %.2f m^2" % (area_width * area_height))

print("Geographical center (UTM)... ", end="")
geo_center = [boundaries[0][0] + area_width / 2.0, boundaries[0][1] + area_height / 2.0, boundaries[0][2]]
print(geo_center)

c = Camera(client, geo_center, airsim.ImageType.Scene, utm_proj)

c.move_by(0, 0, -args.altitude) # Go to altitude

for y in range(0, 5):
    c.move_by(0, 5)
    c.capture(os.path.join(args.output_dir, 'perspective%s.jpg' % y))

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