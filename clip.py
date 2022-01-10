from osgeo import gdal
from osgeo.gdalconst import GA_ReadOnly
import argparse
import subprocess
from pipes import quote

parser = argparse.ArgumentParser(description='Clip rasters (with the same CRS)')
parser.add_argument('input',
                type=str,
                help='Input raster')
parser.add_argument('mask',
                type=str,
                help='Mask raster')
parser.add_argument('output',
                type=str,
                default="clipped.tif",
                help='Output raster')
args = parser.parse_args()

data = gdal.Open(args.mask, GA_ReadOnly)
geoTransform = data.GetGeoTransform()
minx = geoTransform[0]
maxy = geoTransform[3]
maxx = minx + geoTransform[1] * data.RasterXSize
miny = maxy + geoTransform[5] * data.RasterYSize

cmd = 'gdal_translate -projwin ' + ' '.join([str(x) for x in [minx, maxy, maxx, miny]]) + ' -a_ullr ' + ' '.join([str(x) for x in [minx, maxy, maxx, miny]]) + ' -of GTiff ' + quote(args.input) + " " + quote(args.output)
print(cmd)
subprocess.check_output(cmd, shell=True)