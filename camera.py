import airsim
import piexif
import io
from PIL import Image
from math import pi
from datetime import datetime, timedelta

from utils import gps_exif_ifd, GeoToLocalTransformer, to_rational
from camera_constants import FOCAL, CCD_WIDTH

LOOK_DOWN = airsim.to_quaternion(-pi/2, 0, 0)

class Camera:
    def __init__(self, client, geo_center, imageType, utm_proj, world_offset_z):
        self.client = client
        self.geo = [*geo_center]
        self.imageType = imageType

        self.ct = GeoToLocalTransformer(utm_proj)

        # Init camera position
        self.geo[2] = world_offset_z
        self.client.simSetVehiclePose(airsim.Pose(airsim.Vector3r(0, 0, 0), LOOK_DOWN), ignore_collision=True)
        
        vpos = self.client.simGetVehiclePose().position
        self.position = [vpos.x_val, vpos.y_val, vpos.z_val]

        self.time = datetime.now()
    
    def get_image_size(self):
        if self.imageType == airsim.ImageType.Scene:
            imData = self.client.simGetImage('0', self.imageType)
            im = Image.open(io.BytesIO(imData))
            return (im.width, im.height)
        elif self.imageType == airsim.ImageType.DepthPlanar:
            response = self.client.simGetImages([airsim.ImageRequest("0", airsim.ImageType.DepthPlanar, pixels_as_float=True, compress=True)])[0]
            return (response.width, response.height)
        else:
            raise("Unsupported image type")

    def move_by(self, x, y, z = 0):
        self.position[0] += x
        self.position[1] += y
        self.position[2] += z
        
        self.geo[1] += x
        self.geo[0] += y
        self.geo[2] -= z

        pose = airsim.Pose(airsim.Vector3r(self.position[0], self.position[1], self.position[2]), LOOK_DOWN)
        self.client.simSetVehiclePose(pose, ignore_collision=True)

        self.time += timedelta(0, 10)
    
    def get_gps(self):
        # Convert geo to lat/lon/alt
        p = self.ct.reverse(*self.geo)
        
        return {
            'longitude': p[0],
            'latitude': p[1],
            'altitude': p[2]
        }

    def capture(self, filename):
        imData = self.client.simGetImage('0', self.imageType)
        im = Image.open(io.BytesIO(imData))

        gps = self.get_gps()

        exif_d = {
            'GPS': gps_exif_ifd(gps['latitude'], gps['longitude'], gps['altitude']),
            '0th': {
                piexif.ImageIFD.Make: "Microsoft",
                piexif.ImageIFD.Model: "AirSim",
                piexif.ImageIFD.ImageWidth: im.width,
                piexif.ImageIFD.ImageLength: im.height,
            },
            'Exif': {
                piexif.ExifIFD.DateTimeOriginal: self.time.strftime("%Y:%m:%d %H:%M:%S"),
                piexif.ExifIFD.FocalLength: to_rational(FOCAL),
                piexif.ExifIFD.FocalPlaneResolutionUnit: 4, #mm,
                piexif.ExifIFD.FocalPlaneXResolution: to_rational(round(im.width / CCD_WIDTH, 7)),
                piexif.ExifIFD.FocalPlaneYResolution: to_rational(round(im.width / CCD_WIDTH, 7)),
            }
        }
        
        im = im.convert('RGB')
        im.save(filename, exif=piexif.dump(exif_d))

        return filename