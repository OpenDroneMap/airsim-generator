from PIL import Image
import io
import piexif
from osgeo import osr
import math
from fractions import Fraction
from camera_constants import FOCAL, CCD_WIDTH

def save_jpg(filename, image_data):
    im = Image.open(io.BytesIO(image_data))
    im = im.convert('RGB')
    im.save(filename)

def get_utm_zone_and_hemisphere_from(lon, lat):
    """
    Calculate the UTM zone and hemisphere that a longitude/latitude pair falls on
    :param lon longitude
    :param lat latitude
    :return [utm_zone, hemisphere]
    """
    utm_zone = (int(math.floor((lon + 180.0)/6.0)) % 60) + 1
    hemisphere = 'S' if lat < 0 else 'N'
    return [utm_zone, hemisphere]

def get_utm_proj(lon, lat):
    utm_zone, hemisphere = get_utm_zone_and_hemisphere_from(lon, lat)
    return "+proj=utm +zone=%s %s+datum=WGS84 +units=m +no_defs" % (utm_zone, "" if hemisphere == "N" else "+south")


class GeoToLocalTransformer:
    def __init__(self, utm_proj):
        src = osr.SpatialReference()
        src.ImportFromEPSG(4326)
        src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        tgt = osr.SpatialReference()
        tgt.ImportFromProj4(utm_proj)

        self.ct = osr.CoordinateTransformation(src, tgt)
        self.cti = osr.CoordinateTransformation(tgt, src)

    def transform(self, lon, lat, alt):
        return self.ct.TransformPoint(lon, lat, alt)

    def reverse(self, x, y, z):
        return self.cti.TransformPoint(x, y, z)

def to_epsg(proj_def):
    c = osr.SpatialReference()
    c.ImportFromProj4(proj_def)
    c.AutoIdentifyEPSG()
    return c.GetAttrValue("AUTHORITY", 1)

def to_rational(number):
    f = Fraction(str(number))
    return (f.numerator, f.denominator)

# Based on https://gist.github.com/c060604/8a51f8999be12fc2be498e9ca56adc72
def gps_exif_ifd(lat, lng, altitude):
    def to_deg(value, loc):
        """convert decimal coordinates into degrees, munutes and seconds tuple
        Keyword arguments: value is float gps-value, loc is direction list ["S", "N"] or ["W", "E"]
        return: tuple like (25, 13, 48.343 ,'N')
        """
        if value < 0:
            loc_value = loc[0]
        elif value > 0:
            loc_value = loc[1]
        else:
            loc_value = ""
        abs_value = abs(value)
        deg =  int(abs_value)
        t1 = (abs_value-deg)*60
        min = int(t1)
        sec = round((t1 - min)* 60, 7)
        return (deg, min, sec, loc_value)

    lat_deg = to_deg(lat, ["S", "N"])
    lng_deg = to_deg(lng, ["W", "E"])

    exiv_lat = (to_rational(lat_deg[0]), to_rational(lat_deg[1]), to_rational(lat_deg[2]))
    exiv_lng = (to_rational(lng_deg[0]), to_rational(lng_deg[1]), to_rational(lng_deg[2]))
    gps_ifd = {
        piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
        piexif.GPSIFD.GPSAltitudeRef: 1 if altitude < 0 else 0,
        piexif.GPSIFD.GPSAltitude: to_rational(abs(altitude)),
        piexif.GPSIFD.GPSLatitudeRef: lat_deg[3],
        piexif.GPSIFD.GPSLatitude: exiv_lat,
        piexif.GPSIFD.GPSLongitudeRef: lng_deg[3],
        piexif.GPSIFD.GPSLongitude: exiv_lng,
    }

    return gps_ifd


def rotate(point, center, degrees):
    r = math.radians(degrees)
    return [math.cos(r) * (point[0] - center[0]) - math.sin(r) * (point[1] - center[1]) + center[0],
            math.sin(r) * (point[0] - center[0]) + math.cos(r) * (point[1] - center[1]) + center[1]]

def image_footprint(camera_pos, image_width, image_height):
    altitude = camera_pos[2]

    sensor_width = image_width / CCD_WIDTH
    sensor_height = image_height / CCD_WIDTH

    x_view = 2.0 * math.atan(sensor_width / (2.0 * FOCAL))
    y_view = 2.0 * math.atan(sensor_height / (2.0 * FOCAL))

    pitch = -90 # nadir
    roll = 0
    yaw = 0 # TODO!

    bottom = altitude * math.tan(math.radians(90.0 + pitch) - 0.5 * y_view)
    top = altitude * math.tan(math.radians(90.0 + pitch) + 0.5 * y_view)
    left = altitude * math.tan(math.radians(roll) - 0.5 * x_view)
    right = altitude * math.tan(math.radians(roll) + 0.5 * x_view)

    ul = rotate((camera_pos[0] + left, camera_pos[1] + top), camera_pos, -yaw)
    ur = rotate((camera_pos[0] + right, camera_pos[1] + top), camera_pos, -yaw)
    ll = rotate((camera_pos[0] + left, camera_pos[1] + bottom), camera_pos, -yaw)
    lr = rotate((camera_pos[0] + right, camera_pos[1] + bottom), camera_pos, -yaw)

    return [ul, ur, lr, ll]

def calculate_overlap_offset(image_width, image_height, altitude, frontlap=0.85, sidelap=0.7):
    gsd = (CCD_WIDTH * altitude * 100.0) / (FOCAL * image_width)
    footprint_width = (gsd * image_width) / 100.0
    footprint_height = (gsd * image_height) / 100.0

    offset_x = (1 - frontlap) * footprint_height / frontlap
    offset_y = (1 - sidelap) * footprint_width / sidelap
    
    return (offset_x, offset_y)
    