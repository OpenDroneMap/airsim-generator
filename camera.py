import airsim
import piexif
import io
from PIL import Image
from math import pi

from utils import gps_exif_dict, GeoToLocalTransformer

LOOK_DOWN = airsim.to_quaternion(-pi/2, 0, 0)

class Camera:
    def __init__(self, client, geo_center, imageType, utm_proj):
        self.client = client
        self.geo = geo_center
        self.imageType = imageType

        self.ct = GeoToLocalTransformer(utm_proj)

        # Init camera position
        self.geo[2] = 0
        self.client.simSetVehiclePose(airsim.Pose(airsim.Vector3r(0, 0, 0), LOOK_DOWN), ignore_collision=True)
        
        vpos = self.client.simGetVehiclePose().position
        self.position = [vpos.x_val, vpos.y_val, vpos.z_val]

    def move_by(self, x, y, z = 0):
        self.position[0] += x
        self.position[1] += y
        self.position[2] += z
        
        self.geo[1] += x
        self.geo[0] += y
        self.geo[2] -= z

        pose = airsim.Pose(airsim.Vector3r(self.position[0], self.position[1], self.position[2]), LOOK_DOWN)
        self.client.simSetVehiclePose(pose, ignore_collision=True)
    
    def get_gps(self):
        # Convert geo to lat/lon/alt
        p = self.ct.reverse(*self.geo)
        print(p)
        return {
            'longitude': p[0],
            'latitude': p[1],
            'altitude': p[2]
        }

    def capture(self, filename):
        imData = self.client.simGetImage('0', self.imageType)

        gps = self.get_gps()
        im = Image.open(io.BytesIO(imData))
        im = im.convert('RGB')
        im.save(filename, exif=piexif.dump(gps_exif_dict(gps['latitude'], gps['longitude'], gps['altitude'])))